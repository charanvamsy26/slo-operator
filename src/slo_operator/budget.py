"""Error-budget math. Pure functions, no I/O — trivially unit-testable."""

from __future__ import annotations


def allowed_error_ratio(objective: float) -> float:
    """Fraction of requests allowed to fail while still meeting the objective.

    e.g. an objective of 99.9 yields 0.001.
    """
    return 1 - objective / 100


def burn_rate(error_ratio: float, objective: float) -> float:
    """How fast the error budget is being consumed relative to a sustainable pace.

    1.0 means the budget will be exactly exhausted by the end of the window;
    14.4 means it would be gone in ~1/14.4 of the window.
    """
    allowed = allowed_error_ratio(objective)
    if allowed <= 0:
        return 0.0
    return error_ratio / allowed


def remaining_budget_percent(error_ratio: float, objective: float) -> float:
    """Percentage of error budget still available; negative once breached."""
    allowed = allowed_error_ratio(objective)
    if allowed <= 0:
        return 0.0
    consumed = error_ratio / allowed
    return (1 - consumed) * 100


def alert_threshold(factor: float, objective: float) -> float:
    """Error-ratio value an alert compares against: factor * allowed error ratio."""
    return factor * allowed_error_ratio(objective)
