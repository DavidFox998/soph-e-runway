# Ambiguity probes through the fixed Gate 4 — measured 2026-10-27

Work order 3: the five hard inputs from `gate4-ambiguity-probes.md`,
re-run through the merged mask-decode measurement (T1). No
thresholds were tuned for this run. The question was whether
AMBIGUOUS fires with its name on a receipt, or the fixed gate
resolves them. **The gate resolves them — every one on mask and
pixel quantities — and AMBIGUOUS does not fire.** Per photo:

| Probe | v1 (phrase) verdict | v2 (mask) verdict | The v2 quantities |
|---|---|---|---|
| amb_half_frame | pass | **refuse attribute_mismatch:form** | mask fill **0.28**, below the 0.30 floor — a half-kettle's silhouette does not fill its box like a whole one; colour perfect (red share 1.00, median (162, 47, 51)) |
| amb_occluded_flap | refuse item_absent | refuse item_absent | 0 item records; nothing to decode, as before |
| amb_fogged_lens | pass | **pass** | fill 0.48; red share **0.84** under the mask despite the fog (median (170, 139, 140) — washed toward grey, still red-dominant) |
| amb_extreme_blur | pass | **pass** | fill 0.46; red share 0.91 — radius-40 blur does not move the mask measurement |
| amb_very_dark | pass | **refuse attribute_mismatch:colour** | red share **0.33**, median RGB **(51, 9, 12)** — see the low-light finding below |

## What the run established

**The v1 passes were blind; the v2 resolutions are measured.**
Under the phrase measurement, half-frame and very-dark passed on
box overlap and a colour phrase. Under the mask measurement the
half-frame refuses on a named quantity (its silhouette's fill is
what a partial item's fill should be — low), and the fogged and
blurred photos pass on quantities a judge can re-check (their
masks are whole-kettle shaped and their masked pixels are
red-dominant). The gate did not get more lenient or more strict;
it got *specific*.

**Low-light finding (new, named, not tuned away).** The very-dark
kettle is red — proportionally its masked pixels are strongly
red-dominant (51 vs 9 vs 12) — but the colour rule's
red-dominance test carries an absolute floor (R ≥ 70) that a
near-dark photo cannot meet, so the share falls to 0.33 and the
gate refuses on colour. Two honest readings: the floor makes the
gate conservative in the dark (a delivery photo too dark to
verify colour refuses rather than passes, and the receipt names
the exact share and median), and the floor is a brightness
assumption baked into a colour test. Which reading governs is a
design decision for the owner; the run's job was to surface it
with numbers, and it is now on record. No threshold moved.

**The third verdict, final accounting.** Across the v1 matrix,
the ambiguity set, and this run, AMBIGUOUS has fired exactly once
— silver, as `ambiguous:colour`, phrase silence on a present
item. Under the mask measurement its remaining roads are
infrastructure states, not image states: a mask that fails to
decode, or a pixel source not wired. Degradation has never
produced it, at blur radii 12 and 40, in fog, in near-darkness,
at half-frame. The verdict exists, is named, and is narrow —
that is its measured shape, and the doc trail now closes on it.
