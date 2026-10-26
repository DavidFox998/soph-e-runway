from runway.brain import Beat, profile


def test_empty_profile_is_unmeasured_not_zero():
    p = profile([])
    assert p.coherence is None
    assert p.calibration_error is None
    assert p.recovery_beats is None
    assert p.probe_beats == 0 and p.control_beats == 0


def test_profile_measures_what_it_claims():
    beats = [
        Beat(t=0.0, kind="control"),
        Beat(t=1.0, kind="probe", probe="mandate_recall",
             response_ms=120.0, coherent=True, confidence=0.9, outcome=True),
        Beat(t=2.0, kind="probe", probe="claim_consistency",
             response_ms=200.0, coherent=False, confidence=0.9,
             outcome=False, perturbed=True),
        Beat(t=3.0, kind="probe", probe="arithmetic",
             response_ms=160.0, coherent=True),
    ]
    p = profile(beats)
    assert p.probe_beats == 3 and p.control_beats == 1
    assert p.response_ms_median == 160.0
    assert abs(p.coherence - 2 / 3) < 1e-9
    assert p.recovery_beats == 1  # perturbed at idx 2, coherent again at idx 3
    # |0.9-1| and |0.9-0| -> (0.1 + 0.9) / 2
    assert abs(p.calibration_error - 0.5) < 1e-9


def test_unrecovered_perturbation_is_minus_one():
    beats = [Beat(t=0.0, kind="probe", coherent=False, perturbed=True)]
    assert profile(beats).recovery_beats == -1
