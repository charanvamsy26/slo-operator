"""Spec validation and normalization for ServiceLevelObjective resources.

The CRD's openAPIV3Schema enforces structure and basic bounds, but this module
provides the semantic checks (placeholder presence, exclusive bounds) and applies
defaults. Handlers raise these errors as permanent so kopf does not hot-loop on
an object that can never be valid.
"""

from __future__ import annotations

from typing import Any

from .query import PLACEHOLDER, has_window_placeholder
from .windows import SUPPORTED_WINDOW


class SpecError(ValueError):
    """Raised when a ServiceLevelObjective spec is invalid."""


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a raw spec dict and return a normalized copy with defaults applied.

    Raises SpecError on any problem.
    """
    if not isinstance(spec, dict):
        raise SpecError("spec must be a mapping")

    service = spec.get("service")
    if not service or not isinstance(service, str):
        raise SpecError("spec.service is required and must be a non-empty string")

    objective = spec.get("objective")
    if not isinstance(objective, (int, float)) or isinstance(objective, bool):
        raise SpecError("spec.objective is required and must be a number")
    if not (0 < float(objective) < 100):
        raise SpecError(f"spec.objective must be between 0 and 100 (exclusive), got {objective}")

    window = spec.get("window") or SUPPORTED_WINDOW
    if window != SUPPORTED_WINDOW:
        raise SpecError(
            f"spec.window {window!r} is unsupported; only {SUPPORTED_WINDOW!r} is allowed"
        )

    sli = spec.get("sli")
    if not isinstance(sli, dict):
        raise SpecError("spec.sli is required")
    events = sli.get("events")
    if not isinstance(events, dict):
        raise SpecError("spec.sli.events is required")

    error_query = events.get("errorQuery")
    total_query = events.get("totalQuery")
    for name, q in (("errorQuery", error_query), ("totalQuery", total_query)):
        if not q or not isinstance(q, str):
            raise SpecError(f"spec.sli.events.{name} is required and must be a non-empty string")
        if not has_window_placeholder(q):
            raise SpecError(
                f"spec.sli.events.{name} must contain the {PLACEHOLDER} placeholder"
            )

    normalized = {
        "service": service,
        "objective": float(objective),
        "window": window,
        "description": spec.get("description", ""),
        "sli": {"events": {"errorQuery": error_query, "totalQuery": total_query}},
        "labels": dict(spec.get("labels") or {}),
        "annotations": dict(spec.get("annotations") or {}),
        "alerting": _normalize_alerting(spec.get("alerting") or {}),
    }
    return normalized


def _normalize_alerting(alerting: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(alerting, dict):
        raise SpecError("spec.alerting must be a mapping")
    return {
        "disable": bool(alerting.get("disable", False)),
        "pageLabels": dict(alerting.get("pageLabels") or {}),
        "ticketLabels": dict(alerting.get("ticketLabels") or {}),
    }
