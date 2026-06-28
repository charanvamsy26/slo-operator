"""kopf handlers: reconcile ServiceLevelObjective resources into PrometheusRules.

Lifecycle:
  * create/update/resume -> validate spec, compile to a PrometheusRule, adopt it
    (owner reference for garbage collection), apply it, and write status.
  * delete -> best-effort delete of the managed PrometheusRule (owner-ref GC is
    the primary mechanism; this handler makes cleanup explicit and observable).
  * timer -> when --prometheus-url is configured, compute live error-budget
    consumption and write it into status.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import kopf
import kubernetes
from kubernetes.client.exceptions import ApiException

from . import GROUP, PLURAL, VERSION
from . import budget as budget_math
from .compiler import compile_slo, rule_name
from .prometheus import PrometheusClient
from .validation import SpecError, validate_spec

# PrometheusRule custom resource coordinates.
PR_GROUP = "monitoring.coreos.com"
PR_VERSION = "v1"
PR_PLURAL = "prometheusrules"

# Populated at startup from flags/env.
_PROM_CLIENT: PrometheusClient | None = None
_RULE_LABELS: dict[str, str] = {}
_BUDGET_INTERVAL = float(os.getenv("SLO_BUDGET_INTERVAL_SECONDS", "300"))


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, logger, **_: Any) -> None:
    """Load kube config and read operator configuration from the environment."""
    global _PROM_CLIENT, _RULE_LABELS

    try:
        kubernetes.config.load_incluster_config()
        logger.info("loaded in-cluster kube config")
    except kubernetes.config.ConfigException:
        kubernetes.config.load_kube_config()
        logger.info("loaded local kube config")

    prom_url = os.getenv("SLO_PROMETHEUS_URL", "").strip()
    if prom_url:
        _PROM_CLIENT = PrometheusClient(prom_url)
        logger.info("error-budget reporting enabled against %s", prom_url)
    else:
        logger.info("no SLO_PROMETHEUS_URL set; error-budget reporting disabled")

    _RULE_LABELS = _parse_labels(os.getenv("SLO_PROMETHEUSRULE_LABELS", ""))

    # Surface reconcile outcomes as Kubernetes Events.
    settings.posting.enabled = True
    # Run without peering so no ClusterKopfPeering CRD/RBAC is required.
    settings.peering.standalone = True
    # Avoid noisy retries on transient API hiccups.
    settings.batching.error_delays = [10, 30, 60]


@kopf.on.create(GROUP, VERSION, PLURAL)
@kopf.on.update(GROUP, VERSION, PLURAL)
@kopf.on.resume(GROUP, VERSION, PLURAL)
def reconcile(spec, meta, namespace, name, patch, logger, **_: Any) -> None:
    """Compile the SLO into a PrometheusRule and apply it."""
    try:
        normalized = validate_spec(dict(spec))
    except SpecError as exc:
        logger.error("invalid ServiceLevelObjective %s/%s: %s", namespace, name, exc)
        _set_condition(patch, status="False", reason="InvalidSpec", message=str(exc),
                       generation=meta.get("generation"))
        kopf.event({"metadata": meta}, type="Warning", reason="InvalidSpec", message=str(exc))
        # Returning (not raising) avoids a hot retry loop; a spec edit re-triggers us.
        return

    compiled = compile_slo(name, namespace, normalized, rule_labels=_RULE_LABELS)
    manifest = compiled.manifest

    # Owner reference so the PrometheusRule is garbage-collected with the SLO.
    kopf.adopt(manifest)
    _apply_prometheus_rule(manifest, logger)

    patch.status["prometheusRuleName"] = rule_name(name)
    patch.status["recordingRules"] = compiled.recording_rules
    patch.status["alertingRules"] = compiled.alerting_rules
    patch.status["observedGeneration"] = meta.get("generation")
    _set_condition(
        patch,
        status="True",
        reason="Reconciled",
        message=(
            f"Generated {compiled.recording_rules} recording and "
            f"{compiled.alerting_rules} alerting rules"
        ),
        generation=meta.get("generation"),
    )
    logger.info("reconciled SLO %s/%s -> PrometheusRule %s", namespace, name, rule_name(name))


@kopf.on.delete(GROUP, VERSION, PLURAL)
def cleanup(namespace, name, logger, **_: Any) -> None:
    """Best-effort delete of the managed PrometheusRule."""
    api = kubernetes.client.CustomObjectsApi()
    try:
        api.delete_namespaced_custom_object(
            group=PR_GROUP, version=PR_VERSION, namespace=namespace,
            plural=PR_PLURAL, name=rule_name(name),
        )
        logger.info("deleted PrometheusRule %s/%s", namespace, rule_name(name))
    except ApiException as exc:
        if exc.status != 404:
            raise
        logger.info("PrometheusRule %s/%s already gone", namespace, rule_name(name))


@kopf.timer(GROUP, VERSION, PLURAL, interval=_BUDGET_INTERVAL)
def report_error_budget(spec, namespace, name, patch, logger, **_: Any) -> None:
    """Periodically compute live error-budget consumption from Prometheus."""
    if _PROM_CLIENT is None:
        return
    try:
        normalized = validate_spec(dict(spec))
    except SpecError:
        return  # invalid specs are handled by reconcile; nothing to measure

    objective = normalized["objective"]
    window = normalized["window"]
    events = normalized["sli"]["events"]
    try:
        error_ratio = _PROM_CLIENT.error_ratio(
            events["errorQuery"], events["totalQuery"], window
        )
    except Exception as exc:  # noqa: BLE001 - never let the timer crash the operator
        logger.warning("error-budget query failed for %s/%s: %s", namespace, name, exc)
        return

    if error_ratio is None:
        logger.info("no data yet for SLO %s/%s; skipping budget update", namespace, name)
        return

    remaining = budget_math.remaining_budget_percent(error_ratio, objective)
    rate = budget_math.burn_rate(error_ratio, objective)
    patch.status["errorBudget"] = {
        "remainingPercent": f"{remaining:.2f}",
        "burnRate": f"{rate:.2f}",
        "lastEvaluated": _now(),
    }
    logger.info(
        "SLO %s/%s: %.2f%% budget remaining (burn rate %.2f)",
        namespace, name, remaining, rate,
    )


def _apply_prometheus_rule(manifest: dict[str, Any], logger) -> None:
    """Create or replace the PrometheusRule (idempotent server-side reconcile)."""
    api = kubernetes.client.CustomObjectsApi()
    ns = manifest["metadata"]["namespace"]
    nm = manifest["metadata"]["name"]
    try:
        existing = api.get_namespaced_custom_object(
            group=PR_GROUP, version=PR_VERSION, namespace=ns, plural=PR_PLURAL, name=nm,
        )
        manifest["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
        api.replace_namespaced_custom_object(
            group=PR_GROUP, version=PR_VERSION, namespace=ns, plural=PR_PLURAL, name=nm,
            body=manifest,
        )
        logger.debug("replaced PrometheusRule %s/%s", ns, nm)
    except ApiException as exc:
        if exc.status != 404:
            raise
        api.create_namespaced_custom_object(
            group=PR_GROUP, version=PR_VERSION, namespace=ns, plural=PR_PLURAL, body=manifest,
        )
        logger.debug("created PrometheusRule %s/%s", ns, nm)


def _set_condition(patch, *, status: str, reason: str, message: str,
                   generation: int | None) -> None:
    patch.status["conditions"] = [
        {
            "type": "Ready",
            "status": status,
            "reason": reason,
            "message": message,
            "lastTransitionTime": _now(),
            "observedGeneration": generation,
        }
    ]


def _parse_labels(raw: str) -> dict[str, str]:
    """Parse a comma-separated key=value string into a label dict."""
    labels: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        labels[key.strip()] = value.strip()
    return labels


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
