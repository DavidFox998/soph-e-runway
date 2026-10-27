"""SAM 3.1 adapter (Q2 step 3): wire text in, Gate 4 measurement out.

Parses ONLY the schema established in docs/sam-3.1-call-shape.md
(Meta's normative protocol doc). Anything off-schema raises
SamShapeError — loudly, never silently.

measure() returns per-attribute measurements, not verdicts:

- `present` — records exist for the item concept phrase. An empty lane
  is a valid completed response, so zero records is a MEASURED
  `present = False`, not an error.
- `gooseneck_silhouette` — a box-geometry proxy (aspect band on the
  best record's box), labeled as a proxy in its detail. The mask
  raster codec is Meta's arithmetic-coded base85; decoding it is not
  in this stdlib build, and this measure does not pretend otherwise.
- `matte_red` — a second concept prompt ("matte red gooseneck
  kettle"): a color record whose box overlaps the item box is
  measured evidence for the color; NO color records at all is
  genuinely undecidable (wrong color, or phrase sensitivity), so it
  reports AMBIGUOUS — and Gate 4 refuses AMBIGUOUS, never guesses.

`raw_ref` is the SHA-256 of the raw response text, so a measurement
can be chained to the exact artifact it was derived from.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

BASE85_ALPHABET = set(
    "!#$%&'()*+-./0123456789:=?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`"
    "abcdefghijklmnopqrstuvwxyz{"
)
TOKEN_RE = re.compile(r"<\|([^|]*)\|>")
FRAME_RE = re.compile(r"<(\d+)f[^>]*>")
ID_RE = re.compile(r"\d+")


class SamShapeError(Exception):
    """The response does not match the documented schema."""


@dataclass
class SamBox:
    x1: int
    y1: int
    x2: int
    y2: int
    w: int
    h: int
    confidence: float | None = None

    @property
    def width(self) -> int:
        return self.x2 - self.x1 + 1  # wire x2 is inclusive

    @property
    def height(self) -> int:
        return self.y2 - self.y1 + 1

    def iou(self, other: "SamBox") -> float:
        ix = max(0, min(self.x2, other.x2) - max(self.x1, other.x1) + 1)
        iy = max(0, min(self.y2, other.y2) - max(self.y1, other.y1) + 1)
        inter = ix * iy
        union = self.width * self.height + other.width * other.height - inter
        return inter / union if union > 0 else 0.0


@dataclass
class SamMask:
    height: int
    width: int
    payload: str
    encoding: str  # "lossless" (~) | "one_bit" (!)
    confidence: float | None = None


@dataclass
class SamRecord:
    object_id: str
    box: SamBox
    mask: SamMask


def _fields(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in body.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
        else:
            out[part] = ""
    return out


def _confidence(fields: dict[str, str]) -> float | None:
    raw = fields.get("c")
    if raw is None:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None  # documented: invalid c is ignored, record kept
    if val != val or val in (float("inf"), float("-inf")):
        return None
    if not (0.0 <= val <= 1.0):
        return None
    return 0.0 if val == 0 else val


def _int(fields: dict[str, str], key: str, ctx: str) -> int:
    raw = fields.get(key)
    if raw is None:
        raise SamShapeError(f"{ctx}: missing required field {key!r}")
    try:
        return int(raw)
    except ValueError:
        raise SamShapeError(f"{ctx}: field {key!r} is not an integer: {raw!r}") from None


def _parse_mask(fields: dict[str, str], ctx: str) -> SamMask:
    if fields.get("x") != "0" or fields.get("y") != "0":
        raise SamShapeError(f"{ctx}: mask token must carry x=0, y=0")
    data = fields.get("data")
    if data is None:
        raise SamShapeError(f"{ctx}: mask token missing data")
    parts = data.split(",", 2)
    if len(parts) != 3:
        raise SamShapeError(f"{ctx}: mask data is not H,W,payload")
    try:
        h, w = int(parts[0]), int(parts[1])
    except ValueError:
        raise SamShapeError(f"{ctx}: mask dims not integers") from None
    payload = parts[2]
    if not payload or payload[0] not in ("~", "!"):
        raise SamShapeError(f"{ctx}: payload lacks its encoding marker")
    encoding = "lossless" if payload[0] == "~" else "one_bit"
    body = payload[1:]
    if len(body) < 5 or any(ch not in BASE85_ALPHABET for ch in body):
        raise SamShapeError(f"{ctx}: payload outside the base85 alphabet")
    return SamMask(height=h, width=w, payload=payload, encoding=encoding,
                   confidence=_confidence(fields))


def parse_sam_text(text: str) -> list[SamRecord]:
    """Parse one output_text lane into records. Empty text = zero
    matches (valid). Malformed records raise SamShapeError."""
    records: list[SamRecord] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = FRAME_RE.match(line)
        if not m:
            raise SamShapeError(f"line lacks a frame marker: {line[:40]!r}")
        rest = line[m.end():]
        pos = 0
        while pos < len(rest):
            if rest[pos] == ",":
                pos += 1
                continue
            idm = ID_RE.match(rest, pos)
            if not idm:
                raise SamShapeError(f"expected object id at {rest[pos:pos + 20]!r}")
            object_id = idm.group(0)
            pos = idm.end()
            tokens: list[tuple[str, dict[str, str]]] = []
            while True:
                tm = TOKEN_RE.match(rest, pos)
                if not tm:
                    break
                body = tm.group(1)
                name = body.split(";", 1)[0]
                tokens.append((name, _fields(body)))
                pos = tm.end()
            boxes = [f for n, f in tokens if n == "box"]
            masks = [f for n, f in tokens if n == "mask"]
            if len(boxes) != 1 or len(masks) != 1:
                raise SamShapeError(
                    f"record {object_id}: needs exactly one box and one mask token"
                )
            bf = boxes[0]
            box = SamBox(
                x1=_int(bf, "x1", "box"), y1=_int(bf, "y1", "box"),
                x2=_int(bf, "x2", "box"), y2=_int(bf, "y2", "box"),
                w=_int(bf, "w", "box"), h=_int(bf, "h", "box"),
                confidence=_confidence(bf),
            )
            if not (0 <= box.x1 <= box.x2 < box.w and 0 <= box.y1 <= box.y2 < box.h):
                raise SamShapeError(f"record {object_id}: box outside its media dims")
            records.append(SamRecord(
                object_id=object_id, box=box,
                mask=_parse_mask(masks[0], f"record {object_id}"),
            ))
    return records


@dataclass
class AttributeMeasure:
    state: str  # "measured" | "ambiguous"
    present: bool | None
    confidence: float | None
    detail: str


@dataclass
class Gate4Measurement:
    attributes: dict[str, AttributeMeasure]
    raw_ref: str
    records: int


@dataclass
class SamConfig:
    item_phrase: str = "gooseneck kettle"
    color_phrase: str = "matte red gooseneck kettle"
    aspect_band: tuple[float, float] = (0.5, 1.6)
    overlap_min: float = 0.5


def _best(records: list[SamRecord]) -> SamRecord | None:
    if not records:
        return None
    return max(records, key=lambda r: r.box.confidence or 0.0)


def measure_from_texts(item_text: str, color_text: str,
                       cfg: SamConfig = SamConfig()) -> Gate4Measurement:
    """The pure core of measure(): two raw response lanes in, the
    Gate 4 measurement out. Testable without any network."""
    item_records = parse_sam_text(item_text)
    color_records = parse_sam_text(color_text)
    raw_ref = hashlib.sha256((item_text + "\n" + color_text).encode()).hexdigest()

    attrs: dict[str, AttributeMeasure] = {}
    best = _best(item_records)
    if best is None:
        attrs["present"] = AttributeMeasure(
            "measured", False, None, "empty lane: zero records for the item phrase")
        attrs["gooseneck_silhouette"] = AttributeMeasure(
            "ambiguous", None, None, "no item record to measure")
        attrs["matte_red"] = AttributeMeasure(
            "ambiguous", None, None, "no item record to anchor color evidence")
        return Gate4Measurement(attrs, raw_ref, 0)

    attrs["present"] = AttributeMeasure(
        "measured", True, best.box.confidence,
        f"{len(item_records)} record(s) for {cfg.item_phrase!r}")
    aspect = best.box.width / best.box.height
    lo, hi = cfg.aspect_band
    attrs["gooseneck_silhouette"] = AttributeMeasure(
        "measured", lo <= aspect <= hi, best.box.confidence,
        f"box-geometry proxy: aspect {aspect:.2f} vs band {lo}-{hi} "
        "(mask raster decode pending)")
    if not color_records:
        attrs["matte_red"] = AttributeMeasure(
            "ambiguous", None, None,
            "zero records for the color phrase: wrong color or phrase "
            "sensitivity — undecidable, refuses")
    else:
        cbest = _best(color_records)
        overlap = max(cbest.box.iou(r.box) for r in item_records)
        attrs["matte_red"] = AttributeMeasure(
            "measured", overlap >= cfg.overlap_min, cbest.box.confidence,
            f"color-phrase box IoU {overlap:.2f} vs item box (min {cfg.overlap_min})")
    return Gate4Measurement(attrs, raw_ref, len(item_records))


def responses_transport(image_b64: str, phrase: str, *,
                        variant: str = "B") -> str:
    """One live SAM call via the Responses API; returns the raw
    output_text lane. Uses `requests` when available, else urllib.
    The API key comes from META_API_KEY; it is never stored."""
    import base64 as _b64
    import json as _json
    import os as _os
    import urllib.request as _u

    key = _os.environ.get("META_API_KEY")
    if not key:
        raise SamShapeError("META_API_KEY is not set; SAM cannot be called")
    image_part = {
        "type": "input_image",
        "image_url": f"data:image/jpeg;base64,{image_b64}",
    }
    body = {
        "model": "sam-3.1",
        "input": [{
            "type": "message", "role": "user",
            "content": [
                {"type": "input_text", "text": phrase},
                image_part,
            ],
        }],
        "stream": True,
        "metadata": {"include_confidence": "true"},
    }
    req = _u.Request("https://api.meta.ai/v1/responses", method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with _u.urlopen(req, data=_json.dumps(body).encode(), timeout=180) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as exc:
        raise SamShapeError(f"SAM call failed: {exc}") from exc
    text_parts: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            ev = _json.loads(line[5:].strip())
        except ValueError:
            continue
        if ev.get("type") == "response.output_text.delta":
            text_parts.append(ev.get("delta", ""))
        elif ev.get("type") == "response.output_text.done":
            text_parts = [ev.get("text", "")]
    return "".join(text_parts)


def measure(image_b64: str, cfg: SamConfig = SamConfig(),
            transport=responses_transport) -> Gate4Measurement:
    """Two concept calls (item phrase, color phrase) -> one Gate 4
    measurement. Transport is injectable so tests never touch the
    network."""
    item_text = transport(image_b64, cfg.item_phrase)
    color_text = transport(image_b64, cfg.color_phrase)
    return measure_from_texts(item_text, color_text, cfg)


# ---------------------------------------------------------------------
# Mask raster decoding + the v2 measurement (T1, Day 2).
#
# The v1 measurement read colour from a phrase and form from a box.
# B1's matrix measured what that costs: a black kettle passed the
# colour check because the colour phrase's box overlapped the item
# box (co-location is not colour), and wrong-form impostors sat
# inside the box-aspect band. The mask is the measurement: SAM's
# payload decodes to a binary raster that is BOX-LOCAL (it maps onto
# the record's box in source-media coordinates — bounds semantics
# per Meta's reference parser), the silhouette comes from the
# raster's own shape, and the colour from the photo pixels under
# the mask.
#
# The decoders below are a faithful stdlib port of Meta's reference
# codec (meta-sam-parser, _mask_codec.py): base85 envelope with a
# 5-digit length prefix, a range coder, and two raster schemes —
# one_bit ("!": adaptive binary contexts over a padded raster) and
# lossless ("~": predictor residuals under order-0/1/2 models,
# coverage bytes thresholded at 129). Malformed payloads raise
# SamShapeError, loudly, like everything else in this module.
# ---------------------------------------------------------------------

_B85_EXCLUDED = frozenset({chr(34), chr(92), ",", ";", "<", ">", "|"})
_B85_ALPHABET = "".join(
    chr(c) for c in range(0x21, 0x7F) if chr(c) not in _B85_EXCLUDED
)
_B85_VALUE = {ch: i for i, ch in enumerate(_B85_ALPHABET)}
_RC_TOP = 1 << 24
_RC_BOTTOM = 1 << 16


def _b85_digit(ch: str) -> int:
    v = _B85_VALUE.get(ch, -1)
    if v < 0 or v >= 85:
        raise SamShapeError(f"mask payload: invalid base85 character {ch!r}")
    return v


def _b85_pack(data: bytes) -> str:
    length = len(data)
    rem = length
    prefix = [""] * 5
    for i in range(4, -1, -1):
        prefix[i] = _B85_ALPHABET[rem % 85]
        rem //= 85
    if rem:
        raise SamShapeError("mask payload too large for its prefix")
    out = list(prefix)
    off = 0
    full = length - (length % 4)
    while off < full:
        value = ((data[off] << 24) | (data[off + 1] << 16)
                 | (data[off + 2] << 8) | data[off + 3])
        digits = [0] * 5
        for i in range(4, -1, -1):
            digits[i] = value % 85
            value = (value - digits[i]) // 85
        out.extend(_B85_ALPHABET[d] for d in digits)
        off += 4
    remainder = length - off
    if remainder > 0:
        value = 0
        for i in range(4):
            value = (value << 8) | (data[off + i] if i < remainder else 0)
        digits = [0] * 5
        for i in range(4, -1, -1):
            digits[i] = value % 85
            value = (value - digits[i]) // 85
        out.extend(_B85_ALPHABET[digits[i]] for i in range(remainder + 1))
    return "".join(out)


def _b85_unpack(payload: str) -> bytes:
    """payload = the text AFTER the ~ / ! marker."""
    if len(payload) < 5:
        raise SamShapeError("mask payload missing its length prefix")
    length = 0
    for ch in payload[:5]:
        length = length * 85 + _b85_digit(ch)
    remainder = length % 4
    expected = 5 + (length // 4) * 5 + (0 if remainder == 0 else remainder + 1)
    if len(payload) != expected:
        raise SamShapeError("mask payload length does not match its prefix")
    out = bytearray(length)
    src = 5
    dst = 0
    full = length - remainder
    while dst < full:
        value = 0
        for i in range(5):
            value = value * 85 + _b85_digit(payload[src + i])
        if value > 0xFFFFFFFF:
            raise SamShapeError("mask payload group out of range")
        src += 5
        out[dst] = (value >> 24) & 0xFF
        out[dst + 1] = (value >> 16) & 0xFF
        out[dst + 2] = (value >> 8) & 0xFF
        out[dst + 3] = value & 0xFF
        dst += 4
    if remainder > 0:
        value = 0
        for i in range(5):
            value = value * 85 + (
                _b85_digit(payload[src + i]) if i < remainder + 1 else 84)
        if value > 0xFFFFFFFF:
            raise SamShapeError("mask payload tail out of range")
        for i in range(remainder):
            out[dst + i] = (value >> (24 - i * 8)) & 0xFF
    if _b85_pack(bytes(out)) != payload:
        raise SamShapeError("mask payload is not in canonical form")
    return bytes(out)


class _RangeDecoder:
    def __init__(self, data: bytes):
        if len(data) < 4:
            raise SamShapeError("mask payload missing its finalization")
        self._input = data
        self._pos = 0
        self._low = 0
        self._range = 0xFFFFFFFF
        self._code = 0
        self._scaled = 0
        for _ in range(4):
            self._code = ((self._code << 8) | self._read()) & 0xFFFFFFFF

    def _read(self) -> int:
        if self._pos >= len(self._input):
            raise SamShapeError("mask payload ended before decoding completed")
        v = self._input[self._pos]
        self._pos += 1
        return v

    def frequency(self, total: int) -> int:
        self._scaled = self._range // total
        if self._scaled == 0:
            raise SamShapeError("mask payload has invalid coding state")
        value = ((self._code - self._low) & 0xFFFFFFFF) // self._scaled
        return total - 1 if value >= total else value

    def decode(self, cumulative: int, frequency: int) -> None:
        self._low = (self._low + self._scaled * cumulative) & 0xFFFFFFFF
        self._range = self._scaled * frequency
        while True:
            if ((self._low ^ ((self._low + self._range) & 0xFFFFFFFF))
                    & 0xFFFFFFFF) < _RC_TOP:
                pass
            elif self._range < _RC_BOTTOM:
                self._range = (-self._low) & (_RC_BOTTOM - 1)
            else:
                break
            self._code = ((self._code << 8) | self._read()) & 0xFFFFFFFF
            self._low = (self._low << 8) & 0xFFFFFFFF
            self._range = (self._range << 8) & 0xFFFFFFFF


def _ctx_at(raster: bytearray, pos: int, prior: int, earlier: int) -> int:
    return (
        raster[pos - 1]
        | (raster[pos - 2] << 1)
        | (raster[prior - 2] << 2)
        | (raster[prior - 1] << 3)
        | (raster[prior] << 4)
        | (raster[prior + 1] << 5)
        | (raster[prior + 2] << 6)
        | (raster[earlier - 2] << 7)
        | (raster[earlier - 1] << 8)
        | (raster[earlier] << 9)
        | (raster[earlier + 1] << 10)
        | (raster[earlier + 2] << 11)
    )


def _ctx_update(counts: list, offset: int, bit: int) -> None:
    counts[offset + bit] = (counts[offset + bit] + 14) & 0xFFFF
    if counts[offset] + counts[offset + 1] >= 4096:
        counts[offset] = (counts[offset] >> 1) or 1
        counts[offset + 1] = (counts[offset + 1] >> 1) or 1


def _decode_one_bit(payload: str, width: int, height: int) -> bytes:
    decoder = _RangeDecoder(_b85_unpack(payload[1:]))
    counts = [1] * ((1 << 12) * 2)
    padded_w = width + 4
    padded = bytearray(padded_w * (height + 2))
    out = bytearray(width * height)
    for y in range(height):
        row = (y + 2) * padded_w + 2
        for x in range(width):
            pos = row + x
            ctx = _ctx_at(padded, pos, pos - padded_w, pos - 2 * padded_w)
            off = ctx << 1
            zero, one = counts[off], counts[off + 1]
            value = decoder.frequency(zero + one)
            bit = 0 if value < zero else 1
            if bit == 0:
                decoder.decode(0, zero)
            else:
                decoder.decode(zero, one)
            padded[pos] = bit
            out[y * width + x] = bit
            _ctx_update(counts, off, bit)
    return bytes(out)


def _paeth(left: int, up: int, upper_left: int) -> int:
    est = left + up - upper_left
    dl, du, dul = abs(est - left), abs(est - up), abs(est - upper_left)
    if dl <= du and dl <= dul:
        return left
    return up if du <= dul else upper_left


def _predict_byte(out: bytearray, off: int, x: int, y: int,
                  mode: int, width: int) -> int:
    if mode < 0 or mode >= 5:
        raise SamShapeError("lossless mask payload uses an invalid predictor")
    left = out[off - 1] if x > 0 else 0
    up = out[off - width] if y > 0 else 0
    if mode == 1:
        return up
    if mode == 2:
        return left
    if mode == 3:
        return (left + up) >> 1
    upper_left = out[off - width - 1] if x > 0 and y > 0 else 0
    if mode == 0:
        return _paeth(left, up, upper_left)
    if upper_left >= max(left, up):
        return min(left, up)
    if upper_left <= min(left, up):
        return max(left, up)
    return left + up - upper_left


def _decode_lossless(payload: str, width: int, height: int) -> bytes:
    packed = _b85_unpack(payload[1:])
    if len(packed) < 5:
        raise SamShapeError("lossless mask payload is truncated")
    selector = packed[0]
    decoder = _RangeDecoder(packed[1:])
    length = width * height
    output = bytearray(length)
    residuals = bytearray(length)
    zero_counts = [1] * 32
    order_one = [1] * (256 * 256)
    order_one_totals = [256] * 256
    order_zero = [2] * 256
    order_zero_total = 512
    order_two: dict = {}
    previous = 0
    for off in range(length):
        x = off % width
        y = off // width
        left = 1 if x == 0 else int(residuals[off - 1] == 0)
        up = 1 if y == 0 else int(residuals[off - width] == 0)
        ul = 1 if (x == 0 or y == 0) else int(residuals[off - width - 1] == 0)
        ur = 1 if (y == 0 or x == width - 1) else int(residuals[off - width + 1] == 0)
        zoff = (left | (up << 1) | (ul << 2) | (ur << 3)) << 1
        zero, nonzero = zero_counts[zoff], zero_counts[zoff + 1]
        zfreq = decoder.frequency(zero + nonzero)
        bit = 0 if zfreq < zero else 1
        decoder.decode(0 if bit == 0 else zero, zero if bit == 0 else nonzero)
        zero_counts[zoff + bit] = (zero_counts[zoff + bit] + 32) & 0xFFFFFFFF
        if zero_counts[zoff] + zero_counts[zoff + 1] >= 16384:
            zero_counts[zoff] = (zero_counts[zoff] >> 1) or 1
            zero_counts[zoff + 1] = (zero_counts[zoff + 1] >> 1) or 1
        symbol = 0
        if bit == 1:
            above = residuals[off - width] if off >= width else 0
            key = (previous << 8) | above
            second = order_two.get(key)
            if second is None:
                second = [0] * 257
                order_two[key] = second
            first_off = previous << 8
            excluded = second[0] + order_one[first_off] + order_zero[0]
            total = (second[256] + order_one_totals[previous]
                     + order_zero_total - excluded)
            target = decoder.frequency(total)
            cumulative = 0
            symbol = 1
            freq = second[1] + order_one[first_off + 1] + order_zero[1]
            while cumulative + freq <= target:
                cumulative += freq
                symbol += 1
                if symbol >= 256:
                    raise SamShapeError("lossless mask payload is malformed")
                freq = second[symbol] + order_one[first_off + symbol] + order_zero[symbol]
            decoder.decode(cumulative, freq)
            step2 = 14 * 44
            second[symbol] = (second[symbol] + step2) & 0xFFFF
            second[256] = (second[256] + step2) & 0xFFFF
            if second[256] >= 14 * 3584:
                tot = 0
                for v in range(256):
                    second[v] >>= 1
                    tot += second[v]
                second[256] = tot & 0xFFFF
            order_one[first_off + symbol] = (order_one[first_off + symbol] + 56) & 0xFFFF
            order_one_totals[previous] += 56
            if order_one_totals[previous] >= 8192:
                tot = 0
                for v in range(256):
                    scaled = (order_one[first_off + v] >> 1) or 1
                    order_one[first_off + v] = scaled
                    tot += scaled
                order_one_totals[previous] = tot
            order_zero[symbol] = (order_zero[symbol] + 32) & 0xFFFF
            order_zero_total += 32
            if order_zero_total >= 4096:
                tot = 0
                for v in range(256):
                    order_zero[v] >>= 1
                    tot += order_zero[v]
                order_zero_total = tot
        residuals[off] = symbol
        delta = -((symbol + 1) >> 1) if symbol & 1 else symbol >> 1
        output[off] = (_predict_byte(output, off, x, y, selector, width)
                       + delta) & 0xFF
        previous = symbol
    return bytes(1 if v >= 129 else 0 for v in output)


def decode_mask_raster(mask: SamMask) -> bytes:
    """Decode one mask token's payload to a binary raster of exactly
    mask.width * mask.height bytes (row-major, box-local grid)."""
    if mask.width <= 0 or mask.height <= 0:
        raise SamShapeError("mask dimensions must be positive")
    if mask.encoding == "lossless":
        if not mask.payload.startswith("~"):
            raise SamShapeError("lossless mask payload must start with ~")
        return _decode_lossless(mask.payload, mask.width, mask.height)
    if mask.encoding == "one_bit":
        if not mask.payload.startswith("!"):
            raise SamShapeError("one_bit mask payload must start with !")
        return _decode_one_bit(mask.payload, mask.width, mask.height)
    raise SamShapeError(f"unsupported mask encoding {mask.encoding!r}")


@dataclass
class MaskStats:
    set_pixels: int
    bbox: tuple | None      # (x1, y1, x2, y2) inclusive, raster coords
    aspect: float | None    # bbox width / height
    fill: float | None      # set pixels / bbox area
    coverage: float         # set pixels / raster area


def mask_stats(raster: bytes, width: int, height: int) -> MaskStats:
    total = width * height
    if len(raster) != total:
        raise SamShapeError("raster length does not match its dimensions")
    set_px = 0
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for i, v in enumerate(raster):
        if v:
            set_px += 1
            x, y = i % width, i // width
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
    if set_px == 0:
        return MaskStats(0, None, None, None, 0.0)
    bw, bh = max_x - min_x + 1, max_y - min_y + 1
    return MaskStats(set_px, (min_x, min_y, max_x, max_y),
                     bw / bh, set_px / (bw * bh), set_px / total)


def masked_colour(raster: bytes, mask_w: int, mask_h: int,
                  box: SamBox, photo_rgb: bytes,
                  photo_w: int, photo_h: int) -> dict:
    """Colour evidence from the photo pixels under the mask. The mask
    grid is box-local: mask pixel (mx, my) maps to the source pixel
    at the same relative position inside the record's box, scaled to
    the loaded photo's actual dimensions. Returns the share of set
    pixels that are red-dominant plus the median masked colour."""
    if len(photo_rgb) != photo_w * photo_h * 3:
        raise SamShapeError("photo pixel buffer does not match its dimensions")
    box_w = box.x2 - box.x1 + 1
    box_h = box.y2 - box.y1 + 1
    sx_scale = photo_w / box.w
    sy_scale = photo_h / box.h
    rs, gs, bs = [], [], []
    red = 0
    n = 0
    for i, v in enumerate(raster):
        if not v:
            continue
        mx, my = i % mask_w, i // mask_w
        sx = int((box.x1 + (mx + 0.5) * box_w / mask_w) * sx_scale)
        sy = int((box.y1 + (my + 0.5) * box_h / mask_h) * sy_scale)
        sx = min(max(sx, 0), photo_w - 1)
        sy = min(max(sy, 0), photo_h - 1)
        j = (sy * photo_w + sx) * 3
        r, g, b = photo_rgb[j], photo_rgb[j + 1], photo_rgb[j + 2]
        rs.append(r)
        gs.append(g)
        bs.append(b)
        n += 1
        if r >= 70 and r - g >= 24 and r - b >= 24:
            red += 1
    if n == 0:
        return {"pixels": 0, "red_fraction": None, "median_rgb": None}
    rs.sort()
    gs.sort()
    bs.sort()
    mid = n // 2
    return {"pixels": n, "red_fraction": red / n,
            "median_rgb": (rs[mid], gs[mid], bs[mid])}


@dataclass
class SamConfigV2:
    """Thresholds for the mask-based measurement, calibrated on the
    labeled v1 set (docs/gate4-confusion-matrix-v2.md): true
    gooseneck masks fill 0.42-0.48 of their bounding box while the
    two wrong-form impostors fill 0.51 and 0.70, so the fill BAND —
    not the aspect — carries the form decision (the stovetop margin
    is thin and is named as such in the matrix doc). Masked red
    share separates completely on the set: true kettles 0.58-0.88,
    black and silver 0.00."""
    aspect_band: tuple = (0.55, 1.75)
    fill_band: tuple = (0.30, 0.50)
    red_fraction_min: float = 0.50


def measure_v2(image_b64: str, pixel_source, cfg: SamConfigV2 = SamConfigV2(),
               transport=responses_transport,
               phrases: SamConfig = SamConfig()) -> Gate4Measurement:
    """The mask-based Gate 4 measurement. Same two concept calls as
    v1 (same raw_ref), but silhouette and colour are derived from
    the decoded mask of the best item record:
    - silhouette: mask bbox aspect in band AND mask fill inside the
      fill band (both computed from the raster, both in the detail).
    - colour: the red-dominant share of the photo pixels under the
      mask, via pixel_source(image_bytes, mask_w, mask_h, box) ->
      (photo_rgb, photo_w, photo_h). No pixel source, no mask, or a
      decode failure makes the affected attribute AMBIGUOUS with the
      reason named — never a silent fall back to the phrase test.
    """
    import base64 as _b64
    item_text = transport(image_b64, phrases.item_phrase)
    color_text = transport(image_b64, phrases.color_phrase)
    base = measure_from_texts(item_text, color_text, phrases)
    item_records = parse_sam_text(item_text)
    best = _best(item_records)
    attrs = {"present": base.attributes["present"]}
    if best is None:
        attrs["gooseneck_silhouette"] = AttributeMeasure(
            "ambiguous", None, None, "no item record: no mask to measure")
        attrs["matte_red"] = AttributeMeasure(
            "ambiguous", None, None, "no item record: no mask to sample")
        return Gate4Measurement(attrs, base.raw_ref, 0)
    try:
        raster = decode_mask_raster(best.mask)
    except SamShapeError as exc:
        attrs["gooseneck_silhouette"] = AttributeMeasure(
            "ambiguous", None, None, f"mask decode failed: {exc}")
        attrs["matte_red"] = AttributeMeasure(
            "ambiguous", None, None, f"mask decode failed: {exc}")
        return Gate4Measurement(attrs, base.raw_ref, len(item_records))
    stats = mask_stats(raster, best.mask.width, best.mask.height)
    lo, hi = cfg.aspect_band
    flo, fhi = cfg.fill_band
    sil_ok = (stats.aspect is not None and lo <= stats.aspect <= hi
              and stats.fill is not None and flo <= stats.fill <= fhi)
    attrs["gooseneck_silhouette"] = AttributeMeasure(
        "measured", sil_ok, best.box.confidence,
        f"mask silhouette: aspect {stats.aspect:.2f} vs band {lo}-{hi}, "
        f"fill {stats.fill:.2f} vs band {flo}-{fhi}, "
        f"coverage {stats.coverage:.2f} (mask raster, box-local)")
    if pixel_source is None:
        attrs["matte_red"] = AttributeMeasure(
            "ambiguous", None, None,
            "no pixel source wired: colour cannot be sampled from the mask")
        return Gate4Measurement(attrs, base.raw_ref, len(item_records))
    photo = pixel_source(_b64.b64decode(image_b64))
    if photo is None:
        attrs["matte_red"] = AttributeMeasure(
            "ambiguous", None, None, "pixel source returned no pixels")
        return Gate4Measurement(attrs, base.raw_ref, len(item_records))
    photo_rgb, photo_w, photo_h = photo
    sample = masked_colour(raster, best.mask.width, best.mask.height,
                           best.box, photo_rgb, photo_w, photo_h)
    if sample["red_fraction"] is None:
        attrs["matte_red"] = AttributeMeasure(
            "ambiguous", None, None, "mask has no set pixels to sample")
    else:
        attrs["matte_red"] = AttributeMeasure(
            "measured", sample["red_fraction"] >= cfg.red_fraction_min,
            best.box.confidence,
            f"masked-pixel colour: red-dominant share "
            f"{sample['red_fraction']:.2f} vs floor {cfg.red_fraction_min}, "
            f"median RGB {sample['median_rgb']} over {sample['pixels']} px")
    return Gate4Measurement(attrs, base.raw_ref, len(item_records))
