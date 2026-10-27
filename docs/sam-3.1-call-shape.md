# SAM 3.1 call shape — verified facts before any probe

Q2 invariant: **no probe call until these facts are written down with
sources.** Established 2026-10-26 (Day 0 evening) from Meta's own
documentation and Meta's protocol repository. Anything not established
here is marked NOT ESTABLISHED and is what the probe variants test.

## 1. Endpoint, auth, model ID

- SAM 3.1 is served on the Meta Model API and shares its envelope, keys
  and billing with every other Meta model. Base URL
  `https://api.meta.ai/v1`, OpenAI-compatible clients, Bearer API key
  (the same key as Muse Spark). Called through the **Responses API**
  (`responses.create`), streamed.
- Exact model ID: **`sam-3.1`** (confirmed live in this account's model
  list, 2026-10-26).
- Sources:
  - https://developer.meta.com/ai/models/sam-3-1/ (model page:
    "shares its envelope, keys, docs and billing"; quickstart =
    OpenAI-compatible client pointed at Meta Model API)
  - This repo's Appendix A notes (live `/v1/models` list, 2026-10-26)

## 2. Request schema

- One request = one short concept phrase per request (e.g. `person`,
  `red bicycle`) with one image or video. The hosted interface
  currently accepts **text prompts only** (visual prompts are native
  only).
- Worked example (official-guide example, for video): Responses input
  is a message whose content parts are
  `{"type": "input_text", "text": "<phrase>"}` plus
  `{"type": "input_video", "video_url": "<url>"}`; `stream: true`;
  `metadata` may carry `{"mask_encoding": "one_bit"}`.
- For images, the SAM protocol doc names the phrase field `input_text`
  and defines object prompts in the same token vocabulary (box/point
  tokens, image = frame 0). The image content part follows the
  Responses convention (`input_image`). Whether the hosted endpoint
  takes an image **URL**, a **base64 data URL**, or both is
  NOT ESTABLISHED from the docs read so far — probe variants A (URL)
  and B (base64 data URL) test exactly this.
- Request metadata defined by the protocol doc:
  `include_confidence: "true"` asks for per-record confidences;
  `propagation_direction` (`both` default / `forward` / `backward`)
  is video-only.
- Sources:
  - https://github.com/meta-models/meta-sam/blob/main/protocol/sam3.md
    (§ "SAM API input", § "SAM API output")
  - https://learnopencv.com/sam-3-whats-new/ (§ "SAM 3.1 Through Meta
    Model API" — worked example quoting the official segmentation
    guide at dev.meta.ai; secondary source, probe confirms)

## 3. Response schema

- Output arrives as **special-token text in one Responses
  `output_text` lane**, one line per frame:
  `<Nf>` then per object: bare integer object id, one `box` token,
  one `mask` token.
- Box token: `x1,y1,x2,y2` integer source-media coordinates with
  **inclusive** x2/y2 (normalized half-open right = x2+1), plus `w`,`h`
  source dimensions; optional confidence `c` (0..1).
- Mask token: `x=0`, `y=0`, `data=H,W,<payload>`; optional `c`.
  An empty lane (zero matches) is a **valid completed response**.
- Mask payload encoding: **base85 text, not base64**. First char is
  the marker: `~` = lossless (the API default), `!` = one_bit. Then a
  five-character base85 length prefix and an arithmetic-coded body
  that decodes to a row-major binary raster of exactly W*H bytes
  (lossless thresholds coverage bytes at 129). The alphabet excludes
  `, ; < > | " \` so the tuple and the closing `|>` are unambiguous.
  Full raster decoding is specified only by Meta's reference codec
  (`meta-sam-parser`, PyPI); our stdlib-only adapter validates the
  envelope and does not decode rasters in v1 (see sam.py).
- Streaming outcomes: completed / incomplete / refusal / error are
  distinct terminal states of the Responses stream; a refusal content
  part is a terminal typed failure, not an empty result.
- Sources:
  - https://github.com/meta-models/meta-sam/blob/main/protocol/sam3.md
    (§§ "SAM API output", "Mask payload encoding", "Streaming and
    outcomes")
  - Conformance cases (real captured API streams):
    https://github.com/meta-models/meta-sam/tree/main/conformance/cases

## 4. Error shape

- Responses API error envelope (OpenAI-compatible). Documented case:
  **`404 model_not_found`** for teams that cannot access the requested
  model — an API key does not guarantee access to every model.
- SAM stream-level failures are typed outcomes (see §3), separate
  from HTTP errors: a probe must record both layers.
- Source: https://learnopencv.com/sam-3-whats-new/ citing Meta's
  Authentication docs at dev.meta.ai (secondary; probe confirms the
  envelope on any non-2xx).

## 5. Pricing and limits

- **Images: $2.50 per 1,000 images. Video: $0.20 per 1,000 frames.**
  (One concept per request; different concepts are separate requests.)
- Video limits: 15,000 input frames, **16 tracked objects per frame**
  (hosted cap); MP4/MOV with H.264/H.265/MPEG-4 (no WebM/VP9).
- Sources:
  - https://developer.meta.com/ai/models/sam-3-1/ (pricing table:
    model listed as `sam-3-1`)
  - https://learnopencv.com/sam-3-whats-new/ citing Meta's
    segmentation limits at dev.meta.ai

## Status — PROBE VERIFIED 2026-10-26 evening

Live probes ran against this account's key (artifacts:
`artifacts/probe_A_20261027T014808Z.json`,
`artifacts/probe_B_20261027T014808Z.json`):

- **Both image transports work.** Variant A (`input_image` with a
  fetchable `image_url`) and variant B (`image_url` as a base64 data
  URL) each returned HTTP 200 with the full Responses event lifecycle
  (`response.created` → `response.output_text.done` →
  `response.completed`, 9 event types). Results were byte-identical:
  one record for the probe image, box (237, 150)–(1742, 1155) in
  1920×1280 media, confidence 0.9766 (the `include_confidence`
  metadata works), mask raster 684×1024, lossless encoding.
  **Variant B is the build default** — delivery photos need no
  hosting.
- The committed parser (`src/runway/sam.py`) accepted the live wire
  text with no shape errors. Observed: the mask raster dimensions
  (684×1024) are the mask's own, not the box's — recorded as seen,
  not interpreted.
- Fact 4 (error envelope) remains documented-only; no probe failed,
  so no live error body has been captured yet.
- Cost of the two probes: 2 images ≈ $0.005 against the credits.

Remaining Gate 4 work (its own stage): the 12-true / 8-impostor
photo set and the adapter confusion matrix over real delivery
photos; mask raster decoding (for pixel-level color) stays out of
the stdlib build — `matte_red` measures via the color-phrase
overlap, and anything undecidable reports AMBIGUOUS.
