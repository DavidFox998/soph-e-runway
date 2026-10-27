#!/usr/bin/env python3
"""Gate 0 evaluation: run gate_seller over every seller record this
program has actually measured, plus scripted archetypes whose ground
truth is known by construction.

Real records:
- kettle-and-co: the demo merchant's eight claims across the four
  live runs (B2, T2 re-run, Spark Open runs 1-2). Settle claims were
  faithful (3499 asserted, 3499 re-read); refuse-scenario claims
  drifted (3900 asserted, 4250 re-read). Attributes were not
  measured per claim, so that axis does not vote.
- photoset-seller: the Gate 4 photo set read as one seller's
  delivery history. Ground truth is what was delivered (the file
  class in assets/gate4/manifest.json): the twelve true_* photos
  delivered the claimed matte red gooseneck; the eight impostor
  photos delivered something else. Photo measurability (the blurry
  photo, the spout close-up) is a Gate 4 problem, not seller
  infidelity, and is not counted against the seller.

Archetypes (deterministic, ground truth by construction): an honest
seller, a price drifter, an attribute mislabeler, and a newcomer
whose short history is clean but unmeasured-enough.

Output: artifacts/gate0_evaluation.json + a printed table.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from runway.sellers import SellerRecord, gate_seller, seller_profile  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def kettle_and_co():
    runs = [
        ("b2-live-run", 3499, 3499), ("b2-live-run", 3900, 4250),
        ("live_run_20261027T192237Z", 3499, 3499),
        ("live_run_20261027T192237Z", 3900, 4250),
        ("live_run_open_20261028T071420Z", 3499, 3499),
        ("live_run_open_20261028T071420Z", 3900, 4250),
        ("live_run_open_20261028T071917Z", 3499, 3499),
        ("live_run_open_20261028T071917Z", 3900, 4250),
    ]
    return [SellerRecord(seller_id="kettle-and-co", source=src,
                         price_asserted=a, price_measured=m,
                         attributes_ok=None)
            for src, a, m in runs]


def photoset_seller():
    manifest = json.load(open(os.path.join(
        ROOT, "assets", "gate4", "manifest.json")))
    records = []
    for photo in manifest["photos"]:
        genuine = photo["file"].startswith("true_")
        records.append(SellerRecord(
            seller_id="photoset-seller", source=photo["file"],
            attributes_ok=genuine))
    return records


def archetype(seller, n, drift_every=None, mismatch_every=None):
    records = []
    for i in range(n):
        drift = drift_every is not None and (i % drift_every == 1)
        mismatch = mismatch_every is not None and (i % mismatch_every == 1)
        records.append(SellerRecord(
            seller_id=seller, source=f"{seller}-{i}",
            price_asserted=3000,
            price_measured=3400 if drift else 3000,
            attributes_ok=not mismatch))
    return records


SETS = [
    ("kettle-and-co (real, 4 live runs)", kettle_and_co(), None),
    ("photoset-seller (real, Gate 4 set)", photoset_seller(), None),
    ("archetype: honest", archetype("honest", 12), "pass"),
    ("archetype: drifter", archetype("drifter", 12, drift_every=2),
     "seller_price_drift"),
    ("archetype: mislabeler",
     archetype("mislabeler", 12, mismatch_every=3),
     "seller_attribute_mismatch"),
    ("archetype: newcomer", archetype("newcomer", 2),
     "insufficient_history"),
]


def main():
    out = {"sets": []}
    separated = 0
    for name, records, expected in SETS:
        prof = seller_profile(records)
        verdict = gate_seller(records)
        got = verdict.reason if verdict.status == "refuse" else "pass"
        row = {"set": name, "profile": prof.to_dict(),
               "verdict": {"status": verdict.status,
                           "reason": verdict.reason},
               "expected": expected,
               "as_expected": (expected is None or got == expected)}
        if expected is not None and got == expected:
            separated += 1
        out["sets"].append(row)
        print(f"{name}: records={prof.records} "
              f"drift_rate={prof.price_drift_rate} "
              f"mismatch_rate={prof.attribute_mismatch_rate} "
              f"-> {verdict.status}"
              f"{'' if verdict.reason is None else ' (' + verdict.reason + ')'}")
    out["archetypes_separated"] = f"{separated}/4"
    print(f"archetype separation: {separated}/4")
    path = os.path.join(ROOT, "artifacts", "gate0_evaluation.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {path}")
    return 0 if separated == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
