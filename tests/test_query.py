from slo_operator import query


def test_has_window_placeholder():
    assert query.has_window_placeholder("rate(x[{{.window}}])")
    assert query.has_window_placeholder("rate(x[{{ .window }}])")
    assert not query.has_window_placeholder("rate(x[5m])")
    assert not query.has_window_placeholder("")


def test_render_query_substitutes_all_occurrences():
    tmpl = "sum(rate(a[{{.window}}])) + sum(rate(b[{{ .window }}]))"
    rendered = query.render_query(tmpl, "5m")
    assert rendered == "sum(rate(a[5m])) + sum(rate(b[5m]))"
    assert "{{" not in rendered


def test_render_query_noop_without_placeholder():
    assert query.render_query("up", "1h") == "up"
