"""The liveliness probes (Stage 3): four checks that genuinely run.

Each probe measures the agent against the run's own record — never
against a script's expectation of itself:

- `mandate_recall` — the proposer restates the mandate from memory;
  coherent iff item and cap come back exact.
- `claim_consistency` — the emitted claim against the mandate
  (pure check over the actual claim object).
- `arithmetic_check` — the claim's numbers against the cap and the
  running total (pure check).
- `refusal_recall` — after a refusal, the proposer explains it;
  coherent iff it names the recorded reason.

The probes run mid-task and their beats feed brain.profile(). In the
demo they execute against scripted proposers — the choreography is
in the answers, never in the measurement: profile() computes what
the probes actually returned. On the live path the same probes run
against Muse Spark.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .brain import Beat
from .claims import Claim
from .gates import Mandate


@dataclass
class ProbeClock:
    """Monotone demo clock: beats advance it; a hesitation advances
    it further, and continuity is computed from the gaps."""

    t: float = 0.0

    def advance(self, dt: float = 1.0) -> float:
        self.t += dt
        return self.t


def mandate_recall(client, mandate: Mandate, clock: ProbeClock,
                   *, confidence: float = 0.9, hesitate: float = 1.0) -> Beat:
    start = time.perf_counter()
    try:
        reply = client.complete(
            "Restate the mandate you are serving: item and cap in cents."
        )
    except Exception:
        reply = ""
    ms = (time.perf_counter() - start) * 1000.0
    ok = mandate.item in reply and str(mandate.cap_cents) in reply
    return Beat(
        t=clock.advance(hesitate), kind="probe", probe="mandate_recall",
        response_ms=ms, coherent=ok, confidence=confidence, outcome=ok,
        perturbed=not ok,
    )


def claim_consistency(claim: Claim, mandate: Mandate, clock: ProbeClock) -> Beat:
    ok = (
        claim.subject.get("item") == mandate.item
        and claim.asserted_value.get("price_cents") is not None
    )
    return Beat(
        t=clock.advance(), kind="probe", probe="claim_consistency",
        coherent=ok, confidence=0.95, outcome=ok,
    )


def arithmetic_check(claim: Claim, mandate: Mandate, already_cents: int,
                     clock: ProbeClock) -> Beat:
    price = claim.asserted_value.get("price_cents")
    ok = (
        isinstance(price, int)
        and 0 < price <= mandate.cap_cents
        and already_cents + price <= mandate.cap_cents
    )
    return Beat(
        t=clock.advance(), kind="probe", probe="arithmetic_check",
        coherent=ok, confidence=0.95, outcome=ok,
    )


def refusal_recall(client, reason: str, clock: ProbeClock,
                   *, confidence: float = 0.9) -> Beat:
    try:
        reply = client.complete(
            "Why was the last claim refused? Answer with the reason code."
        )
    except Exception:
        reply = ""
    ok = reason in reply
    return Beat(
        t=clock.advance(), kind="probe", probe="refusal_recall",
        coherent=ok, confidence=confidence, outcome=ok,
    )


def control_beat(clock: ProbeClock) -> Beat:
    """An unprobed beat: the wrapper observes silence. Control beats
    are reported separately, never mixed into the probe series —
    probing perturbs, so the unprobed baseline stays visible."""
    return Beat(t=clock.advance(), kind="control")
