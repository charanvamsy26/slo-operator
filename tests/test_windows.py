from slo_operator import windows


def test_standard_windows_shape():
    ws = windows.standard_windows()
    assert len(ws) == 4
    # Two page tiers, two ticket tiers.
    sev = [w.severity for w in ws]
    assert sev.count(windows.SEVERITY_PAGE) == 2
    assert sev.count(windows.SEVERITY_TICKET) == 2


def test_standard_windows_canonical_factors():
    ws = {(w.long_window, w.short_window): w.factor for w in windows.standard_windows()}
    assert ws[("1h", "5m")] == 14.4
    assert ws[("6h", "30m")] == 6
    assert ws[("1d", "2h")] == 3
    assert ws[("3d", "6h")] == 1


def test_ratio_windows_cover_all_alert_windows():
    rate_windows = set(windows.ratio_windows())
    for w in windows.standard_windows():
        assert w.long_window in rate_windows
        assert w.short_window in rate_windows


def test_ratio_windows_unique_and_ordered():
    rw = windows.ratio_windows()
    assert len(rw) == len(set(rw))
    assert rw == ["5m", "30m", "1h", "2h", "6h", "1d", "3d"]
