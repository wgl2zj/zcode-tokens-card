"""stats 纯函数单测:单位换算边界值、聚合、TOP3、占比、日期基准、生成速率。"""

import datetime

import pytest

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
    assert S.today_label(d) == "9月14日 周一"


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


# —— 生成速率口径 ——

def test_speed_of_uses_generation_window_not_duration():
    """分母取 completed-first_token(真实生成窗口),不能退化成整轮时长。

    取自真机样本:整轮 13.765s,其中 7.9s 在等首字,生成窗口只有 5.865s。
    若误用整轮时长会算出 56 tok/s,把 132 的速度低估一半以上。
    """
    first, done = 1_000_000, 1_005_865
    assert S.speed_of(776, first, done) == pytest.approx(776 / 5.865)
    assert S.speed_of(776, first, done) > 776 / 13.765 * 2


def test_speed_of_rejects_untrustworthy_samples():
    """字段缺失/窗口过短/速度超上限一律判不可信(返回 None,不显示离谱数字)。"""
    assert S.speed_of(0, 1_000_000, 1_005_000) is None        # 无输出
    assert S.speed_of(500, None, 1_005_000) is None           # 缺首字时刻
    assert S.speed_of(500, 1_000_000, None) is None           # 缺完成时刻
    assert S.speed_of(500, 1_000_000, 1_000_050) is None      # 窗口 50ms 过短
    assert S.speed_of(1_000_000, 1_000_000, 1_001_000) is None  # 超速度上限
    assert S.speed_of(500, 1_000_000, 1_001_000) is not None  # 正常样本


def test_gen_rates_latest_and_per_model():
    """当前速率取最近一次可信样本;各模型各取自己最近一次(多模型可并行)。"""
    now = 1_000_000
    rows = [                                    # 已按 completed_at 倒序
        ("b", 200, now - 5_000, now - 4_000),   # 最近:b 200/1s
        ("a", 300, now - 9_000, now - 6_000),   # a 300/3s
        ("a", 999, now - 30_000, now - 20_000),  # a 更早,不得覆盖上面那条
    ]
    latest, by_model = S.gen_rates(rows, now, fresh_ms=60_000)
    assert latest == pytest.approx(200.0)
    assert by_model["a"] == pytest.approx(100.0)
    assert by_model["b"] == pytest.approx(200.0)


def test_gen_rates_drops_stale_and_skips_bad_samples():
    """超新鲜期的样本一律不算(空闲不显示陈旧速率);坏样本跳过续看更早的。"""
    now = 1_000_000
    assert S.gen_rates([("a", 300, now - 200_000, now - 190_000)],
                       now, fresh_ms=60_000) == (None, {})
    assert S.gen_rates([], now, fresh_ms=60_000) == (None, {})
    rows = [
        ("a", 300, now - 5_000, now - 4_950),   # 窗口 50ms → 坏样本
        ("a", 240, now - 9_000, now - 8_000),   # 240/1s → 应被取到
    ]
    latest, by_model = S.gen_rates(rows, now, fresh_ms=60_000)
    assert latest == pytest.approx(240.0)
    assert by_model["a"] == pytest.approx(240.0)


def test_fmt_rate_idle_clamp_and_unit():
    """无样本显示「空闲」;取整;超上限钳成 999+;单位按调用方给。"""
    assert S.fmt_rate(None) == "空闲"
    assert S.fmt_rate(238.6) == "239"
    assert S.fmt_rate(238.6, "t/s") == "239 t/s"
    assert S.fmt_rate(999) == "999"
    assert S.fmt_rate(1000) == "999+"
    assert S.fmt_rate(1500, "t/s") == "999+ t/s"


def test_fmt_count_units():
    """轮次:4 位内含「次」(无空格);达万改用中文单位且不带小数。"""
    assert S.fmt_count(0) == "0次"
    assert S.fmt_count(5124) == "5124次"
    assert S.fmt_count(9999) == "9999次"
    assert S.fmt_count(10000) == "1万次"
    assert S.fmt_count(123456) == "12万次"
