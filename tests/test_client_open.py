"""Baseten Spark Open client: the comparison proposer. Offline —
the transport is stubbed; what is pinned is the shape: the exact
hackathon model string, the Baseten base URL, the shared proposal
parser, and the no-key / no-content disciplines."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402

from runway.client import (  # noqa: E402
    BASETEN_API_BASE,
    BASETEN_MODEL,
    BasetenSparkClient,
    ProposalError,
)
from runway.gates import Mandate  # noqa: E402

MANDATE = Mandate(item="gooseneck kettle",
                  attributes={"colour": "matte red", "form": "gooseneck"},
                  cap_cents=4000, currency="USD")
REPLY = ('{"item": "gooseneck kettle", "attributes": '
         '{"colour": "matte red", "form": "gooseneck"}, '
         '"price_cents": 3499, "currency": "USD", "merchant": "Kettle & Co."}')


def test_defaults_are_the_hackathon_surface():
    client = BasetenSparkClient()
    assert client.model == "meta-models/muse-spark-open-1026"
    assert client.model == BASETEN_MODEL
    assert client.api_base == "https://inference.baseten.co/v1"
    assert client.api_base == BASETEN_API_BASE


def test_no_key_is_a_no_proposal(monkeypatch):
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    with pytest.raises(ProposalError):
        BasetenSparkClient().complete("anything")


def test_proposal_parses_through_the_shared_parser(monkeypatch):
    monkeypatch.setenv("BASETEN_API_KEY", "test-key-not-real")
    client = BasetenSparkClient()
    monkeypatch.setattr(client, "_chat", lambda prompt: REPLY)
    claim = client.propose_offer(MANDATE, merchant_hint="Kettle & Co.")
    assert claim.asserted_value["price_cents"] == 3499
    assert claim.asserted_by == f"spark:{BASETEN_MODEL}"


def test_contributor_guard_applies_here_too():
    with pytest.raises(ProposalError):
        BasetenSparkClient(model="muse-spark-open-contributor")
