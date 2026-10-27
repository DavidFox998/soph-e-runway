# SOPH-E — the agent you can hand money to

**Team:** Pistis Sophia · **Track:** Indie · **Problem statement:** Push the Frontier
**Event:** Meta Global AI Developer Hackathon, Oct 26 – Nov 4, 2026

SOPH-E is a trust-gated shopping agent that runs on **the Runway** — the
scaffold of checkpoints a purchase must cross before money moves. A client
hands SOPH-E a *mandate*: an exact item, a hard budget cap, a deadline. From
that moment the agent may propose, but it may not assert. Every claim it makes
about the world — this is the item, this is the price, this was delivered —
is independently re-measured before it is acted on, and anything unmeasured
is **refused**, not assumed. The refusal is a first-class outcome, not an
error.

## The Runway (five gates)

1. **Mandate gate** — the mandate is parsed into exact, checkable terms:
   item identity and attributes, cap, deadline. Ambiguity refuses.
2. **Offer gate** — a proposed offer is re-measured against the mandate:
   exact item, exact attributes, delivered price. Mismatch refuses.
3. **Payment gate** — payment is prepared only for a passed offer, only
   through a gated rail, only up to the cap. Nothing passes on the agent's
   word.
4. **Delivery gate** — the delivered item is verified from a photo with
   **SAM 3.1**: the mandated item, present and correct, or the delivery is
   refused and the dispute route opens.
5. **Receipt gate** — every gate verdict is appended to a sealed,
   hash-chained, replayable receipt. The receipt is the product: anyone can
   replay the run and re-check every measurement the money moved on.

While SOPH-E works, a **brain layer** keeps a heartbeat over the agent
itself: cognitive probes ride the heartbeat, and the agent's *liveliness* —
response, coherence, continuity, recovery, calibration — is recorded as a
measured profile on the same chain. Liveliness is measured, never asserted.

Method: **G-Ecom Optimization**. Foundation: **Gadiel Alignment Theory
(GAT)** — see `DESIGN.md`.

## Built during the event

This repository is the entry. It was started on Day 0 of the event
(Oct 26, 2026) and everything in it is built inside the event window, in
dated commits. Prior work is used only as a *platform*: the zerobeacon API
(1,052-tool catalogue and its Trust Stack harness) is called as an external
service, exactly as any participant could call a public API; it is not part
of this entry and none of its code is in this repository.

## Layout

- `DESIGN.md` — architecture, the GAT axes, the sealed-core boundary
- `docs/BRAIN-WRAPPER-SPEC.md` — heartbeat + liveliness measurement spec
- `schemas/` — the claim and receipt JSON Schemas
- `src/runway/` — gates, receipt chain, brain wrapper
- `tests/` — the gates and the chain, tested refusal-first

## Status

Day 0: the scaffold (schemas, receipt chain, gate cores, liveliness
profiler) plus **Stage 1 of the build order — the Spark shopper skeleton**:
mandate in, typed claim out, structurally unable to spend. The run wiring,
the live heartbeat and the SAM 3.1 delivery check land per the stage
sequence in `DESIGN.md`.

*Motto: measured, not minted — proven, not asserted.*
