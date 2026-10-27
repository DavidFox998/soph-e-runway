"""The mandate parser (Q4): model proposes, validator disposes.

Doctrine: Spark may *propose* a structured mandate from free text, but
nothing reaches the gates on the model's say-so. A deterministic
validator re-checks every field against the source text itself:

- The cap must appear in the text **as digits** ($40, 40 dollars).
  A cap expressed in words ("under forty bucks") is REFUSED with
  FUZZY_CAP — David's ratified strictness (2026-10-26): no
  word-to-number conversion, ever. If the model's number disagrees
  with the digits in the text, that is SCHEMA_VIOLATION.
- The deadline must be an absolute ISO date **present in the text**.
  "by Friday" is RELATIVE_DEADLINE; no date at all is
  MISSING_DEADLINE; a past date is PAST_DEADLINE. No defaults, no
  week-guessing.
- Every attribute value must appear verbatim in the text. An
  attribute the user never typed is an invention: UNCLEAR_ATTRIBUTE.
- A vague item ("a nice kettle") is VAGUE_ITEM.

Malformed model replies emit NO mandate (the shopper.py precedent).
Both outcomes — parsed and refused — are hash-chained when a chain
is supplied.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from .client import ProposalError
from .gates import Mandate
from .receipts import ReceiptChain

CODES = (
    "VAGUE_ITEM", "MISSING_CAP", "FUZZY_CAP", "RELATIVE_DEADLINE",
    "MISSING_DEADLINE", "PAST_DEADLINE", "UNCLEAR_ATTRIBUTE",
    "SCHEMA_VIOLATION",
)

VAGUE_WORDS = {
    "nice", "good", "great", "quality", "decent", "some", "any",
    "cheap", "best", "fancy", "nice-looking",
}
NUMBER_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
    "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
    "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred", "thousand",
}
RELATIVE_WORDS = {
    "friday", "monday", "tuesday", "wednesday", "thursday",
    "saturday", "sunday", "tomorrow", "tonight", "weekend",
    "asap", "soon", "next", "eow", "eod",
}
CAP_DIGITS_RE = re.compile(
    r"\$\s*(\d+(?:\.\d{1,2})?)|(\d+(?:\.\d{1,2})?)\s*(?:dollars|usd)\b",
    re.IGNORECASE,
)


class MandateProposer(Protocol):
    def complete(self, prompt: str) -> str:
        ...


@dataclass
class StubProposer:
    """Canned proposer for tests: returns the reply verbatim."""

    reply: str

    def complete(self, prompt: str) -> str:
        return self.reply


@dataclass(frozen=True)
class ParsedMandate:
    item_identity: str
    required_attributes: tuple[tuple[str, str], ...]
    price_cap_cents: int
    deadline: date

    def to_mandate(self) -> Mandate:
        return Mandate(
            item=self.item_identity,
            attributes=dict(self.required_attributes),
            cap_cents=self.price_cap_cents,
        )


@dataclass(frozen=True)
class ParseRefusal:
    codes: tuple[str, ...]
    detail: str


_PROMPT = (
    "Extract a shopping mandate from the user's text as JSON only, "
    "with keys: \"item\" (string or null), \"attributes\" (object of "
    "string->string), \"price_cap_cents\" (integer or null), "
    "\"deadline\" (ISO date string YYYY-MM-DD or null), "
    "\"unresolved\" (array of strings). Rules: copy numbers ONLY as "
    "digits that literally appear in the text; copy the deadline ONLY "
    "if an ISO date literally appears; copy attribute values ONLY "
    "verbatim from the text; anything not explicit goes in "
    "\"unresolved\" naming the field. Never convert words to numbers. "
    "Never invent. Text: "
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _schema_decode(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if set(data.keys()) != {
        "item", "attributes", "price_cap_cents", "deadline", "unresolved"
    }:
        return None
    if not isinstance(data["attributes"], dict):
        return None
    if not isinstance(data["unresolved"], list):
        return None
    return data


def _digit_cap_cents(text: str) -> int | None:
    m = CAP_DIGITS_RE.search(text)
    if not m:
        return None
    val = m.group(1) or m.group(2)
    return int(round(float(val) * 100))


def _validate(text: str, data: dict, today: date) -> list[str]:
    codes: list[str] = []
    lower = text.lower()

    def add(code: str) -> None:
        if code not in codes:
            codes.append(code)

    # The model's own honesty array forces the named fields' codes.
    for entry in data["unresolved"]:
        e = str(entry).lower()
        if "item" in e:
            add("VAGUE_ITEM")
        elif "cap" in e or "price" in e or "budget" in e:
            add("FUZZY_CAP")
        elif "deadline" in e or "date" in e:
            add("MISSING_DEADLINE")
        elif "attribute" in e:
            add("UNCLEAR_ATTRIBUTE")

    # Item: present, non-empty, free of vague qualifiers.
    item = data["item"]
    if not item or not str(item).strip():
        add("VAGUE_ITEM")
    elif any(w in str(item).lower().split() for w in VAGUE_WORDS):
        add("VAGUE_ITEM")

    # Cap: digits in the text are the only authority.
    digit_cap = _digit_cap_cents(text)
    model_cap = data["price_cap_cents"]
    if digit_cap is None:
        words = set(re.findall(r"[a-z]+", lower))
        if words & NUMBER_WORDS or "bucks" in words:
            add("FUZZY_CAP")
        else:
            add("MISSING_CAP")
    else:
        if model_cap is None:
            add("MISSING_CAP")
        elif not isinstance(model_cap, int) or isinstance(model_cap, bool):
            add("SCHEMA_VIOLATION")
        elif model_cap != digit_cap:
            add("SCHEMA_VIOLATION")  # model converted or invented
        elif model_cap <= 0:
            add("SCHEMA_VIOLATION")

    # Deadline: an absolute ISO date, present in the text, not past.
    model_deadline = data["deadline"]
    if model_deadline is None:
        words = set(re.findall(r"[a-z]+", lower))
        if words & RELATIVE_WORDS:
            add("RELATIVE_DEADLINE")
        else:
            add("MISSING_DEADLINE")
    else:
        try:
            parsed = date.fromisoformat(str(model_deadline))
        except ValueError:
            add("SCHEMA_VIOLATION")
        else:
            if str(model_deadline) not in text:
                add("RELATIVE_DEADLINE")  # model resolved a relative date
            elif parsed < today:
                add("PAST_DEADLINE")

    # Attributes: every value verbatim in the text, or it is invented.
    for key, value in data["attributes"].items():
        if str(value).lower() not in lower:
            add("UNCLEAR_ATTRIBUTE")

    return codes


def parse_mandate(text: str, *, today: date, spark_client,
                  chain: ReceiptChain | None = None,
                  ts: str | None = None) -> ParsedMandate | ParseRefusal:
    """Free text in; ParsedMandate or ParseRefusal out. Downstream
    only ever receives the former."""
    norm = normalize(text)
    text_hash = hashlib.sha256(norm.encode()).hexdigest()

    def record(outcome: str, payload_extra: dict) -> None:
        if chain is not None:
            chain.append("claim", {
                "op": "PARSE_PROPOSED", "text_hash": text_hash,
                **payload_extra,
            }, ts=ts)
            status = "pass" if outcome == "parsed" else "refuse"
            chain.append("gate_verdict", {
                "op": "PARSE_VERDICT", "gate": "parse", "status": status,
                "reason": (payload_extra.get("codes") or [None])[0]
                if status == "refuse" else None,
                "codes": payload_extra.get("codes", []),
            }, ts=ts)

    try:
        raw = spark_client.complete(_PROMPT + norm)
    except ProposalError as exc:
        refusal = ParseRefusal(("SCHEMA_VIOLATION",), f"proposer failed: {exc}")
        record("refused", {"codes": list(refusal.codes)})
        return refusal

    data = _schema_decode(raw)
    if data is None:
        refusal = ParseRefusal(
            ("SCHEMA_VIOLATION",), "model reply is not the strict schema")
        record("refused", {"codes": list(refusal.codes)})
        return refusal

    codes = _validate(norm, data, today)
    if codes:
        refusal = ParseRefusal(tuple(codes), "validator refused the proposal")
        record("refused", {"codes": list(codes)})
        return refusal

    parsed = ParsedMandate(
        item_identity=str(data["item"]).strip(),
        required_attributes=tuple(
            sorted((str(k), str(v)) for k, v in data["attributes"].items())
        ),
        price_cap_cents=int(data["price_cap_cents"]),
        deadline=date.fromisoformat(str(data["deadline"])),
    )
    record("parsed", {"item": parsed.item_identity})
    return parsed
