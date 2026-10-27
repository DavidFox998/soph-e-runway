"""Gate 0 (sellers): profile arithmetic and verdict discipline.
Every rate is computed from measured records only; unmeasured axes
do not vote; a short clean history still refuses."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402

from runway.sellers import (SellerRecord, SellerThresholds,  # noqa: E402
                            gate_seller, seller_profile)


def rec(seller="s", price=(1000, 1000), attrs=True, src="r"):
    pa, pm = price if price is not None else (None, None)
    return SellerRecord(seller_id=seller, source=src,
                        price_asserted=pa, price_measured=pm,
                        attributes_ok=attrs)


def test_profile_rates_and_means():
    records = [rec(price=(1000, 1000)), rec(price=(1000, 1200)),
               rec(price=(2000, 2000)), rec(price=(2000, 1500))]
    p = seller_profile(records)
    assert p.price_measured_count == 4
    assert p.price_drift_count == 2
    assert p.price_drift_rate == 0.5
    assert p.mean_abs_drift_cents == 350.0


def test_unmeasured_axes_report_none_not_zero():
    records = [rec(price=None, attrs=None) for _ in range(4)]
    p = seller_profile(records)
    assert p.price_drift_rate is None
    assert p.attribute_mismatch_rate is None
    assert p.records == 4


def test_mixed_sellers_and_empty_raise():
    with pytest.raises(ValueError):
        seller_profile([rec(seller="a"), rec(seller="b")])
    with pytest.raises(ValueError):
        seller_profile([])


def test_clean_history_passes():
    records = [rec() for _ in range(6)]
    v = gate_seller(records)
    assert v.status == "pass" and v.gate == "seller" and v.reason is None


def test_short_clean_history_refuses_insufficient():
    v = gate_seller([rec() for _ in range(2)])
    assert v.status == "refuse" and v.reason == "insufficient_history"


def test_drift_refuses_and_is_checked_before_attributes():
    records = [rec(price=(1000, 1000), attrs=True),
               rec(price=(1000, 1400), attrs=False),
               rec(price=(1000, 1400), attrs=False),
               rec(price=(1000, 1000), attrs=True)]
    v = gate_seller(records)
    assert v.status == "refuse" and v.reason == "seller_price_drift"


def test_mismatch_refuses():
    records = [rec(attrs=True), rec(attrs=False),
               rec(attrs=False), rec(attrs=True), rec(attrs=True)]
    v = gate_seller(records)
    assert v.status == "refuse" and v.reason == "seller_attribute_mismatch"


def test_unmeasured_price_axis_does_not_vote():
    # attributes-only history: passes on the attribute axis alone
    records = [rec(price=None, attrs=True) for _ in range(5)]
    assert gate_seller(records).status == "pass"
    # and cannot be refused for drift it never had measured
    records = [rec(price=None, attrs=False), rec(price=None, attrs=True),
               rec(price=None, attrs=True), rec(price=None, attrs=True)]
    assert gate_seller(records).status == "pass"


def test_thresholds_are_parameters_not_constants():
    records = [rec(price=(1000, 1100)), rec(price=(1000, 1000)),
               rec(price=(1000, 1000)), rec(price=(1000, 1000))]
    strict = SellerThresholds(max_price_drift_rate=0.10)
    assert gate_seller(records, strict).reason == "seller_price_drift"
    assert gate_seller(records).status == "pass"
