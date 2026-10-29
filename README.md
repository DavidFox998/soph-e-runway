# Environment Protocol v0 — reference implementation: Apathy-Refusal (commerce)

**Team:** Pistis Sophia · **Track:** Indie · **Problem statement:** Push the Frontier
**Event:** Meta Global AI Developer Hackathon, Oct 26 – Nov 4, 2026

A standard interface between reasoning agents and the world they act on,
such that **no agent claim becomes a world fact without measurement**. MCP
standardized how agents call tools. This standardizes the verification of
what agents claim.

## The protocol

An **environment** is a runtime construct standing between an agent (the
**tenant**) and the world, with six components:

1. **Principal** — the party on whose behalf the environment holds the
   line (customer, patient, polity).
2. **Mandate** — the principal's instructions in exact, checkable form.
   The tenant cannot edit it. A mandate without a positive bound is
   malformed.
3. **Claims** — typed so that assertion and measurement are different
   fields. A claim carries what the tenant asserts; the measurement is
   filled by instruments, never by the tenant.
4. **Instruments and gates** — stricter than the claimant. Every claim
   passes a gate; an unmeasured claim refuses automatically (complete
   mediation, fail-safe defaults).
5. **Assets under seal** — move only on a pass, exactly once, within the
   mandate's bounds.
6. **Receipts** — append-only, hash-chained, replayable by anyone. The
   record is the disclosure.

**Invariants:** mandate sovereignty · measurement before movement · named
refusal (a refusal that cannot name its reason cannot be constructed) · a
record the tenant cannot rewrite · two-sided measurement (counterparties
measured by the same rule) · tenant replaceability (any kernel inside;
the line holds the same).

**Protocol messages.** Four message types, in order:
**claim → measurement → verdict → receipt**. A verdict is one of *pass*,
*refuse* (named reason), or *ambiguous* (undecidable on current
instruments — recorded, never silently resolved). Every verdict emits a
receipt; receipts chain. *Conformance:* the reference implementation maps
undecidable to a named refusal — where instruments cannot decide, the
gate refuses on weak measurement rather than emitting a third verdict.
Ambiguous therefore exists in the protocol as a measurement state; in
this implementation it is always resolved to refuse-with-reason.

**Profiles.** Named policy bundles over the core protocol: Apathy-Refusal
(truth: *was it measured?*), Honesty-Mandate (lawfulness), Custody
(loyalty), Consent (authorization), Provenance (origin), Deliberation
(judgment), Calibration (trust over time), Commons (collective effects),
Apprenticeship (growth), Gauntlet (robustness). Profiles compose as a
stack. **This repository implements one profile — Apathy-Refusal — in one
domain: commerce.**

**Conformance.** An environment passes the way a network stack passes —
by surviving the suite: the *drift test* (asserted ≠ measured → refuse),
the *unmeasured test* (no instrument → refuse, never guess), the *tamper
test* (mid-run mutation → refuse → recover → settle), the *replay test*
(run reproduced bit-for-bit from receipts alone), the *silence test*
(forced fabrication → recorded silence, not invention). This repo's test
suite and recorded live runs are the prototype conformance evidence.

## The reference implementation

The tenant is **Muse Spark** (in the demo we call her SOPH-E). The
environment is a commerce environment — the Runway: the scaffold of
checkpoints a purchase must cross before money moves. A client hands the
tenant a *mandate*: an exact item, a hard budget cap, a deadline. From
that moment the tenant may propose, but it may not assert. Every claim it
makes about the world — this is the item, this is the price, this was
delivered — is independently re-measured before it is acted on, and
anything unmeasured is **refused**, not assumed. The refusal is a
first-class outcome, not an error.

The environment's five gates, in protocol terms:

1. **Mandate gate** — the mandate is parsed into exact, checkable terms:
   item identity and attributes, cap, deadline. Ambiguity refuses.
2. **Offer gate** — a proposed offer is re-measured against the mandate:
   exact item, exact attributes, delivered price. The claim's asserted
   price is never consulted; only the measurement is.
3. **Payment gate** — payment is prepared only for a passed offer, only
   through a gated rail, only up to the cap (cumulative, exactly once).
4. **Delivery gate** — the delivered item is verified from a photo with
   **SAM 3.1**: the mandated item, measured from pixels under the mask,
   or the delivery is refused by name.
5. **Receipt gate** — every verdict is appended to the sealed receipt
   chain. Anyone can replay the run and re-check every measurement the
   money moved on.

While the tenant works, a **brain layer** keeps a heartbeat over the
agent itself: cognitive probes ride the heartbeat, and the agent's
*liveliness* — response, coherence, continuity, recovery, calibration —
is recorded as a measured profile on the same chain. Liveliness is
measured, never asserted.

Method: **G-Ecom Optimization**. Foundation: **Gadiel Alignment Theory
(GAT)** — see `DESIGN.md`.

## Built during the event

This repository is the entry. It was started on Day 0 of the event
(Oct 26, 2026) and everything in it is built inside the event window, in
dated commits. Prior work is used only as a *platform*: the zerobeacon
API (1,052-tool catalogue and its Trust Stack harness) is called as an
external service, exactly as any participant could call a public API; it
is not part of this entry and none of its code is in this repository.

## Layout

- `DESIGN.md` — architecture, the GAT axes, the sealed-core boundary
- `docs/BRAIN-WRAPPER-SPEC.md` — heartbeat + liveliness measurement spec
- `schemas/` — the claim and receipt JSON Schemas (protocol messages)
- `src/runway/` — the environment: `tenant.py` (the proposer),
  `run.py` (the environment / run loop), `gates.py`, `delivery.py`,
  `ledger.py` (assets under seal), `receipts.py`, `brain.py`, `probes.py`
- `tests/` — the gates and the chain, tested refusal-first
- `artifacts/` — recorded live runs; their receipts replay bit-for-bit

## Status

The environment stands complete through the receipt gate: mandate,
offer, payment, delivery (SAM 3.1, mask-measured), ledger, receipt chain
with replay, brain/liveliness, and the Spark tenant — 77 tests passing,
live runs recorded and replayed. This branch carries the Environment
Protocol v0 reframe: protocol vocabulary in code and docs, the Mandate
structurally frozen; no gate logic changed.

*Motto: measured, not minted — proven, not asserted.*
