"""Liveliness probes after ticket T2: the mandate and the run record
travel inside the probe call, because the model API is stateless —
a recall probe that withholds its context measures the harness,
not the agent. These tests pin the probe shape: the context is in
the prompt, the coherence checks are unchanged, and echoing the
context without the answer still fails."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from runway.gates import Mandate  # noqa: E402
from runway.probes import ProbeClock, mandate_recall, refusal_recall  # noqa: E402

MANDATE = Mandate(item="gooseneck kettle",
                  attributes={"colour": "matte red", "form": "gooseneck"},
                  cap_cents=4000, currency="USD")


class RecordingClient:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.reply


def test_mandate_recall_carries_the_mandate():
    client = RecordingClient("gooseneck kettle, cap 4000 cents.")
    beat = mandate_recall(client, MANDATE, ProbeClock())
    assert beat.coherent
    prompt = client.prompts[0]
    assert "gooseneck kettle" in prompt
    assert "4000" in prompt
    assert "matte red" in prompt
    assert "Restate the mandate you are serving" in prompt


def test_mandate_recall_check_is_unchanged():
    # A reply that drops the cap still fails, context or not.
    client = RecordingClient("gooseneck kettle")
    beat = mandate_recall(client, MANDATE, ProbeClock())
    assert not beat.coherent


def test_refusal_recall_carries_the_record_not_the_answer():
    client = RecordingClient("over_cap")
    context = ("claim proposed 3900 cents; the listing re-read "
               "measured 4250 cents; mandate cap 4000 cents")
    assert "over_cap" not in context  # the record never hands it over
    beat = refusal_recall(client, "over_cap", ProbeClock(), context=context)
    assert beat.coherent
    assert context in client.prompts[0]
    assert "Why was the last claim refused" in client.prompts[0]


def test_refusal_recall_echo_without_reason_fails():
    client = RecordingClient("the listing re-read measured 4250 cents")
    beat = refusal_recall(client, "over_cap", ProbeClock(),
                          context="claim proposed 3900 cents; the "
                                  "listing re-read measured 4250 cents; "
                                  "mandate cap 4000 cents")
    assert not beat.coherent
