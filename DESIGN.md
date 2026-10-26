# SOPH-E / Runway — design notes

## Foundation: Gadiel Alignment Theory (GAT)

The build rests on **Gadiel Alignment Theory (GAT)**: an agent entrusted
with a client's money is aligned exactly to the extent that its actions are
gated on two axes, and on nothing else:

- **Axis 1 — Client financial well-being.** No action may leave the client
  worse off than the mandate allows: hard cap, no duplicate charges, no
  payment without a passed measurement. Enforced at the Offer and Payment
  gates.
- **Axis 2 — Client preferences.** The client asked for *this* item with
  *these* attributes — not a near substitute, not a plausible one. Exact
  match or refusal. Enforced at the Mandate, Offer and Delivery gates;
  the exactness standard is sharpest at Gate 4, where a photograph, not a
  listing, is the evidence.

A gate that cannot measure must refuse. That single rule — *unmeasured ⇒
refused* — is the whole theory in operational form.

*(Easter egg, with a paper trail: the name is an old one. The theory keeps
the name because the build keeps the discipline — a guardian that measures
before it acts.)*

## The public method: G-Ecom Optimization

The Runway applies GAT to commerce: a purchase is a sequence of claims, and
each claim is optimized — in the only sense that matters — by being
re-measured before it is paid for.

## Components

### Claims (`schemas/claim.schema.json`)

Everything the agent wants the system to believe is a **claim**: a typed,
attributed assertion with the evidence it rests on and the verdict it
received. A claim with no measurement has no path to a payment.

### Gates (`src/runway/gates.py`)

Each gate is a function from (claim, independent measurement) to a verdict:
`PASS` with the measurement attached, or `REFUSE` with a named reason.
Gates never see the agent's confidence; they see measurements.

| Gate | Claim checked | Measurement | Refusal examples |
|------|---------------|-------------|------------------|
| 1 Mandate | "this mandate is exact" | parse to item/attributes/cap/deadline | ambiguity, no cap |
| 2 Offer | "this offer is the mandated item at this price" | re-read offer: identity, attributes, delivered total | wrong item, over cap, unmeasured |
| 3 Payment | "pay exactly this, once" | gated rail quote + mandate ledger | over cap, duplicate, rail unmeasured |
| 4 Delivery | "the mandated item arrived" | SAM 3.1 segmentation of the delivery photo vs mandate attributes | impostor item, attribute mismatch, unmeasured |
| 5 Receipt | "the run is replayable" | hash-chain verification over all verdicts | broken chain, missing verdict |

Gate 4 test discipline: a fixed set of true delivery photos and named
impostors (wrong colour, wrong form factor, wrong item, box-only). The gate
must pass the true set and refuse every impostor; a tuning change that
admits one impostor fails the set.

Gate 4 sits behind a **swappable verifier interface** (landed Day 0,
`src/runway/delivery.py`): the gate consumes a Measurement and never cares
which backend produced it; the agent never supplies Gate 4's measurement —
the gate calls the verifier itself. A stub verifier carries the loop today;
the SAM 3.1 API verifier ships unconfigured (⇒ refuses `unmeasured`) until
Appendix A verifies the hosted endpoint, and a self-host smoke test on GPU
box time is the fallback track, not the plan of record: per the Official
Rules, SAM 3.1 is a hosted Standard model on the Meta Model API.

Demo mandate: a **matte red gooseneck kettle**, **$40 cap**.

### Sandbox ledger rail

Money in the demo moves on an **offline sandbox ledger**: the mandate opens
a ledger account capped at the mandate amount; a passed Payment gate moves
funds from the client's ledger to the merchant's; a refused delivery moves
them back. The ledger is append-only and its entries are receipt-chain
payloads, so the money trail and the proof trail are the same trail.

### Brain layer (`docs/BRAIN-WRAPPER-SPEC.md`)

A heartbeat wraps the agent during a run. Probes — small cognitive checks
with known answers, consistency checks across the agent's own claims,
recall of the mandate mid-run — ride the heartbeat. The wrapper records a
**liveliness profile**: response, coherence, continuity, recovery,
calibration. Unprobed **control beats** interleave with probe beats so the
measurement can price its own perturbation: observation affects the
observed, so the profile reports probe and control beats separately and
never merges them into a single flattering number.

### Receipt chain (`src/runway/receipts.py`, `schemas/receipt.schema.json`)

Append-only, hash-chained (SHA-256 over canonical JSON), replayable. Every
gate verdict, ledger movement and heartbeat profile is an entry. Replay
recomputes the chain and re-derives the run's verdicts; a chain that does
not verify, refuses.

## Boundaries

- **Sealed core stays sealed.** Allocation internals of the platform the
  agent calls are not part of this entry, are not in this repository, and
  are not described beyond their public interface. What is published is
  the format and the verification; issuance stays where it belongs.
- **Prior work is platform, not entry.** zerobeacon (API + Trust Stack
  harness) predates the event and is called over its public API. This
  repository contains only event-window work.
- **Standard models only.** Muse Spark, SAM 3.1, Muse Image, Muse Wonder —
  Standard tier throughout; nothing Contributor-tier touches the build.

## Build order (event window)

1. Day 0 — scaffold, claim + receipt schemas, receipt chain, brain spec. ✅
2. Gates 1–3 with the sandbox ledger rail; refusal-first tests.
3. Gate 4: delivery photo set (true + named impostors), SAM 3.1 check.
4. End-to-end loop on the demo mandate; brain wrapper live on the run.
5. Gate 5 replay + receipt export; demo hardening.
6. Freeze, rehearse, submit (deadline Nov 4, 9:00 PM ET).
