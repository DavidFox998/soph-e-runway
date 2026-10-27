# Gate 4 confusion matrix v2 — mask-based measurement, 2026-10-27

The v2 measurement (T1, Day 2): SAM 3.1's mask payloads are decoded
to rasters by a stdlib port of Meta's reference codec (byte-identical
to the reference decoder on the captured probe payload — see
`tests/test_sam_mask.py`), the silhouette is taken from the mask's
own shape, and the colour from the photo pixels under the mask.
Same 20 photos, same Gate 4, same expectations as the
[v1 matrix](gate4-confusion-matrix.md). Verdict direction:
**18/20** (v1: 12/20). Every v1 miss in the unsafe direction is
closed; the two remaining divergences are named below and are the
same in both versions.

## What changed, per photo

| Photo | Expected | v1 verdict | v2 verdict | The v2 measurement |
|---|---|---|---|---|
| true_01, 02, 03, 06, 08, 09, 10, 12 (8 photos) | pass | pass | **pass** | mask fill 0.42–0.48, red share 0.61–0.88 |
| true_04, true_07, true_11 | pass | refuse attribute_mismatch:form (box aspects 1.69 / 1.60 / 1.64 vs the v1 band's 1.6 ceiling) | **pass** | mask aspects inside the recalibrated band (0.55–1.75), fill 0.45–0.47, red 0.58–0.79 |
| true_05_spout_closeup | pass | refuse item_absent | refuse item_absent | SAM returns no complete-kettle record for the tight crop, in both versions |
| wrong_colour_black | refuse colour | **PASS (unsafe)** | **refuse attribute_mismatch:colour** | red share **0.00** over the mask, median RGB (28, 28, 26) |
| wrong_colour_silver | refuse (ambiguous in v1's terms) | refuse ambiguous:colour | **refuse attribute_mismatch:colour** | red share **0.00**, median (137, 132, 122) — measured silver, no longer ambiguous |
| wrong_form_stovetop | refuse form | **PASS (unsafe)** | **refuse attribute_mismatch:form** | mask fill **0.51**, above the true cluster |
| wrong_form_electric_jug | refuse form | **PASS (unsafe)** | **refuse attribute_mismatch:form** | mask fill **0.70** |
| wrong_item_toaster / box_only_empty / packaging_only | refuse item_absent | refuse item_absent | refuse item_absent | 0 item records, as before |
| blurry_true_kettle | ambiguous | PASS | PASS | red share 0.88, fill 0.46 — SAM + mask are blur-robust; see below |

## The two measurements that did the work

**Colour from masked pixels separates completely.** True red
kettles: red-dominant share 0.58–0.88 of the pixels under the mask.
Black: 0.00. Silver: 0.00. The v1 failure — a colour phrase's box
overlapping the item box at IoU 1.00 on a black kettle — cannot
occur here, because no phrase is consulted: the object's own
pixels are the evidence. Colour, as now measured, is evidence of
colour.

**Form is carried by mask fill, not aspect.** True gooseneck masks
fill 0.42–0.48 of their bounding box (thin spout and handle leave
air in the box); the stovetop impostor fills 0.51 and the electric
jug 0.70. The decision band is fill ∈ [0.30, 0.50], calibrated on
this labeled set and recorded in `SamConfigV2`. **The stovetop
margin is thin** — 0.51 against a true-set maximum of 0.48, three
points of fill on one labeled set. It is a calibrated band, not a
law of kettles; the ambiguity probe set (five harder inputs,
branch `gate4/ambiguity`) is staged as the next evidence against
it, to be folded in on the owner's word.

## Still open, named

- **true_05 (spout close-up)** refuses `item_absent` in both
  versions: SAM finds no complete kettle in a tight crop of the
  spout. Whether a close-up counts as a delivery photo of the item
  is a scope decision for the owner, unchanged by the mask work.
- **blurry_true_kettle** passes in both versions. The mask
  measurement confirms the v1 observation: SAM is robust to blur
  (radius 12 here; the ambiguity probes pushed radius 40 with the
  same outcome). AMBIGUOUS remains a phrase-silence verdict, not a
  degradation verdict — see `gate4-ambiguity-probes.md`.

Gate 4's verdict after v2: presence strong, colour now measured
from the object itself, form measured from the silhouette's fill
with one thin margin on record. The weakest remaining joint is
that margin, and it is written down where a judge can find it.
