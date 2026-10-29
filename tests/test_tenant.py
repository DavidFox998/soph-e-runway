import pytest

from runway.client import MetaSparkClient, ProposalError, StubSparkClient
from runway.gates import Mandate
from runway.tenant import Tenant

MANDATE = Mandate(
    item="gooseneck kettle",
    attributes={"colour": "matte red", "form": "gooseneck"},
    cap_cents=4000,
)

GOOD_REPLY = (
    '{"item": "gooseneck kettle", "attributes": {"colour": "matte red", '
    '"form": "gooseneck"}, "price_cents": 3850, "currency": "USD", '
    '"merchant": "KettleHouse"}'
)


def test_mandate_in_typed_claim_out():
    claim = Tenant(StubSparkClient(GOOD_REPLY)).propose(MANDATE)
    assert claim.kind == "offer"
    assert claim.subject["item"] == "gooseneck kettle"
    assert claim.subject["attributes"]["colour"] == "matte red"
    assert claim.asserted_value["price_cents"] == 3850
    assert claim.asserted_by == "spark:stub"


def test_proposal_is_unmeasured_by_construction():
    claim = Tenant(StubSparkClient(GOOD_REPLY)).propose(MANDATE)
    assert claim.measurement is None
    assert claim.verdict_status == "pending"


def test_malformed_proposal_emits_no_claim():
    with pytest.raises(ProposalError):
        Tenant(StubSparkClient("the kettle is nice, trust me")).propose(MANDATE)


def test_fenced_json_still_parses():
    claim = Tenant(StubSparkClient("```json\n" + GOOD_REPLY + "\n```")).propose(MANDATE)
    assert claim.asserted_value["price_cents"] == 3850


def test_contributor_model_refused_at_construction():
    with pytest.raises(ProposalError):
        MetaSparkClient(model="muse-spark-1.3-contributor")


def test_missing_api_key_is_a_clean_refusal(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)
    with pytest.raises(ProposalError):
        MetaSparkClient().propose_offer(MANDATE)
