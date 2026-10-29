"""The demo feed (Q3): one JSON object per line, a closed event set.

The demo UI consumes ONLY this feed — it never imports runway
modules. The environment side appends; the server side reads with
`since=` cursors. An event outside the closed set is a code error:
the feed is a contract, not a log file.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

EVENT_KINDS = {
    "mandate.loaded",
    "claim.proposed",
    "gate.verdict",
    "brain.beat",
    "delivery.photo",
    "tamper.armed",
    "tamper.flipped",
    "receipt.appended",
    "receipt.sealed",
}


class FeedError(Exception):
    pass


class Feed:
    def __init__(self, path: str):
        self.path = path
        self._seq = 0
        self._lock = threading.Lock()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self._seq = sum(1 for _ in f)

    def emit(self, kind: str, payload: dict) -> dict:
        if kind not in EVENT_KINDS:
            raise FeedError(f"event kind {kind!r} is not in the closed set")
        with self._lock:
            self._seq += 1
            event = {
                "seq": self._seq,
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                **payload,
            }
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, sort_keys=True) + "\n")
            return event


def read_events(path: str, since: int = 0) -> tuple[list[dict], int]:
    """Events with seq > since, plus the current head seq."""
    events: list[dict] = []
    head = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                head = max(head, int(ev.get("seq", 0)))
                if int(ev.get("seq", 0)) > since:
                    events.append(ev)
    return events, head
