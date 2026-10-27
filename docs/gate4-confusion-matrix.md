# Gate 4 confusion matrix — photo set v1 (measured 2026-10-27)

Method: every photo in `assets/gate4/` (manifest: all 20 `generated`,
labeled per photo; the blurry one is a generated true photo with a
Gaussian blur, radius 12, applied programmatically) was run through
`runway.sam.measure` (SAM 3.1, two concept calls per photo: "gooseneck
kettle", "matte red gooseneck kettle") and then through the real
Gate 4 (`SamApiVerifier` + `gate_delivery`) against the demo mandate
(gooseneck kettle, colour = matte red, form = gooseneck). Per-photo
measurements, confidences and raw-response hashes are in
`assets/gate4/measurements.json`. Reported as measured — the misses
below are named, not explained away.

## The table

| Photo | Expected | Present | Form (aspect proxy) | Colour | Gate 4 verdict |
|---|---|---|---|---|---|
| true_01_front_white | pass | ✓ (0.969) | ✓ 1.57 | ✓ IoU 1.00 | **pass** |
| true_02_side_counter | pass | ✓ (0.969) | ✓ 1.54 | ✓ IoU 1.00 | **pass** |
| true_03_doorstep_box | pass | ✓ (0.973) | ✓ 1.43 | ✓ IoU 1.00 | **pass** |
| true_04_table_warm | pass | ✓ (0.969) | ✗ 1.69 | ✓ IoU 1.00 | refuse attribute_mismatch:form |
| true_05_spout_closeup | pass | ✗ 0 records | — | — | refuse item_absent |
| true_06_porch_openbox | pass | ✓ (0.980) | ✓ 1.58 | ✓ IoU 1.00 | **pass** |
| true_07_stovetop | pass | ✓ (0.961) | ✗ 1.60 | ✓ IoU 1.00 | refuse attribute_mismatch:form |
| true_08_steam_kitchen | pass | ✓ (0.973) | ✓ 1.59 | ✓ IoU 1.00 | **pass** |
| true_09_lowangle_grey | pass | ✓ (0.949) | ✓ 1.51 | ✓ IoU 1.00 | **pass** |
| true_10_in_open_box | pass | ✓ (0.957) | ✓ 1.16 | ✓ IoU 1.00 | **pass** |
| true_11_counter_mugs | pass | ✓ (0.945) | ✗ 1.64 | ✓ IoU 1.00 | refuse attribute_mismatch:form |
| true_12_straight_beige | pass | ✓ (0.961) | ✓ 1.54 | ✓ IoU 1.00 | **pass** |
| wrong_colour_black | refuse :colour | ✓ (0.977) | ✓ 1.52 | ✓ IoU 1.00 | **pass — MISS** |
| wrong_colour_silver | refuse :colour | ✓ (0.883) | ✗ 1.72 | ambiguous (0 records) | refuse ambiguous:colour |
| wrong_form_stovetop | refuse :form | ✓ (0.575) | ✓ 1.15 | ✓ IoU 1.00 | **pass — MISS** |
| wrong_form_electric_jug | refuse :form | ✓ (0.754) | ✓ 1.29 | ✓ IoU 1.00 | **pass — MISS** |
| wrong_item_toaster | refuse item_absent | ✗ 0 records | — | — | refuse item_absent |
| box_only_empty | refuse item_absent | ✗ 0 records | — | — | refuse item_absent |
| packaging_only | refuse item_absent | ✗ 0 records | — | — | refuse item_absent |
| blurry_true_kettle | refuse ambiguous | ✓ (0.961) | ✓ 1.52 | ✓ IoU 1.00 | **pass — MISS** |

## Score, as measured

- Verdict direction (pass the true, refuse the impostors): **12/20**.
- Expectation-exact, named reason included: **11/20** (silver refused,
  but as `ambiguous:colour`, not `attribute_mismatch:colour`).
- True set: 8/12 pass. Impostors: 4/8 refused.

## What the misses say

1. **Presence is strong.** SAM returned zero records for all three
   no-kettle photos and the toaster, and ≥0.945 confidence on 11 of 12
   full-kettle photos. The one absence on a true photo is the spout
   close-up — a tight crop gives the item phrase nothing to anchor to.
2. **The colour measurement is not evidence of colour.** On the black
   kettle, the "matte red gooseneck kettle" call returned a record
   whose box is identical to the item box (IoU 1.00) — the phrase's
   noun dominates and the overlap test then "confirms" a colour that
   is not there. Co-location is not colour.
3. **The form measurement is a box-aspect proxy, and it shows.** The
   three true form refusals are band-edge cases (aspects 1.69, 1.60,
   1.64 against a 0.5–1.6 band — a kettle framed wide reads "not
   gooseneck"), while both wrong-form impostors sit comfortably
   inside the band (1.15, 1.29). The proxy is labeled as a proxy in
   `runway/sam.py`; this matrix is what that label costs today.
4. **Blur does not move SAM 3.1.** Radius-12 Gaussian blur left every
   measurement unchanged in kind (confidence 0.961). The expected
   AMBIGUOUS never materialised — a blurry delivery photo is not, by
   itself, undecidable to this model.
5. **A signal the gate does not use yet:** the wrong-form stovetop's
   presence confidence was 0.575 and the jug's 0.754, against ≥0.945
   for every true full kettle. Noted as an observation only — no
   threshold has been adopted on the strength of one set.

## The fix path (already documented in `runway/sam.py`)

The real silhouette and the real colour both live in the **mask
raster**: decode Meta's arithmetic-coded base85 masks, take the
silhouette from the mask's shape instead of the box's aspect, and
sample the masked pixels' colour instead of trusting a phrase. That
decode is deliberately outside the stdlib build; this matrix is the
measured case for doing it next. Until then, Gate 4 is a strong
presence check and a weak attribute check, and the demo says so.
