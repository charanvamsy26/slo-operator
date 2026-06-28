"""Burn-rate window definitions from the Google SRE workbook.

Kept free of any Kubernetes/kopf imports so the tables can be unit-tested in
isolation and reused by both the compiler and the documentation generator.
"""

from __future__ import annotations

from dataclasses import dataclass

# Severity levels attached to generated alerts.
SEVERITY_PAGE = "page"
SEVERITY_TICKET = "ticket"

# The only SLO compliance window currently supported.
SUPPORTED_WINDOW = "30d"


@dataclass(frozen=True)
class BurnRateWindow:
    """One multi-window burn-rate alert.

    An alert fires only when the error ratio exceeds the threshold over BOTH the
    long and short windows. The long window establishes a sustained burn; the
    short window confirms it is still happening, which makes alerts both
    fast-reacting and resistant to flapping.
    """

    severity: str
    long_window: str
    short_window: str
    factor: float
    # How much of a 30d budget `factor` consumes over `long_window`; surfaced in
    # alert annotations for human context.
    budget_consumed_percent: float


def standard_windows() -> list[BurnRateWindow]:
    """Return the canonical four-tier MWMB alert windows for a 30-day SLO."""
    return [
        BurnRateWindow(SEVERITY_PAGE, "1h", "5m", 14.4, 2),
        BurnRateWindow(SEVERITY_PAGE, "6h", "30m", 6, 5),
        BurnRateWindow(SEVERITY_TICKET, "1d", "2h", 3, 10),
        BurnRateWindow(SEVERITY_TICKET, "3d", "6h", 1, 10),
    ]


def ratio_windows() -> list[str]:
    """Every distinct rate window referenced by the burn-rate alerts.

    One recording rule is generated per window so alert expressions are cheap
    label lookups rather than repeated rate() evaluations.
    """
    return ["5m", "30m", "1h", "2h", "6h", "1d", "3d"]
