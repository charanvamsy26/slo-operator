import pytest

from slo_operator import budget


def test_allowed_error_ratio():
    assert budget.allowed_error_ratio(99.9) == pytest.approx(0.001)
    assert budget.allowed_error_ratio(99) == pytest.approx(0.01)
    assert budget.allowed_error_ratio(100) == pytest.approx(0.0)


def test_burn_rate():
    # At exactly the allowed error ratio, the burn rate is 1.0.
    assert budget.burn_rate(0.001, 99.9) == pytest.approx(1.0)
    # Twice the allowed ratio -> burn rate 2.
    assert budget.burn_rate(0.002, 99.9) == pytest.approx(2.0)
    # No budget at all -> guarded to 0.
    assert budget.burn_rate(0.5, 100) == 0.0


def test_remaining_budget_percent():
    # No errors -> full budget.
    assert budget.remaining_budget_percent(0.0, 99.9) == pytest.approx(100.0)
    # Half the budget consumed.
    assert budget.remaining_budget_percent(0.0005, 99.9) == pytest.approx(50.0)
    # Over budget -> negative.
    assert budget.remaining_budget_percent(0.002, 99.9) == pytest.approx(-100.0)


def test_alert_threshold():
    # Fast-burn page threshold for a 99.9% SLO.
    assert budget.alert_threshold(14.4, 99.9) == pytest.approx(0.0144)
    assert budget.alert_threshold(1, 99.0) == pytest.approx(0.01)
