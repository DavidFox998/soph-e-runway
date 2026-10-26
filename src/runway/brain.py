"""The brain wrapper: heartbeat beats in, a liveliness profile out.

Implements docs/BRAIN-WRAPPER-SPEC.md. The wrapper observes the agent; it
does not coach it, and no liveliness number ever gates a payment. Every
profile field is None when its evidence is absent — unmeasured is
reported as unmeasured, never estimated.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass
class Beat:
    t: float
    kind: str  # "probe" | "control"
    probe: str | None = None
    response_ms: float | None = None
    coherent: bool | None = None
    confidence: float | None = None
    outcome: bool | None = None
    perturbed: bool = False

    def __post_init__(self) -> None:
        if self.kind not in ("probe", "control"):
            raise ValueError(f"unknown beat kind: {self.kind!r}")


@dataclass
class LivelinessProfile:
    response_ms_median: float | None
    coherence: float | None
    continuity: float | None
    recovery_beats: int | None  # None: no perturbation; -1: never recovered
    calibration_error: float | None
    probe_beats: int
    control_beats: int

    def to_dict(self) -> dict:
        return {
            "response_ms_median": self.response_ms_median,
            "coherence": self.coherence,
            "continuity": self.continuity,
            "recovery_beats": self.recovery_beats,
            "calibration_error": self.calibration_error,
            "probe_beats": self.probe_beats,
            "control_beats": self.control_beats,
        }


def profile(beats: list[Beat]) -> LivelinessProfile:
    probes = [b for b in beats if b.kind == "probe"]
    controls = [b for b in beats if b.kind == "control"]

    responses = [b.response_ms for b in probes if b.response_ms is not None]
    response = statistics.median(responses) if responses else None

    scored = [b for b in probes if b.coherent is not None]
    coherence = (
        sum(1 for b in scored if b.coherent) / len(scored) if scored else None
    )

    continuity = None
    if len(probes) >= 2:
        gaps = [b.t - a.t for a, b in zip(probes, probes[1:])]
        med = statistics.median(gaps)
        if med > 0:
            stalls = sum(1 for g in gaps if g > 3 * med)
            continuity = 1.0 - stalls / len(gaps)
        else:
            continuity = 1.0

    recovery = None
    for i, b in enumerate(beats):
        if b.perturbed:
            recovery = -1
            for j in range(i + 1, len(beats)):
                if beats[j].kind == "probe" and beats[j].coherent:
                    recovery = j - i
                    break
            break

    pairs = [
        (b.confidence, b.outcome)
        for b in beats
        if b.confidence is not None and b.outcome is not None
    ]
    calibration = (
        sum(abs(c - (1.0 if o else 0.0)) for c, o in pairs) / len(pairs)
        if pairs
        else None
    )

    return LivelinessProfile(
        response_ms_median=response,
        coherence=coherence,
        continuity=continuity,
        recovery_beats=recovery,
        calibration_error=calibration,
        probe_beats=len(probes),
        control_beats=len(controls),
    )
