# Spark Open comparison battery — 2026-10-28

The T2 battery (same mandate, same two scenarios, same probes with
the context fix, same runner and receipts) run against the
open-weights sibling, Muse Spark Open on Baseten's hackathon
surface (`meta-models/muse-spark-open-1026`, partner credits), next
to the hosted Spark 1.3 profile it is compared against. This is a
comparison measurement, not the submission's measured agent: the
B2/T2 receipts belong to the hosted Standard model.

| | hosted Spark 1.3 (T2 re-run) | Spark Open (Baseten, run 2) |
| --- | --- | --- |
| settle scenario | SETTLED, replay matched | SETTLED, replay matched |
| refuse scenario | REFUSED `over_cap`, replay matched | REFUSED `over_cap`, replay matched |
| coherence | 0.857 | 0.857 |
| continuity | 1.0 | 1.0 |
| calibration error | 0.186 | 0.186 |
| response median | 3.2s | 3.2s |
| `refusal_recall` | fails (explains, never names) | fails (explains, never names) |

Two findings:

1. **The profiles are identical at the headline level.** Same
   outcomes through the gates, same probe aggregates, same response
   band. Whatever the gates measure, they measure it the same way
   on both variants — the instrument is variant-stable on this
   battery.
2. **The `refusal_recall` holdout replicates.** Handed the full
   record, the open model also explains the refusal in prose
   without producing the recorded reason code. The T2 holdout is
   therefore not a quirk of one hosted checkpoint: across two
   model variants, the agent explains and the receipt names. The
   design line stands on a second measurement: the receipt names
   the reason so the agent doesn't have to.

Bookkeeping, kept honest: this battery ran twice. Run 1
(`artifacts/live_run_open_20261028T071420Z`, receipts on file)
completed both scenarios with identical outcomes and replay-matched
receipts, then the runner crashed serialising the liveliness
profile (a missing `.to_dict()` in the new script, fixed in
5ee56fb7), so run 1 has no profile. Run 1 also showed beat-level
variance the aggregate hides: its refuse-scenario `mandate_recall`
came back incoherent where run 2's passed. Run 2
(`artifacts/live_run_open_20261028T071917Z`) is the complete set:
5 model calls against the $100 grant.
