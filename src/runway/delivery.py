"""Gate 4 — Delivery: the mandated item, verified in a photograph.

The riskiest dependency in the build is the vision backend, so Gate 4
sits behind a swappable measurement interface (suggestion: Beacon,
adopted Day 0): the gate logic consumes a Measurement and does not care
which backend produced it.

One property is stronger here than at any other gate: **the agent never
supplies Gate 4's measurement.** The gate calls the verifier itself, on
the photo reference, and the claim arrives empty-handed. A verifier that
is unconfigured, unreachable, or has never seen the photo returns None,
and None refuses as `unmeasured` — the end-to-end loop can run on the
stub today, and swapping in SAM 3.1 changes the backend, not the gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .claims import Claim, Measurement
from .gates import Mandate, Verdict, _apply


class DeliveryVerifier(Protocol):
    """Anything that can look at a delivery photo and report what is
    actually in it: {item, attributes, present}."""

    name: str

    def measure(self, photo_ref: str) -> Measurement | None:
        ...


@dataclass
class StubVerifier:
    """Fixture-backed verifier: photo_ref -> observed contents.

    Stands in for SAM until a backend is configured, so the loop, the
    impostor test set and the receipt format are all exercised now.
    An unknown photo_ref returns None (unmeasured), never a guess.
    """

    fixtures: dict[str, dict]
    name: str = "stub"

    def measure(self, photo_ref: str) -> Measurement | None:
        observed = self.fixtures.get(photo_ref)
        if observed is None:
            return None
        return Measurement(
            measured_by=f"stub:{self.name}",
            measured_value=dict(observed),
            evidence_refs=[photo_ref],
        )


@dataclass
class SamApiVerifier:
    """SAM 3.1 via the Meta Model API (hosted, Standard tier).

    Deliberately unconfigured until Appendix A verifies the in-account
    endpoint and model ID: until then measure() returns None and Gate 4
    refuses everything as unmeasured rather than pretending to see.
    """

    name: str = "sam-3.1-api"
    endpoint: str | None = None
    model_id: str | None = None

    def measure(self, photo_ref: str) -> Measurement | None:
        if not self.endpoint or not self.model_id:
            return None
        raise NotImplementedError(
            "SAM API transport lands with the Appendix A verification"
        )


def gate_delivery(
    mandate: Mandate,
    claim: Claim,
    verifier: DeliveryVerifier,
    photo_ref: str,
) -> Verdict:
    """Gate 4 verdict. Exact item + exact attributes + present, measured
    from the photo — or a named refusal."""
    gate = "delivery"
    if claim.kind != "delivery":
        return _apply(claim, Verdict("refuse", gate, "wrong_claim_kind"))
    measurement = verifier.measure(photo_ref)
    if measurement is None:
        return _apply(claim, Verdict("refuse", gate, "unmeasured"))
    claim.measurement = measurement
    m = measurement.measured_value
    if not m.get("present", False):
        return _apply(claim, Verdict("refuse", gate, "item_absent"))
    if m.get("item") != mandate.item:
        return _apply(claim, Verdict("refuse", gate, "item_mismatch"))
    measured_attrs = m.get("attributes") or {}
    for key, want in mandate.attributes.items():
        if measured_attrs.get(key) != want:
            return _apply(
                claim, Verdict("refuse", gate, f"attribute_mismatch:{key}")
            )
    return _apply(claim, Verdict("pass", gate))
