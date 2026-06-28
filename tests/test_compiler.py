import pytest

from slo_operator import compiler
from slo_operator.validation import validate_spec

BASE = {
    "service": "api",
    "objective": 99.9,
    "sli": {
        "events": {
            "errorQuery": "sum(rate(http_requests_total{code=~'5..'}[{{.window}}]))",
            "totalQuery": "sum(rate(http_requests_total[{{.window}}]))",
        }
    },
}


def _compile(name="api-availability", namespace="demo", **spec_overrides):
    spec = {**BASE, **spec_overrides}
    return compiler.compile_slo(name, namespace, validate_spec(spec))


def test_counts_and_structure():
    c = _compile()
    assert c.recording_rules == 7
    assert c.alerting_rules == 4
    groups = c.manifest["spec"]["groups"]
    assert [g["name"] for g in groups] == [
        "slo-api-availability-sli-recordings",
        "slo-api-availability-alerts",
    ]
    assert c.manifest["metadata"]["name"] == "slo-api-availability"
    assert c.manifest["apiVersion"] == "monitoring.coreos.com/v1"
    assert c.manifest["kind"] == "PrometheusRule"


def test_metadata_labels():
    labels = _compile().manifest["metadata"]["labels"]
    assert labels["app.kubernetes.io/managed-by"] == "slo-operator"
    assert labels["sre_service"] == "api"
    assert labels["sre_slo"] == "api-availability"


def test_recording_rules_render_each_window():
    rec = _compile().manifest["spec"]["groups"][0]["rules"]
    records = {r["record"] for r in rec}
    assert records == {
        "slo:sli_error:ratio_rate5m",
        "slo:sli_error:ratio_rate30m",
        "slo:sli_error:ratio_rate1h",
        "slo:sli_error:ratio_rate2h",
        "slo:sli_error:ratio_rate6h",
        "slo:sli_error:ratio_rate1d",
        "slo:sli_error:ratio_rate3d",
    }
    # The {{.window}} placeholder is fully substituted.
    for r in rec:
        assert "{{" not in r["expr"]


def test_alert_threshold_in_expr():
    alerts = _compile().manifest["spec"]["groups"][1]["rules"]
    # The fast-burn (14.4x) alert for a 99.9% SLO uses threshold 0.0144.
    fast = next(a for a in alerts if a["labels"]["sre_long_window"] == "1h")
    assert "> 0.0144" in fast["expr"]
    assert "slo:sli_error:ratio_rate1h" in fast["expr"]
    assert "slo:sli_error:ratio_rate5m" in fast["expr"]
    assert fast["labels"]["sre_severity"] == "page"
    assert fast["for"] == "2m"


def test_determinism():
    a = _compile().manifest
    b = _compile().manifest
    assert a == b


def test_disable_alerts():
    c = _compile(alerting={"disable": True})
    assert c.alerting_rules == 0
    assert len(c.manifest["spec"]["groups"]) == 1


def test_user_labels_and_severity_labels_propagate():
    c = _compile(
        labels={"team": "payments"},
        alerting={"pageLabels": {"severity": "critical"}, "ticketLabels": {"severity": "warning"}},
    )
    rec = c.manifest["spec"]["groups"][0]["rules"][0]
    assert rec["labels"]["team"] == "payments"

    alerts = c.manifest["spec"]["groups"][1]["rules"]
    page = next(a for a in alerts if a["labels"]["sre_severity"] == "page")
    ticket = next(a for a in alerts if a["labels"]["sre_severity"] == "ticket")
    assert page["labels"]["severity"] == "critical"
    assert ticket["labels"]["severity"] == "warning"
    assert page["labels"]["team"] == "payments"


def test_rule_labels_added_to_metadata():
    spec = validate_spec(dict(BASE))
    c = compiler.compile_slo("api-availability", "demo", spec, rule_labels={"release": "kps"})
    assert c.manifest["metadata"]["labels"]["release"] == "kps"


@pytest.mark.parametrize(
    "objective,expected",
    [(99.9, "0.0144"), (99.0, "0.144"), (99.99, "0.00144")],
)
def test_threshold_scales_with_objective(objective, expected):
    alerts = _compile(objective=objective).manifest["spec"]["groups"][1]["rules"]
    fast = next(a for a in alerts if a["labels"]["sre_long_window"] == "1h")
    assert f"> {expected}" in fast["expr"]
