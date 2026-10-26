"""Claims: typed, attributed assertions with a verdict.

The mirror of schemas/claim.schema.json. A claim carries what is asserted,
who asserts it, the independent measurement (or None), and its verdict.
Unmeasured is a state, not an oversight: a claim whose measurement is None
can only ever be refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CLAIM_KINDS = ("mandate", "offer", "payment", "delivery", "receipt")
VERDICTS = ("pending", "pass", "refuse")


@dataclass
class Measurement:
    measured_by: str
    measured_value: dict
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Claim:
    claim_id: str
    kind: str
    subject: dict
    asserted_by: str
    asserted_value: dict
    measurement: Measurement | None = None
    verdict_status: str = "pending"
    verdict_reason: str | None = None
    verdict_gate: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in CLAIM_KINDS:
            raise ValueError(f"unknown claim kind: {self.kind!r}")
        if self.verdict_status not in VERDICTS:
            raise ValueError(f"unknown verdict: {self.verdict_status!r}")

    @property
    def measured(self) -> bool:
        return self.measurement is not None

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "kind": self.kind,
            "subject": self.subject,
            "asserted_by": self.asserted_by,
            "asserted_value": self.asserted_value,
            "measurement": (
                None
                if self.measurement is None
                else {
                    "measured_by": self.measurement.measured_by,
                    "measured_value": self.measurement.measured_value,
                    "evidence_refs": list(self.measurement.evidence_refs),
                }
            ),
            "verdict": {
                "status": self.verdict_status,
                "reason": self.verdict_reason,
                "gate": self.verdict_gate,
            },
        }
