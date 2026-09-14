"""stats 纯函数单测:单位换算边界值、聚合、TOP3、占比、日期基准。"""

import datetime

import stats as S


def test_cny_units():
    assert S.cny(0) == "0"
    assert S.cny(5593) == "5,593"
    assert S.cny(9999) == "9,999"           # 万边界下沿
    assert S.cny(10000) == "1.0万"           # 万边界
    assert S.cny(493000) == "49.3万"
    assert S.cny(1066000) == "106.6万"
    assert S.cny(99999999) == "10000.0万"    # 亿边界下沿(与设计稿一致)
    assert S.cny(100000000) == "1.00亿"      # 亿边界
    assert S.cny(5771405738) == "57.71亿"


def test_full_units():
    assert S.full(0) == "0"
    assert S.full(999) == "999"
    assert S.full(1234567) == "1,234,567"
    assert S.full(150_952_341.4) == "150,952,341"
    assert S.full(150_952_341.6) == "150,952,342"


def test_today_start_ms():
    d = datetime.datetime(2026, 9, 14, 10, 30, 45)
    ts = S.today_start_ms(d)
    back = datetime.datetime.fromtimestamp(ts / 1000)
    assert (back.year, back.month, back.day) == (2026, 9, 14)
    assert back.hour == back.minute == back.second == 0


def test_today_label():
    d = datetime.datetime(2026, 9, 14, 8, 0)  # 2026-09-14 是周一
    assert S.today_label(d) == "今日 · 9月14日 周一"


def test_aggregate():
    rows = [(10, 1, 5, 16), (20, 2, 8, 30)]
    assert S.aggregate(rows) == {"count": 2, "input": 30, "output": 3,
                                 "cache": 13, "total": 46}
    assert S.aggregate([]) == {"count": 0, "input": 0, "output": 0,
                               "cache": 0, "total": 0}


def test_top_models_merges_and_ranks():
    rows = [("a", 10), ("b", 30), ("c", 20), ("a", 5), ("d", 1)]
    assert S.top_models(rows, 3) == [("b", 30), ("c", 20), ("a", 15)]
    assert S.top_models([], 3) == []


def test_shares():
    assert S.shares([("a", 75), ("b", 25)]) == [0.75, 0.25]
    assert S.shares([("a", 0)]) == [0.0]
    assert S.shares([]) == []
