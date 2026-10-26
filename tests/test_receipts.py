from runway.receipts import ReceiptChain


def _chain() -> ReceiptChain:
    c = ReceiptChain()
    c.append("run_start", {"run_id": "r1"}, ts="2026-10-26T22:30:00+00:00")
    c.append("gate_verdict", {"gate": "offer", "status": "refuse",
                              "reason": "over_cap"},
             ts="2026-10-26T22:30:01+00:00")
    c.append("run_end", {"verdicts": 1}, ts="2026-10-26T22:30:02+00:00")
    return c


def test_chain_verifies():
    assert _chain().verify()


def test_roundtrip_jsonl():
    c = _chain()
    back = ReceiptChain.from_jsonl(c.to_jsonl())
    assert back.verify()
    assert back.to_jsonl() == c.to_jsonl()


def test_tampered_payload_fails():
    c = _chain()
    c.entries[1].payload["reason"] = "unmeasured"
    assert not c.verify()


def test_tampered_order_fails():
    c = _chain()
    c.entries[1], c.entries[2] = c.entries[2], c.entries[1]
    assert not c.verify()


def test_replay_refuses_broken_chain():
    c = _chain()
    c.entries[0].payload["run_id"] = "forged"
    try:
        c.replay()
    except ValueError:
        return
    raise AssertionError("replay of a broken chain must refuse")


def test_verdicts_extracted():
    assert _chain().verdicts() == [
        {"gate": "offer", "status": "refuse", "reason": "over_cap"}
    ]
