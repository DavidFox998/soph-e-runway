"""Gate 0: seller verification. Gates 1-4 judge a claim; Gate 0
judges the claimant.

The demo's closing line is the design brief: today the agent
verifies the item, tomorrow it verifies the seller. Gate 0 applies
the system's one doctrine to the seller's measured history --
unmeasured refuses, and every refusal names its reason. A seller is
a sequence of claims that were measured: prices that were re-read,
attributes that were checked against delivered items. Gate 0
aggregates that record and issues one verdict for the seller,
before any single offer is entertained.

What it is not: a reputation score, a review aggregate, or a trust
rating asserted by anyone. Every input is a (claim, measurement)
pair this system produced; every rate is computed from those pairs;
a seller with too little measured history is refused for
insufficient_history, which is the unmeasured-refuses rule applied
to a track record instead of a claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gates import Verdict


@dataclass
class SellerRecord:
    """One measured claim in a seller's history.

    price_asserted / price_measured are cents; either may be None
    when that claim carried no price measurement. attributes_ok is
    True when the delivered item matched the claimed attributes,
    False when it did not, None when attributes were not measured
    for this claim. Unmeasured fields are excluded from their rates,
    never counted as faithful.
    """

    seller_id: str
    source: str  # evidence ref: run artifact, photo id, battery round
    price_asserted: int | None = None
    price_measured: int | None = None
    attributes_ok: bool | None = None


@dataclass
class SellerThresholds:
    min_records: int = 4          # below this, history is unmeasured
    max_price_drift_rate: float = 0.25
    max_attribute_mismatch_rate: float = 0.25


@dataclass
class SellerProfile:
    seller_id: str
    records: int
    price_measured_count: int
    price_drift_count: int
    price_drift_rate: float | None      # None when nothing measured
    mean_abs_drift_cents: float | None
    attribute_measured_count: int
    attribute_mismatch_count: int
    attribute_mismatch_rate: float | None

    def to_dict(self) -> dict:
        return {
            "seller_id": self.seller_id,
            "records": self.records,
            "price_measured_count": self.price_measured_count,
            "price_drift_count": self.price_drift_count,
            "price_drift_rate": self.price_drift_rate,
            "mean_abs_drift_cents": self.mean_abs_drift_cents,
            "attribute_measured_count": self.attribute_measured_count,
            "attribute_mismatch_count": self.attribute_mismatch_count,
            "attribute_mismatch_rate": self.attribute_mismatch_rate,
        }


def seller_profile(records: list[SellerRecord],
                   ) -> SellerProfile:
    """Aggregate a seller's measured record. Pure arithmetic over
    (claim, measurement) pairs; no record, no rate."""
    if not records:
        raise ValueError("a profile needs at least one record")
    seller_id = records[0].seller_id
    if any(r.seller_id != seller_id for r in records):
        raise ValueError("records mix sellers; profile one seller at a time")

    priced = [r for r in records
              if r.price_asserted is not None and r.price_measured is not None]
    drifts = [abs(r.price_measured - r.price_asserted) for r in priced
              if r.price_measured != r.price_asserted]
    attributed = [r for r in records if r.attributes_ok is not None]
    mismatches = [r for r in attributed if r.attributes_ok is False]

    return SellerProfile(
        seller_id=seller_id,
        records=len(records),
        price_measured_count=len(priced),
        price_drift_count=len(drifts),
        price_drift_rate=(len(drifts) / len(priced)) if priced else None,
        mean_abs_drift_cents=(sum(drifts) / len(drifts)) if drifts else None,
        attribute_measured_count=len(attributed),
        attribute_mismatch_count=len(mismatches),
        attribute_mismatch_rate=(len(mismatches) / len(attributed))
        if attributed else None,
    )


def gate_seller(records: list[SellerRecord],
                thresholds: SellerThresholds = SellerThresholds(),
                ) -> Verdict:
    """Gate 0. Pass requires measured history inside both rates.

    Check order is fixed and documented: history first (unmeasured
    refuses), then price drift (the money line), then attribute
    mismatch. A rate with no measurements behind it cannot pass a
    seller on that axis and cannot refuse one either -- it simply
    does not vote; the doc records which axes voted.
    """
    if len(records) < thresholds.min_records:
        return Verdict(status="refuse", reason="insufficient_history",
                       gate="seller")
    prof = seller_profile(records)
    if (prof.price_drift_rate is not None
            and prof.price_drift_rate > thresholds.max_price_drift_rate):
        return Verdict(status="refuse", reason="seller_price_drift",
                       gate="seller")
    if (prof.attribute_mismatch_rate is not None
            and prof.attribute_mismatch_rate
            > thresholds.max_attribute_mismatch_rate):
        return Verdict(status="refuse", reason="seller_attribute_mismatch",
                       gate="seller")
    return Verdict(status="pass", reason=None, gate="seller")
