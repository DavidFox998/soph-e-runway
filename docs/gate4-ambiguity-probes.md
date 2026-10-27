# Gate 4 ambiguity probes — measured 2026-10-27

Purpose: the AMBIGUOUS verdict existed in code but had never been
exercised by a degraded input (the v1 set's blurry photo, radius 12,
sailed through at 0.961). These five probes are genuinely hard
inputs, built to give the third verdict its chance to fire — or to
measure SAM 3.1's robustness trying. Photos and per-photo
measurements: `assets/gate4/ambiguity/` (two generated scenes, three
programmatic degradations of v1 true photos; all labeled in
`measurements.json`'s companion notes below).

| Probe | Construction | Present (conf) | Form | Colour | Gate 4 verdict |
|---|---|---|---|---|---|
| amb_half_frame | true_01 cropped to left 42% — kettle half out of frame | ✓ 0.961 | ✓ aspect 0.76 | ✓ IoU 1.00 | **pass** |
| amb_occluded_flap | generated: kettle inside its box, mostly hidden behind the flap | ✗ 0 records | ambiguous (no anchor) | ambiguous (no anchor) | refuse item_absent |
| amb_fogged_lens | true_02 blended 55% toward white + blur 2.5 | ✓ 0.961 | ✓ 1.54 | ✓ IoU 1.00 | **pass** |
| amb_extreme_blur | true_03, Gaussian blur radius 40 | ✓ 0.668 | ✓ 1.38 | ✓ IoU 0.78 | **pass** |
| amb_very_dark | generated: doorstep at night, distant porch bulb | ✓ 0.949 | ✓ 1.44 | ✓ IoU 1.00 | **pass** |

## What fired, and what did not

**Degradation produced zero AMBIGUOUS verdicts (0/5).** Half-frame,
fog, near-darkness and a radius-40 blur all measured confidently.
The blur did register in the numbers — presence confidence fell to
0.668 and the colour-phrase IoU to 0.78 — but nothing crossed a
decision boundary, because the measurement layer has no boundary
there to cross: a record either exists or it does not.

**The one refusal came through presence, not ambiguity.** The
occluded kettle returned zero item records, so its form and colour
were indeed `ambiguous` inside the measurement — but Gate 4 checks
presence first and exits `item_absent`. When the item cannot be
found at all, `item_absent` is arguably the honest refusal; the
ambiguity underneath it is real but unreachable on that path.

**Where AMBIGUOUS has actually fired:** exactly once so far — the
v1 matrix's silver kettle, where the item was present and the
colour phrase returned zero records (`ambiguous:colour`). Given the
gate's check order, that is the only shape ambiguity can take
today: an attribute phrase falling silent while the item stands.
Form ambiguity cannot surface at Gate 4, because form is ambiguous
only when there is no item record — and that case already refused
as `item_absent` one check earlier.

## Conclusion, as measured

SAM 3.1 does not do undecidable-by-degradation; it degrades
gracefully and keeps answering. The third verdict is real, fired,
and narrow: it names *phrase silence on a present item*, not
*uncertainty*. If Gate 4 ever needs a true "cannot tell" for
degraded photos, it will have to come from a confidence or
agreement boundary in the measurement layer — a design decision,
with this set as its evidence — not from waiting for SAM to shrug.
These five photos join the set as hard inputs for the Day 2 mask
decode, which gets its colour from masked pixels and will meet
the fog and the dark on pixel evidence instead of phrases.
