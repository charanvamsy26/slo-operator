"""Optional Prometheus HTTP API client used to compute live error budgets.

Only used when the operator is started with --prometheus-url. The client is
deliberately tiny (instant queries via the HTTP API) and isolated behind a small
surface so the budget timer can be tested with a fake.
"""

from __future__ import annotations

import requests

from .query import render_query


class PrometheusError(RuntimeError):
    """Raised when a Prometheus query fails or returns an unusable result."""


class PrometheusClient:
    """Minimal Prometheus query client (instant queries only)."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def query_scalar(self, expr: str) -> float | None:
        """Run an instant query and return a single float, or None if no data."""
        resp = requests.get(
            f"{self.base_url}/api/v1/query",
            params={"query": expr},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") != "success":
            raise PrometheusError(f"query failed: {payload.get('error', 'unknown error')}")
        return _extract_scalar(payload.get("data", {}))

    def error_ratio(self, error_query: str, total_query: str, window: str) -> float | None:
        """Compute bad/total over the SLO window. Returns None if total is empty."""
        total = self.query_scalar(render_query(total_query, window))
        if total is None or total == 0:
            return None
        errors = self.query_scalar(render_query(error_query, window)) or 0.0
        return errors / total


def _extract_scalar(data: dict) -> float | None:
    """Pull a single numeric value out of a Prometheus query result."""
    result_type = data.get("resultType")
    result = data.get("result")
    if result_type == "scalar":
        # result is [timestamp, "value"]
        return float(result[1])
    if result_type == "vector":
        if not result:
            return None
        return float(result[0]["value"][1])
    return None
