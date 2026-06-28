from slo_operator.prometheus import PrometheusClient, _extract_scalar


def test_extract_scalar_types():
    assert _extract_scalar({"resultType": "scalar", "result": [123, "0.5"]}) == 0.5
    assert _extract_scalar(
        {"resultType": "vector", "result": [{"value": [123, "2"]}]}
    ) == 2.0
    assert _extract_scalar({"resultType": "vector", "result": []}) is None
    assert _extract_scalar({"resultType": "matrix", "result": []}) is None


def test_error_ratio_divides(monkeypatch):
    client = PrometheusClient("http://prom.example")
    answers = {
        "errors[30d]": 5.0,
        "total[30d]": 100.0,
    }
    monkeypatch.setattr(client, "query_scalar", lambda expr: answers[expr])
    ratio = client.error_ratio("errors[{{.window}}]", "total[{{.window}}]", "30d")
    assert ratio == 0.05


def test_error_ratio_none_when_no_traffic(monkeypatch):
    client = PrometheusClient("http://prom.example")
    monkeypatch.setattr(client, "query_scalar", lambda expr: 0.0)
    assert client.error_ratio("errors[{{.window}}]", "total[{{.window}}]", "30d") is None
