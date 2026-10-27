"""Gate 4 v2: mask raster decoding, silhouette stats, masked colour.

The ground-truth vector is the real mask payload captured in the
Night Queue's live SAM probe (artifacts/probe_B_20261027T014808Z.json,
the matte red kettle at 0.9766). Its expected raster hash was
produced by Meta's reference codec (meta-sam-parser) decoding the
same payload; the ported decoder in runway.sam must reproduce it
byte for byte. The one_bit vector was encoded by the reference
encoder from the synthetic raster rebuilt in the test.
"""
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from runway.sam import (  # noqa: E402
    SamBox,
    SamMask,
    SamShapeError,
    decode_mask_raster,
    mask_stats,
    masked_colour,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

ONE_BIT_PAYLOAD = "!!!!!0CA'&T-hTbsKI:t{!!"
ONE_BIT_SHA256 = "3932032debdc619dccfe13e13261e8623e8b07553f8e29a1723eb319478c94a9"
PROBE_RASTER_SHA256 = (
    "0234c55b10279c1b6315e826862a0e08c21a53c412e7f545bee08434a940f4b8"
)


def one_bit_raster():
    w, h = 24, 16
    raster = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if 4 <= x <= 19 and 3 <= y <= 12 and not (16 <= x and y <= 5):
                raster[y * w + x] = 1
    return bytes(raster)


class MaskDecodeTests(unittest.TestCase):
    def test_lossless_probe_payload_matches_reference_raster(self):
        payload = open(os.path.join(FIXTURES, "probe_mask_payload.txt")).read()
        mask = SamMask(height=684, width=1024, payload=payload,
                       encoding="lossless", confidence=0.9766)
        raster = decode_mask_raster(mask)
        self.assertEqual(len(raster), 684 * 1024)
        self.assertTrue(set(raster) <= {0, 1})
        self.assertEqual(hashlib.sha256(raster).hexdigest(), PROBE_RASTER_SHA256)
        self.assertEqual(sum(raster), 320307)

    def test_one_bit_round_trip_vector(self):
        mask = SamMask(height=16, width=24, payload=ONE_BIT_PAYLOAD,
                       encoding="one_bit", confidence=None)
        raster = decode_mask_raster(mask)
        self.assertEqual(raster, one_bit_raster())
        self.assertEqual(hashlib.sha256(raster).hexdigest(), ONE_BIT_SHA256)

    def test_wrong_marker_is_loud(self):
        mask = SamMask(height=16, width=24, payload="~!!!!0CA",
                       encoding="one_bit", confidence=None)
        with self.assertRaises(SamShapeError):
            decode_mask_raster(mask)

    def test_truncated_payload_is_loud(self):
        mask = SamMask(height=16, width=24, payload="!!!!",
                       encoding="one_bit", confidence=None)
        with self.assertRaises(SamShapeError):
            decode_mask_raster(mask)

    def test_unsupported_encoding_is_loud(self):
        mask = SamMask(height=4, width=4, payload="~AAAA",
                       encoding="zip", confidence=None)
        with self.assertRaises(SamShapeError):
            decode_mask_raster(mask)


class MaskStatsTests(unittest.TestCase):
    def test_stats_on_synthetic_raster(self):
        stats = mask_stats(one_bit_raster(), 24, 16)
        self.assertEqual(stats.set_pixels, 148)
        self.assertEqual(stats.bbox, (4, 3, 19, 12))
        self.assertEqual(round(stats.aspect, 3), 1.6)
        self.assertEqual(round(stats.fill, 3), round(148 / 160, 3))
        self.assertEqual(round(stats.coverage, 3), round(148 / 384, 3))

    def test_empty_raster(self):
        stats = mask_stats(bytes(24 * 16), 24, 16)
        self.assertEqual(stats.set_pixels, 0)
        self.assertIsNone(stats.bbox)
        self.assertIsNone(stats.aspect)

    def test_length_mismatch_is_loud(self):
        with self.assertRaises(SamShapeError):
            mask_stats(bytes(10), 24, 16)


class MaskedColourTests(unittest.TestCase):
    def _photo(self, rgb, w=24, h=16):
        return bytes(rgb) * (w * h), w, h

    def test_red_object_measures_red(self):
        photo_rgb, w, h = self._photo((178, 34, 40))
        box = SamBox(x1=0, y1=0, x2=23, y2=15, w=24, h=16, confidence=None)
        sample = masked_colour(one_bit_raster(), 24, 16, box, photo_rgb, w, h)
        self.assertEqual(sample["pixels"], 148)
        self.assertEqual(sample["red_fraction"], 1.0)
        self.assertEqual(sample["median_rgb"], (178, 34, 40))

    def test_black_object_does_not_measure_red(self):
        # The B1 failure, inverted: the same silhouette in black must
        # report ~0 red share from its own pixels.
        photo_rgb, w, h = self._photo((22, 22, 24))
        box = SamBox(x1=0, y1=0, x2=23, y2=15, w=24, h=16, confidence=None)
        sample = masked_colour(one_bit_raster(), 24, 16, box, photo_rgb, w, h)
        self.assertEqual(sample["red_fraction"], 0.0)

    def test_background_pixels_are_not_sampled(self):
        # Red background, black object: sampling only under the mask
        # must still say the object is not red.
        w, h = 24, 16
        buf = bytearray()
        raster = one_bit_raster()
        for i in range(w * h):
            buf.extend((200, 30, 30) if not raster[i] else (20, 20, 20))
        box = SamBox(x1=0, y1=0, x2=23, y2=15, w=24, h=16, confidence=None)
        sample = masked_colour(raster, 24, 16, box, bytes(buf), w, h)
        self.assertEqual(sample["red_fraction"], 0.0)
        self.assertEqual(sample["median_rgb"], (20, 20, 20))


if __name__ == "__main__":
    unittest.main()
