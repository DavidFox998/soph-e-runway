#!/usr/bin/env python3
"""Live Spark run (Order B2): the real proposer, end to end.

Drives `run_mandate` with the real `MetaSparkClient` (Muse Spark 1.3,
Standard tier) as the proposer. The API key comes from the
META_API_KEY environment variable; it is never committed, never
echoed, and the client reads it at call time.

THE OFFER RE-READER IS FIXTURE-BACKED. No merchant surface exists
yet, so the measurement each claim is gated on comes from a fixed
fixture snapshot of a merchant page (one per scenario, below). The
gates read the fixture measurement exactly as they would read a live
re-read — the asserted price in Spark's proposal is never consulted.
That substitution is the one unreal part of this run, and it is
stated here in plain words rather than hidden.

Scenarios (same mandate both times — matte red gooseneck kettle,
$40.00 cap):
  1. settle — the fixture re-read is $34.99, inside the cap. The run
     must SETTLE and seal its receipt.
  2. refuse — the listing snapshot the proposer saw says $39.00
     delivered (in cap, and Spark proposes it cleanly); the fixture
     re-read at purchase time measures $42.50 — the price moved.
     The run must REFUSE — the gate reads the measurement, not the
     assertion — and seal the refusal. (Scenario redesigned
     2026-10-27 after measurement, not taste: prompts that forced
     Spark to either fabricate a number or break the cap — an
     over-cap price in the prompt, or a pre-fees price with the
     delivered total unknowable — returned empty content on 8 of 9
     calls across four runs and direct diagnostics, while every
     well-posed prompt answered. Spark's silence over fabrication
     is recorded in those transcripts; this scenario tests the gate
     against price drift, which is the attack the gate exists for.)

Probes run live against the same Spark client (mandate recall before
the run, refusal recall after a refusal); consistency and arithmetic
probes are pure checks over the emitted claim. If Spark returns a
malformed proposal, the client emits no claim; the transcript
records NO_CLAIM and the scenario stops there — not forced, not
hidden.

Cost guard: at most 20 model calls per scenario; the run aborts if
the estimated spend exceeds $0.50. The estimate uses the published
Spark 1.3 rates ($1.25 / 1M input, $4.25 / 1M output) at the
client's 1024-token completion budget — an upper-bound estimate,
labelled as such; the client does not surface per-call usage.

Artifacts land in artifacts/live_run_<UTC timestamp>/: transcript,
one receipt per scenario, the liveliness profile, and a summary.
Exit 0 iff scenario 1 SETTLED and scenario 2 REFUSED.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from runway.brain import profile  # noqa: E402
from runway.claims import Measurement  # noqa: E402
from runway.client import MetaSparkClient, ProposalError  # noqa: E402
from runway.gates import Mandate  # noqa: E402
from runway.probes import (ProbeClock, arithmetic_check,  # noqa: E402
                           claim_consistency, control_beat,
                           mandate_recall, refusal_recall)
from runway.run import replay, run_mandate  # noqa: E402

MANDATE = Mandate(
    item="gooseneck kettle",
    attributes={"colour": "matte red", "form": "gooseneck"},
    cap_cents=4000,
    currency="USD",
)
MAX_CALLS_PER_SCENARIO = 20
EST_INPUT_TOKENS = 220          # prompt is short; reasoning dominates
EST_OUTPUT_TOKENS = 2048        # the live run's completion budget
EST_CALL_USD = (EST_INPUT_TOKENS * 1.25 + EST_OUTPUT_TOKENS * 4.25) / 1_000_000
COST_GUARD_USD = 0.50
# Reasoning budget. Measured live, 2026-10-27: on the over-cap prompt
# Spark's reasoning is high-variance — one call finished at 1,355
# completion tokens with the offer JSON; another burned 4,094
# reasoning tokens and returned empty content (finish=length). A
# bigger budget makes a spiral longer, not rarer, so the run uses
# 2048 and treats an empty reply as what the client already calls it:
# no proposal. The driver may re-ask (MAX_PROPOSAL_ATTEMPTS) — each
# attempt is transcribed, the prompt is never edited to force an
# outcome, and the 20-call cost guard still binds.
LIVE_MAX_TOKENS = 2048
MAX_PROPOSAL_ATTEMPTS = 3


class CountingClient:
    """Delegates verbatim to the real client; counts model calls and
    enforces the per-scenario call budget."""

    def __init__(self, inner):
        self.inner = inner
        self.model = inner.model
        self.calls = 0

    def _tick(self):
        self.calls += 1
        if self.calls > MAX_CALLS_PER_SCENARIO:
            raise RuntimeError(
                f"cost guard: scenario exceeded {MAX_CALLS_PER_SCENARIO} calls"
            )

    def propose_offer(self, mandate, merchant_hint=None):
        self._tick()
        return self.inner.propose_offer(mandate, merchant_hint)

    def complete(self, prompt):
        self._tick()
        return self.inner.complete(prompt)


class FixtureMeasurer:
    """The fixture-backed offer re-reader (see the header). Returns
    the scenario's fixed merchant-page snapshot as the measurement,
    whatever the claim asserted."""

    def __init__(self, price_cents: int, snapshot: str):
        self.price_cents = price_cents
        self.snapshot = snapshot

    def __call__(self, claim) -> Measurement:
        return Measurement(
            measured_by="fixture_rereader",
            measured_value={
                "item": MANDATE.item,
                "attributes": dict(MANDATE.attributes),
                "price_cents": self.price_cents,
                "currency": "USD",
            },
            evidence_refs=[f"fixture:{self.snapshot}"],
        )


def run_scenario(name, hint, fixture_price, snapshot, outdir, log):
    client = CountingClient(MetaSparkClient(max_tokens=LIVE_MAX_TOKENS))
    clock = ProbeClock()
    beats = []
    receipt_path = os.path.join(outdir, f"receipt_{name}.jsonl")

    log(f"--- scenario {name} ---")
    log(f"merchant hint: {hint}")
    log(f"fixture re-read: {fixture_price} cents ({snapshot})")

    beats.append(mandate_recall(client, MANDATE, clock))
    log(f"probe mandate_recall: coherent={beats[-1].coherent} "
        f"response_ms={beats[-1].response_ms:.0f}")
    beats.append(control_beat(clock))

    claim = None
    for attempt in range(1, MAX_PROPOSAL_ATTEMPTS + 1):
        try:
            claim = client.propose_offer(MANDATE, merchant_hint=hint)
            log(f"proposal attempt {attempt}: claim emitted")
            break
        except ProposalError as exc:
            log(f"proposal attempt {attempt}: NO_CLAIM ({exc})")
    if claim is None:
        return {"scenario": name, "outcome": "NO_CLAIM", "calls": client.calls,
                "beats": beats, "receipt_head": None, "replay_match": None}
    log(f"proposal: item={claim.subject.get('item')!r} "
        f"attributes={claim.subject.get('attributes')} "
        f"asserted_price_cents={claim.asserted_value.get('price_cents')} "
        f"merchant={claim.asserted_value.get('merchant')!r} "
        f"asserted_by={claim.asserted_by}")

    beats.append(claim_consistency(claim, MANDATE, clock))
    beats.append(arithmetic_check(claim, MANDATE, 0, clock))
    log(f"probe claim_consistency: coherent={beats[-2].coherent}; "
        f"arithmetic_check: coherent={beats[-1].coherent}")

    result = run_mandate(
        MANDATE, [claim], receipt_path,
        measurer=FixtureMeasurer(fixture_price, snapshot),
        run_id=f"live-{name}",
    )
    log(f"outcome: {result.outcome}")
    for v in result.verdicts:
        log(f"verdict: gate={v.get('gate')} status={v.get('status')} "
            f"reason={v.get('reason')}")
    log(f"receipt head: {result.receipt_head_hash}")
    log(f"ledger state: {json.dumps(result.ledger_state)}")

    rep = replay(receipt_path, MANDATE)
    match = (rep.outcome == result.outcome
             and rep.receipt_head_hash == result.receipt_head_hash)
    log(f"replay: outcome={rep.outcome} head_match={match}")

    if result.outcome == "REFUSED":
        reason = next(
            (v.get("reason") for v in result.verdicts
             if v.get("status") == "refuse"), "")
        beats.append(refusal_recall(client, reason or "", clock))
        log(f"probe refusal_recall (reason={reason!r}): "
            f"coherent={beats[-1].coherent}")

    return {"scenario": name, "outcome": result.outcome, "calls": client.calls,
            "beats": beats, "receipt_head": result.receipt_head_hash,
            "replay_match": match}


def main():
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    outdir = os.path.join(
        os.path.dirname(__file__), "..", "artifacts", f"live_run_{ts}")
    outdir = os.path.normpath(outdir)
    os.makedirs(outdir, exist_ok=True)

    lines = []

    def log(s=""):
        print(s, flush=True)
        lines.append(s)

    log(f"live Spark run — {ts}")
    log(f"model: {MetaSparkClient().model} (Standard tier; "
        "contributor IDs refused by the client)")
    log("re-reader: FIXTURE-BACKED (no merchant surface exists yet)")

    scenarios = [
        ("settle",
         "Merchant context: Kettle & Co. lists the matte red gooseneck "
         "kettle at $34.99 delivered.",
         3499, "kettle-co-listing-3499"),
        ("refuse",
         "Merchant context: Kettle & Co. lists the matte red gooseneck "
         "kettle at $39.00 delivered.",
         4250, "kettle-co-reread-4250-price-moved"),
    ]

    results = []
    all_beats = []
    total_calls = 0
    for name, hint, price, snapshot in scenarios:
        r = run_scenario(name, hint, price, snapshot, outdir, log)
        results.append(r)
        all_beats.extend(r["beats"])
        total_calls += r["calls"]
        est = total_calls * EST_CALL_USD
        log(f"calls so far: {total_calls}; estimated spend: ${est:.4f}")
        if est > COST_GUARD_USD:
            log("cost guard tripped — aborting further scenarios")
            break

    prof = profile(all_beats).to_dict()
    with open(os.path.join(outdir, "profile.json"), "w") as f:
        json.dump(prof, f, indent=2)
    log(f"liveliness profile: {json.dumps(prof)}")

    summary = {
        "ts": ts,
        "model": MetaSparkClient().model,
        "scenarios": [
            {k: v for k, v in r.items() if k != "beats"} for r in results
        ],
        "total_calls": total_calls,
        "estimated_spend_usd": round(total_calls * EST_CALL_USD, 4),
        "cost_estimate_basis": "upper bound: 220 input + 1024 output "
                               "tokens per call at $1.25/$4.25 per 1M",
    }
    with open(os.path.join(outdir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    with open(os.path.join(outdir, "transcript.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")

    ok = (len(results) == 2
          and results[0]["outcome"] == "SETTLED"
          and results[1]["outcome"] == "REFUSED")
    log(f"acceptance: {'PASS' if ok else 'NOT MET — reported as measured'}")
    with open(os.path.join(outdir, "transcript.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
