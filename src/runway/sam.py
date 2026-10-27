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
