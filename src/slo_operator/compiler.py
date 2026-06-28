"""Compile a ServiceLevelObjective spec into a PrometheusRule manifest.

This is the heart of the operator and is intentionally pure: given a normalized
spec it returns a deterministic dict, with no Kubernetes API calls. That makes
the SLO-to-rules translation exhaustively unit-testable and keeps reconciles
idempotent (identical input -> byte-identical output -> no rule churn).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .budget import alert_threshold
from .query import render_query
from .windows import SEVERITY_PAGE, ratio_windows, standard_windows

# Metric-name prefix for generated SLI recording rules. The rate window is
# appended (e.g. slo:sli_error:ratio_rate5m).
RECORD_PREFIX = "slo:sli_error:ratio_rate"

# Shared alertname; severity and window labels distinguish individual alerts.
ALERT_NAME = "SLOErrorBudgetBurn"

# Label keys the operator owns on generated rules.
LABEL_SERVICE = "sre_service"
LABEL_SLO = "sre_slo"
LABEL_SEVERITY = "sre_severity"
LABEL_LONG = "sre_long_window"
LABEL_SHORT = "sre_short_window"

# `for:` durations giving alerts a little debounce on top of the short window.
PAGE_FOR = "2m"
TICKET_FOR = "15m"

MANAGED_BY = "slo-operator"


@dataclass
class Compiled:
    """Result of compiling an SLO."""

    manifest: dict[str, Any]
    recording_rules: int = 0
    alerting_rules: int = 0


def recording_metric_name(window: str) -> str:
    return f"{RECORD_PREFIX}{window}"


def rule_name(slo_name: str) -> str:
    """Deterministic PrometheusRule name for an SLO."""
    return f"slo-{slo_name}"


def _fmt(value: float) -> str:
    """Format a float with minimal, stable representation (0.0144, 14.4, 2)."""
    return f"{value:.10g}"


def _matcher(labels: dict[str, str]) -> str:
    """Render a deterministic PromQL label matcher, e.g. {sre_service="api"}."""
    if not labels:
        return ""
    inner = ",".join(f'{k}="{labels[k]}"' for k in sorted(labels))
    return "{" + inner + "}"


def compile_slo(
    name: str,
    namespace: str,
    spec: dict[str, Any],
    rule_labels: dict[str, str] | None = None,
) -> Compiled:
    """Compile a normalized spec into a PrometheusRule manifest.

    `spec` is expected to be the output of validation.validate_spec.
    `rule_labels` are extra labels placed on the PrometheusRule metadata so the
    Prometheus Operator's ruleSelector can discover it.
    """
    objective = float(spec["objective"])
    window = spec["window"]
    description = spec.get("description", "")
    error_query = spec["sli"]["events"]["errorQuery"]
    total_query = spec["sli"]["events"]["totalQuery"]
    user_labels = spec.get("labels", {})
    user_annotations = spec.get("annotations", {})
    alerting = spec.get("alerting", {})

    identity = {LABEL_SERVICE: spec["service"], LABEL_SLO: name}
    base_labels = {**identity, **user_labels}
    matcher = _matcher(identity)

    groups = [_recording_group(name, base_labels, error_query, total_query)]
    recording_count = len(groups[0]["rules"])

    alerting_count = 0
    if not alerting.get("disable", False):
        alert_group = _alert_group(
            name=name,
            service=spec["service"],
            objective=objective,
            window=window,
            description=description,
            matcher=matcher,
            user_labels=user_labels,
            user_annotations=user_annotations,
            page_labels=alerting.get("pageLabels", {}),
            ticket_labels=alerting.get("ticketLabels", {}),
        )
        groups.append(alert_group)
        alerting_count = len(alert_group["rules"])

    metadata_labels = {
        "app.kubernetes.io/managed-by": MANAGED_BY,
        "app.kubernetes.io/part-of": MANAGED_BY,
        LABEL_SERVICE: spec["service"],
        LABEL_SLO: name,
        **(rule_labels or {}),
    }

    manifest = {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "PrometheusRule",
        "metadata": {
            "name": rule_name(name),
            "namespace": namespace,
            "labels": metadata_labels,
        },
        "spec": {"groups": groups},
    }
    return Compiled(
        manifest=manifest,
        recording_rules=recording_count,
        alerting_rules=alerting_count,
    )


def _recording_group(
    name: str, base_labels: dict[str, str], error_query: str, total_query: str
) -> dict[str, Any]:
    rules = []
    for w in ratio_windows():
        expr = (
            f"(\n  {render_query(error_query, w)}\n)\n/\n(\n  {render_query(total_query, w)}\n)"
        )
        rules.append(
            {
                "record": recording_metric_name(w),
                "expr": expr,
                "labels": dict(base_labels),
            }
        )
    return {"name": f"slo-{name}-sli-recordings", "rules": rules}


def _alert_group(
    *,
    name: str,
    service: str,
    objective: float,
    window: str,
    description: str,
    matcher: str,
    user_labels: dict[str, str],
    user_annotations: dict[str, str],
    page_labels: dict[str, str],
    ticket_labels: dict[str, str],
) -> dict[str, Any]:
    rules = []
    for bw in standard_windows():
        threshold = _fmt(alert_threshold(bw.factor, objective))
        long_metric = recording_metric_name(bw.long_window)
        short_metric = recording_metric_name(bw.short_window)
        expr = (
            f"(\n  {long_metric}{matcher} > {threshold}\n"
            f"  and\n"
            f"  {short_metric}{matcher} > {threshold}\n)"
        )

        labels = {
            LABEL_SERVICE: service,
            LABEL_SLO: name,
            LABEL_SEVERITY: bw.severity,
            LABEL_LONG: bw.long_window,
            LABEL_SHORT: bw.short_window,
            **user_labels,
            **(page_labels if bw.severity == SEVERITY_PAGE else ticket_labels),
        }

        desc_suffix = f" {description}" if description else ""
        annotations = {
            "summary": f"SLO {name} ({service}) is burning its error budget",
            "description": (
                f"{service} burn-rate over {bw.long_window}/{bw.short_window} exceeds "
                f"{_fmt(bw.factor)}x, consuming ~{_fmt(bw.budget_consumed_percent)}% of the "
                f"{window} error budget. Objective is {_fmt(objective)}%.{desc_suffix}"
            ),
            **user_annotations,
        }

        rules.append(
            {
                "alert": ALERT_NAME,
                "expr": expr,
                "for": PAGE_FOR if bw.severity == SEVERITY_PAGE else TICKET_FOR,
                "labels": labels,
                "annotations": annotations,
            }
        )
    return {"name": f"slo-{name}-alerts", "rules": rules}
