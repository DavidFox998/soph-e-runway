"""The shopper (build Stage 1): mandate in, typed claim out.

The shopper is the proposer half of SOPH-E and it is structurally
incapable of spending: this module has no payment import, no ledger
handle, no rail. Its only output is a Claim — an assertion with the
proposer's name on it and no measurement — which the gates may pass,
refuse, or ignore. Everything else in the system bolts onto this spine:
gates judge what the shopper proposes, the receipt chain seals the
judgments, the brain watches the shopper work.

Propose-only invariants, checked on every proposal:
- the claim is an offer claim
- the claim carries no measurement (a proposer that arrives with its
  own measurement is grading its own homework)
"""

from __future__ import annotations

from dataclasses import dataclass

from .claims import Claim
from .client import SparkClient
from .gates import Mandate


@dataclass
class Shopper:
    client: SparkClient

    def propose(self, mandate: Mandate, merchant_hint: str | None = None) -> Claim:
        claim = self.client.propose_offer(mandate, merchant_hint)
        if claim.kind != "offer":
            raise ValueError(f"proposer emitted a {claim.kind!r} claim, not an offer")
        if claim.measurement is not None:
            raise ValueError("proposer arrived with its own measurement; refused")
        return claim
