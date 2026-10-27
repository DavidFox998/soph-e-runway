"""Spark clients: anything that can turn a mandate into a proposed offer.

The shopper's proposer is Muse Spark over the Meta Model API
(OpenAI-compatible chat). Two disciplines are enforced in this module:

- **Standard tier only.** A model ID ending in `-contributor` is refused
  at construction time. Contributor traffic may be used for training;
  the build never touches it.
- **Proposal is not evidence.** What comes back is an *asserted* claim
  with no measurement. Spark can be wrong, optimistic, or manipulated by
  a merchant page; the gates exist precisely because this module's
  output is not trusted.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .claims import Claim
from .gates import Mandate

API_BASE = "https://api.meta.ai/v1"
DEFAULT_MODEL = "muse-spark-1.3"


class ProposalError(Exception):
    """The proposer produced nothing usable. A failed proposal emits no
    claim at all — silence, not a guess."""


def _guard_model(model: str) -> str:
    if model.endswith("-contributor"):
        raise ProposalError(
            f"refusing contributor-tier model {model!r}: Standard tier only"
        )
    return model


class SparkClient(Protocol):
    model: str

    def propose_offer(self, mandate: Mandate, merchant_hint: str | None = None) -> Claim:
        ...


def _prompt(mandate: Mandate, merchant_hint: str | None) -> str:
    attrs = ", ".join(f"{k}={v}" for k, v in sorted(mandate.attributes.items()))
    hint = f" Merchant context: {merchant_hint}." if merchant_hint else ""
    return (
        "You are the proposer for a trust-gated shopping agent. "
        f"Mandate: item = {mandate.item}; attributes: {attrs}; "
        f"hard cap = {mandate.cap_cents} cents {mandate.currency} delivered total."
        f"{hint} Propose ONE offer as JSON only, no prose, with keys: "
        '"item" (string), "attributes" (object), "price_cents" (integer, '
        'delivered total), "currency" (string), "merchant" (string).'
    )


def claim_from_proposal(raw: str, model: str, claim_id: str = "offer-1") -> Claim:
    """Parse a proposer reply into a typed offer Claim, or raise."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        data = json.loads(text)
        price = int(data["price_cents"])
        item = str(data["item"])
        attributes = {str(k): str(v) for k, v in dict(data["attributes"]).items()}
        currency = str(data.get("currency", "USD"))
        merchant = str(data.get("merchant", "unknown"))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ProposalError(f"unparseable proposal: {exc}") from exc
    return Claim(
        claim_id=claim_id,
        kind="offer",
        subject={"item": item, "attributes": attributes},
        asserted_by=f"spark:{model}",
        asserted_value={
            "price_cents": price,
            "currency": currency,
            "merchant": merchant,
        },
        measurement=None,
    )


@dataclass
class MetaSparkClient:
    """Muse Spark over the Meta Model API. The key is read from the
    META_API_KEY environment variable at call time and never stored."""

    model: str = DEFAULT_MODEL
    api_base: str = API_BASE
    max_tokens: int = 1024  # Spark reasons first; budget for the reasoning

    def __post_init__(self) -> None:
        _guard_model(self.model)

    def complete(self, prompt: str) -> str:
        """One raw chat completion. Used by the mandate parser, which
        applies its own strict decoding to whatever comes back."""
        return self._chat(prompt)

    def _chat(self, prompt: str) -> str:
        key = os.environ.get("META_API_KEY")
        if not key:
            raise ProposalError("META_API_KEY is not set; proposer cannot run")
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
        }
        req = urllib.request.Request(
            self.api_base + "/chat/completions", method="POST"
        )
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(
                req, data=json.dumps(body).encode(), timeout=60
            ) as resp:
                out = json.loads(resp.read().decode())
            content = out["choices"][0]["message"]["content"]
        except Exception as exc:  # transport, HTTP, shape: all are no-proposal
            raise ProposalError(f"proposer call failed: {exc}") from exc
        if not content:
            raise ProposalError("proposer returned no content (reasoning budget?)")
        return content

    def propose_offer(self, mandate: Mandate, merchant_hint: str | None = None) -> Claim:
        content = self._chat(_prompt(mandate, merchant_hint))
        return claim_from_proposal(content, self.model)


@dataclass
class StubSparkClient:
    """A canned proposer for tests and offline runs. Returns the reply
    verbatim through the same parser the live client uses."""

    reply: str
    model: str = "stub"

    def propose_offer(self, mandate: Mandate, merchant_hint: str | None = None) -> Claim:
        return claim_from_proposal(self.reply, self.model)
