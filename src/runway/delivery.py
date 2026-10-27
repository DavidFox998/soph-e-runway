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

    The call shape was doc-verified 2026-10-26
    (docs/sam-3.1-call-shape.md); the live probe decides the image
    transport variant. Wire `sam_measure` (runway.sam.measure) and a
    `photo_loader` to activate. Until wired, measure() returns None
    and Gate 4 refuses everything as unmeasured rather than
    pretending to see. Attributes SAM reports as AMBIGUOUS travel on
    the measurement, and Gate 4 refuses them by name — ambiguous is
    never silently converted into a mismatch or a pass.
    """

    name: str = "sam-3.1-api"
    item_label: str = "gooseneck kettle"
    sam_measure: object = None    # callable(image_b64) -> Gate4Measurement
    photo_loader: object = None   # callable(photo_ref) -> bytes

    def measure(self, photo_ref: str) -> Measurement | None:
        if self.sam_measure is None or self.photo_loader is None:
            return None
        import base64

        photo = self.photo_loader(photo_ref)
        gm = self.sam_measure(base64.b64encode(photo).decode())
        attrs_in = gm.attributes
        measured_attrs: dict[str, str] = {}
        ambiguous: list[str] = []
        colour = attrs_in.get("matte_red")
        if colour is not None:
            if colour.state == "ambiguous":
                ambiguous.append("colour")
            else:
                measured_attrs["colour"] = (
                    "matte red" if colour.present else "not matte red")
        form = attrs_in.get("gooseneck_silhouette")
        if form is not None:
            if form.state == "ambiguous":
                ambiguous.append("form")
            else:
                measured_attrs["form"] = (
                    "gooseneck" if form.present else "not gooseneck")
        present = attrs_in.get("present")
        return Measurement(
            measured_by="sam-3.1",
            measured_value={
                "item": self.item_label,
                "attributes": measured_attrs,
                "present": bool(present and present.present),
                "ambiguous": ambiguous,
            },
            evidence_refs=[f"sam-raw:{gm.raw_ref}"],
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
    ambiguous = m.get("ambiguous") or []
    if ambiguous:
        # An undecidable attribute refuses by name; it never guesses.
        return _apply(claim, Verdict("refuse", gate, f"ambiguous:{ambiguous[0]}"))
    if m.get("item") != mandate.item:
        return _apply(claim, Verdict("refuse", gate, "item_mismatch"))
    measured_attrs = m.get("attributes") or {}
    for key, want in mandate.attributes.items():
        if measured_attrs.get(key) != want:
            return _apply(
                claim, Verdict("refuse", gate, f"attribute_mismatch:{key}")
            )
    return _apply(claim, Verdict("pass", gate))
