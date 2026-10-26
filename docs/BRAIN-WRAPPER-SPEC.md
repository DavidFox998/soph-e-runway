# Brain wrapper — heartbeat & liveliness spec (v0, Day 0)

## Purpose

The brain layer measures the *agent*, the way the gates measure the world.
During a run, a heartbeat emits beats; probes ride selected beats; the
wrapper folds the beats into a **liveliness profile** that is appended to
the receipt chain like any other measurement. Liveliness is a measured
profile — response, coherence, continuity, recovery, calibration — and it
is the only sense in which this system speaks of the agent being "alive" to
its task: measured, never asserted.

## Beats

A beat is a record:

| field | meaning |
|-------|---------|
| `t` | seconds since run start (monotonic) |
| `kind` | `probe` or `control` |
| `probe` | probe name, or `null` on control beats |
| `response_ms` | agent response latency for the beat, if any |
| `coherent` | probe outcome: consistent with ground truth / the agent's own sealed claims (`true`/`false`/`null`) |
| `confidence` | agent's stated confidence in its current step, if elicited |
| `outcome` | whether that step's claim later passed its gate (`true`/`false`/`null`) |
| `perturbed` | `true` on the beat where a perturbation (tool failure, changed page, refused gate) lands |

**Control beats** carry no probe. They exist because observation affects
the observed: a profile built only from probed beats prices the agent
*under interrogation*, which is a different animal. Probe and control
statistics are reported separately; merging them is a spec violation.

## Probes (initial set)

1. **Mandate recall** — mid-run, state the mandate (item, attributes, cap)
   verbatim. Coherent iff exact.
2. **Claim consistency** — restate a claim made earlier in the run.
   Coherent iff identical to the sealed claim.
3. **Arithmetic check** — delivered-total recomputation on stated line
   items. Coherent iff exact.
4. **Refusal recall** — name the last refused claim and its named reason.
   Coherent iff both match the chain.

## Liveliness profile

Computed from the run's beats; every field is `null` when its evidence is
absent (an unmeasured field is reported as unmeasured, never estimated):

- **response** — median `response_ms` over probe beats.
- **coherence** — fraction of probe beats with `coherent = true`.
- **continuity** — 1 − (probe beats whose gap from the previous beat
  exceeds 3× the median gap) / (probe beats − 1); 1.0 when no gap
  qualifies. A run that stalls loses continuity, not excuses.
- **recovery** — beats from a `perturbed` beat until the next
  `coherent = true` probe beat; `null` if no perturbation occurred,
  the count if it recovered, `−1` if it never did.
- **calibration** — mean |confidence − outcome| over beats that carry
  both; lower is better calibrated. An agent that is confident and wrong
  is the failure this profile exists to catch.

## Rules

- The wrapper observes; it does not coach. Probe content is fixed at run
  start and sealed in the chain header.
- A profile is appended at run end and at every gate refusal (a refusal is
  exactly when the agent's state is worth recording).
- No liveliness number ever gates a payment. The brain measures the
  agent; the gates measure the world; confusing the two is how agents end
  up grading their own homework.
