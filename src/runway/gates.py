"""Gates: (claim, measurement) -> verdict. Unmeasured refuses.

A gate never sees the agent's confidence. It sees a claim and an
independent measurement, and it returns PASS with the measurement attached
or REFUSE with a named reason. Gates are the operational form of Gadiel
Alignment Theory: Axis 1 (client financial well-being) and Axis 2 (client
preferences, exact) are enforced here and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass

from .claims import Claim


@dataclass
class Verdict:
    status: str  # "pass" | "refuse"
    gate: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ("pass", "refuse"):
            raise ValueError(f"unknown verdict status: {self.status!r}")
        if self.status == "refuse" and not self.reason:
            raise ValueError("a refusal must name its reason")


@dataclass(frozen=True)
class Mandate:
    """A client mandate in exact, checkable terms."""

    item: str
    attributes: dict  # e.g. {"colour": "matte red", "form": "gooseneck"}
    cap_cents: int
    currency: str = "USD"
    deadline_iso: str | None = None

    def __post_init__(self) -> None:
        if self.cap_cents <= 0:
            raise ValueError("a mandate without a positive cap is not a mandate")


def _apply(claim: Claim, verdict: Verdict) -> Verdict:
    claim.verdict_status = verdict.status
    claim.verdict_reason = verdict.reason
    claim.verdict_gate = verdict.gate
    return verdict


def gate_offer(mandate: Mandate, claim: Claim) -> Verdict:
    """Gate 2 — Offer. The measured offer must be the mandated item, with
    the mandated attributes, at a delivered total within the cap.

    The claim's *asserted* price is never consulted. Only the measurement
    is. That is the whole point of the gate.
    """
    gate = "offer"
    if claim.kind != "offer":
        return _apply(claim, Verdict("refuse", gate, "wrong_claim_kind"))
    if not claim.measured:
        return _apply(claim, Verdict("refuse", gate, "unmeasured"))
    m = claim.measurement.measured_value
    if m.get("item") != mandate.item:
        return _apply(claim, Verdict("refuse", gate, "item_mismatch"))
    measured_attrs = m.get("attributes") or {}
    for key, want in mandate.attributes.items():
        if measured_attrs.get(key) != want:
            return _apply(claim, Verdict("refuse", gate, f"attribute_mismatch:{key}"))
    price = m.get("price_cents")
    if price is None:
        return _apply(claim, Verdict("refuse", gate, "price_unmeasured"))
    if m.get("currency", mandate.currency) != mandate.currency:
        return _apply(claim, Verdict("refuse", gate, "currency_mismatch"))
    if price > mandate.cap_cents:
        return _apply(claim, Verdict("refuse", gate, "over_cap"))
    return _apply(claim, Verdict("pass", gate))


def gate_payment(mandate: Mandate, claim: Claim, already_paid_cents: int = 0) -> Verdict:
    """Gate 3 — Payment. Pay exactly the measured amount, once, within cap.

    The ledger total (already paid in this run + this payment) may never
    exceed the mandate cap: no double charges, no double payments.
    """
    gate = "payment"
    if claim.kind != "payment":
        return _apply(claim, Verdict("refuse", gate, "wrong_claim_kind"))
    if not claim.measured:
        return _apply(claim, Verdict("refuse", gate, "unmeasured"))
    m = claim.measurement.measured_value
    amount = m.get("amount_cents")
    if amount is None:
        return _apply(claim, Verdict("refuse", gate, "amount_unmeasured"))
    if amount <= 0:
        return _apply(claim, Verdict("refuse", gate, "nonpositive_amount"))
    if already_paid_cents + amount > mandate.cap_cents:
        return _apply(claim, Verdict("refuse", gate, "over_cap_cumulative"))
    return _apply(claim, Verdict("pass", gate))
