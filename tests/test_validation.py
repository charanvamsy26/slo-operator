import pytest

from slo_operator.validation import SpecError, validate_spec

VALID = {
    "service": "api",
    "objective": 99.9,
    "sli": {
        "events": {
            "errorQuery": "sum(rate(http_requests_total{code=~'5..'}[{{.window}}]))",
            "totalQuery": "sum(rate(http_requests_total[{{.window}}]))",
        }
    },
}


def _spec(**overrides):
    import copy

    s = copy.deepcopy(VALID)
    s.update(overrides)
    return s


def test_valid_spec_normalizes_with_defaults():
    out = validate_spec(_spec())
    assert out["service"] == "api"
    assert out["objective"] == 99.9
    assert out["window"] == "30d"  # default applied
    assert out["alerting"] == {"disable": False, "pageLabels": {}, "ticketLabels": {}}
    assert out["labels"] == {}


def test_missing_service_rejected():
    s = _spec()
    del s["service"]
    with pytest.raises(SpecError, match="service"):
        validate_spec(s)


@pytest.mark.parametrize("bad", [0, 100, -1, 100.1, 150])
def test_objective_bounds_rejected(bad):
    with pytest.raises(SpecError, match="objective"):
        validate_spec(_spec(objective=bad))


def test_boolean_objective_rejected():
    # bool is a subclass of int; make sure True/False are not accepted.
    with pytest.raises(SpecError, match="objective"):
        validate_spec(_spec(objective=True))


def test_unsupported_window_rejected():
    with pytest.raises(SpecError, match="window"):
        validate_spec(_spec(window="7d"))


def test_missing_placeholder_rejected():
    s = _spec()
    s["sli"]["events"]["errorQuery"] = "sum(rate(http_requests_total[5m]))"
    with pytest.raises(SpecError, match="placeholder"):
        validate_spec(s)


def test_missing_sli_rejected():
    s = _spec()
    del s["sli"]
    with pytest.raises(SpecError, match="sli"):
        validate_spec(s)
