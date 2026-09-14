"""drip 单测:增量摊放调度的窗口收敛、守恒与字段等比。

全部用注入时钟(now_ms 参数),不依赖真实时间;不触碰任何数据库。
"""

import drip


def drive(sched: drip.DripScheduler, start_ms: float, dur_ms: float,
          step_ms: float = 500.0) -> tuple[dict, int]:
    """推进假时钟并在到点时释放,返回累计释放量与释放次数。"""
    released: dict[str, float] = {}
    count = 0
    t = start_ms
    while t < start_ms + dur_ms:
        if sched.due(t):
            count += 1
            for key, val in sched.release(t).items():
                released[key] = released.get(key, 0.0) + val
        t += step_ms
    return released, count


def test_single_delta_drips_within_window():
    """单批增量:30s 窗口内放完,3~4s 一跳(至少 5 跳)。"""
    s = drip.DripScheduler(window_ms=30_000, tick_min_ms=3_000,
                           tick_max_ms=4_000)
    t0 = 1_000.0
    s.add({"total": 100_000.0}, t0)
    released, count = drive(s, t0, 32_000)
    assert count >= 5
    assert abs(released["total"] - 100_000.0) < 0.01
    assert not s.pending()


def test_conservation_when_new_delta_joins():
    """窗口内新增量并入同一池:任意时刻已释放+在池 = 总入池,不丢量。"""
    s = drip.DripScheduler(window_ms=30_000, tick_min_ms=3_000,
                           tick_max_ms=4_000)
    t0 = 0.0
    s.add({"total": 60_000.0}, t0)
    released_total = 0.0
    deposited = 60_000.0
    t = t0
    while t < t0 + 20_000:
        if t == 6_000.0:
            s.add({"total": 30_000.0}, t)   # 窗口未到期,deadline 不顺延
            deposited += 30_000.0
        if s.due(t):
            chunk = s.release(t)
            released_total += chunk.get("total", 0.0)
        # 守恒:已释放 + 在池 == 已入池
        assert abs(released_total + sum(s.pending().values())
                   - deposited) < 0.01
        t += 500.0
    tail, _ = drive(s, t, 30_000)
    released_total += tail.get("total", 0.0)
    assert abs(released_total - 90_000.0) < 0.01


def test_display_lag_bounded_and_catches_up():
    """显示不超真实;真实值停止增长后 30s 内追平。"""
    s = drip.DripScheduler(window_ms=30_000, tick_min_ms=3_000,
                           tick_max_ms=4_000)
    t = 0.0
    real = 0.0
    shown = 0.0
    while t < 60_000:                      # 持续输入:每 3s 到账 1 万
        real += 10_000.0
        s.add({"total": 10_000.0}, t)
        if s.due(t):
            shown += s.release(t).get("total", 0.0)
        assert shown <= real + 0.01        # 全程不超真实
        t += 500.0
    tail, _ = drive(s, t, 30_000)          # 输入停止,窗口内应追平
    shown += tail.get("total", 0.0)
    assert abs(shown - real) < 0.01


def test_fields_released_proportionally():
    """多字段同池:单次释放保持池内字段比例(总量:输入:输出 同步)。"""
    s = drip.DripScheduler(window_ms=30_000, tick_min_ms=3_000,
                           tick_max_ms=4_000)
    s.add({"total": 1_000.0, "input": 100.0, "output": 900.0}, 0.0)
    assert s.due(3_500.0)
    chunk = s.release(3_500.0)
    ratio_total_input = chunk["total"] / chunk["input"]
    ratio_total_output = chunk["total"] / chunk["output"]
    assert abs(ratio_total_input - 10.0) < 1e-6
    assert abs(ratio_total_output - 10.0 / 9.0) < 1e-6


def test_empty_scheduler_is_inert():
    """空池不排程不释放;窗口内部分释放,过期后一次清空。"""
    s = drip.DripScheduler()
    assert not s.due(0.0)
    assert s.release(1_000.0) == {}
    s.add({"total": 5_000.0}, 1_000.0)
    assert s.due(1_000.0 + 4_000.0)
    chunk = s.release(1_000.0 + 4_000.0)
    assert 0.0 < chunk["total"] < 5_000.0        # 窗口未过 → 只放一份
    tail, _ = drive(s, 5_000.0, 40_000.0)        # 推进过 30s 窗口
    total_out = chunk["total"] + tail.get("total", 0.0)
    assert abs(total_out - 5_000.0) < 0.01       # 全部放完
    assert not s.due(60_000.0)
