"""Q3 acceptance: feed contract, three-beat run, server smoke."""

import json
import os
import threading
import urllib.request

import pytest

from runway.demo_feed import Feed, FeedError, read_events
from runway.demo_run import run_demo, write_tamper


def _run(tmp_path, auto=True):
    feed_path = str(tmp_path / "events.jsonl")
    feed = Feed(feed_path)
    summary = run_demo(
        feed,
        receipt_path=str(tmp_path / "receipt.jsonl"),
        tamper_path=str(tmp_path / "tamper.json"),
        auto=auto,
    )
    events, head = read_events(feed_path)
    return summary, events


def test_feed_closed_set_is_enforced(tmp_path):
    feed = Feed(str(tmp_path / "e.jsonl"))
    feed.emit("mandate.loaded", {"beat": 1})
    with pytest.raises(FeedError):
        feed.emit("environment.vibes", {})
    events, head = read_events(str(tmp_path / "e.jsonl"), since=0)
    assert head == 1 and events[0]["kind"] == "mandate.loaded"
    events2, _ = read_events(str(tmp_path / "e.jsonl"), since=1)
    assert events2 == []


def test_three_beats_pass_tamper_recovery(tmp_path):
    summary, events = _run(tmp_path)
    outcomes = [b["outcome"] for b in summary["beats"]]
    assert outcomes == ["SETTLED", "REFUSED", "SETTLED"]
    assert summary["beats"][1]["reason"] == "attribute_mismatch:colour"
    assert summary["verified"] is True
    kinds = [e["kind"] for e in events]
    assert "tamper.armed" in kinds and "tamper.flipped" in kinds
    assert kinds[-1] == "receipt.sealed"
    delivery = [e for e in events
                if e["kind"] == "gate.verdict" and e["gate"] == "delivery"]
    assert [d["status"] for d in delivery] == ["pass", "refuse", "pass"]
    assert delivery[1]["failed_attribute"] == "colour"


def test_liveliness_dip_and_recovery_are_computed(tmp_path):
    summary, events = _run(tmp_path)
    prof = summary["profile"]
    # the beat-2 recall really failed and hesitated: continuity dips,
    # recovery is a measured number of beats, calibration carries the
    # overconfident failure
    assert prof["continuity"] is not None and prof["continuity"] < 1.0
    assert prof["recovery_beats"] is not None and prof["recovery_beats"] >= 0
    assert prof["coherence"] is not None and prof["coherence"] < 1.0
    assert prof["control_beats"] >= 2  # unprobed beats, kept separate
    brain_events = [e for e in events if e["kind"] == "brain.beat"]
    assert len(brain_events) >= 3


def test_preset_impostor_flips_from_beat_one(tmp_path):
    tamper = str(tmp_path / "tamper.json")
    write_tamper(tamper, "IMPOSTOR")
    feed = Feed(str(tmp_path / "events.jsonl"))
    summary = run_demo(
        feed, receipt_path=str(tmp_path / "r.jsonl"),
        tamper_path=tamper, auto=False)
    assert summary["beats"][0]["outcome"] == "REFUSED"
    assert summary["beats"][0]["reason"] == "attribute_mismatch:colour"


def test_serve_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("SOPHE_DEMO_DIR", str(tmp_path))
    monkeypatch.setenv("SOPHE_DEMO_DRIVER", "off")
    import importlib
    import sys
    sys.path.insert(0, os.path.join(
        os.path.dirname(__file__), "..", "demo"))
    import serve
    importlib.reload(serve)
    httpd = serve.make_server(0)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "SOPH-E" in html and "Liveliness" in html
        data = json.loads(urllib.request.urlopen(base + "/events?since=0").read())
        assert data == {"events": [], "head": 0}
        req = urllib.request.Request(
            base + "/tamper", method="POST",
            data=json.dumps({"mode": "ARMED"}).encode())
        assert json.loads(urllib.request.urlopen(req).read()) == {"mode": "ARMED"}
        state = json.loads(urllib.request.urlopen(base + "/tamper").read())
        assert state == {"mode": "ARMED"}
    finally:
        httpd.shutdown()
