"""drip 单测:增量摊放调度的按时长摊放、守恒、封顶与字段等比。

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


def test_first_batch_uses_default_tick():
    """首段无间隔信息:按一个节拍(4s)快速放完。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    s.add({"total": 10_000.0}, 1_000.0)
    released, _ = drive(s, 1_000.0, 6_000.0)
    assert abs(released["total"] - 10_000.0) < 0.01
    assert not s.pending()


def test_duration_matches_arrival_gap():
    """间隔 60s 到账的一批:在接下来的 60s 内渐进释放,不过期不放完。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    s.add({"total": 10_000.0}, 0.0)                 # 首段默认 4s
    first, _ = drive(s, 0.0, 6_000.0)
    assert abs(first["total"] - 10_000.0) < 0.01

    s.add({"total": 60_000.0}, 60_000.0)            # 距上次到账 60s → 时长 60s
    mid, count = drive(s, 60_000.0, 40_000.0)       # 只推 40s(<60s 时长)
    assert 0.0 < mid["total"] < 60_000.0            # 渐进中,未放完
    tail, count2 = drive(s, 100_000.0, 30_000.0)    # 推过 deadline(120s)
    assert abs(mid["total"] + tail["total"] - 60_000.0) < 0.01
    assert count + count2 >= 10                     # 40s 内节拍 2~4s 至少 10 跳


def test_conservation_parallel_batches():
    """多段并行:任意时刻 已释放+在池 = 已入池,先到期先放完。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    deposited = 0.0
    released_total = 0.0
    t = 0.0
    while t <= 100_000.0:
        if t == 0.0:
            s.add({"total": 40_000.0}, t)           # 40s 时长段
            deposited += 40_000.0
        if t == 20_000.0:
            s.add({"total": 10_000.0}, t)           # 20s 时长段
            deposited += 10_000.0
        if s.due(t):
            released_total += s.release(t).get("total", 0.0)
        assert abs(released_total + sum(s.pending().values())
                   - deposited) < 0.01
        t += 500.0
    tail, _ = drive(s, t, 60_000.0)
    assert abs(released_total + tail.get("total", 0.0) - 50_000.0) < 0.01


def test_display_lag_bounded_and_catches_up():
    """持续到账:显示不超真实;停止到账后一个节拍+一段间隔内追平。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    t = 0.0
    real = 0.0
    shown = 0.0
    while t < 120_000.0:                    # 每 5s 到账 1 万(时长 5s)
        real += 10_000.0
        s.add({"total": 10_000.0}, t)
        if s.due(t):
            shown += s.release(t).get("total", 0.0)
        assert shown <= real + 0.01
        t += 500.0
    tail, _ = drive(s, t, 20_000.0)
    shown += tail.get("total", 0.0)
    assert abs(shown - real) < 0.01


def test_max_duration_cap():
    """间隔超过封顶(10 分钟)时按封顶时长放完:610s 内应放完 700s 间隔的量。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    s.add({"total": 1_000.0}, 0.0)
    drive(s, 0.0, 6_000.0)
    s.add({"total": 1_000_000.0}, 700_000.0)        # 间隔 700s > 封顶
    released, _ = drive(s, 700_000.0, 610_000.0)    # 只推 610s(<未封顶的 700s)
    assert abs(released["total"] - 1_000_000.0) < 0.01


def test_fields_released_proportionally():
    """单段多字段:一次释放保持段内字段比例(同跳共用抖动因子)。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    s.add({"total": 1_000.0, "input": 100.0, "output": 900.0}, 0.0)
    assert s.due(4_000.0)
    chunk = s.release(4_000.0)
    assert abs(chunk["total"] / chunk["input"] - 10.0) < 1e-6
    assert abs(chunk["total"] / chunk["output"] - 10.0 / 9.0) < 1e-6


def test_adjacent_releases_differ():
    """相邻两跳的 total 释放量取整后必不相同(抖动+撞值重抽)。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    s.add({"total": 1_000.0}, 0.0)                  # 首段默认 4s
    drive(s, 0.0, 6_000.0)
    s.add({"total": 1_000_000.0}, 60_000.0)         # 间隔 60s → 时长 60s
    outs = []
    t = 60_000.0
    while t < 126_000.0:
        if s.due(t):
            val = round(s.release(t).get("total", 0.0))
            if val:
                outs.append(val)
        t += 500.0
    assert len(outs) >= 3
    assert len(set(outs)) == len(outs)              # 互不相同


def test_reset_drops_all_pending():
    """跨天重置:清空池与排程,旧量不再放出。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    s.add({"total": 100_000.0}, 0.0)
    drive(s, 0.0, 6_000.0)                          # 首段放完
    s.add({"total": 50_000.0}, 10_000.0)            # 10s 时长段,在池
    assert s.pending()
    s.reset()
    assert s.pending() == {}
    assert not s.due(20_000.0)
    released, _ = drive(s, 20_000.0, 30_000.0)
    assert released == {}


def test_empty_and_zero_delta_are_inert():
    """空池不释放;零增量不入池、也不推进到账时刻。"""
    s = drip.DripScheduler(tick_min_ms=2_000, tick_max_ms=4_000,
                           max_duration_ms=600_000)
    assert not s.due(0.0)
    assert s.release(1_000.0) == {}
    s.add({"total": 0.0}, 5_000.0)                  # 零增量:不入池
    assert s.pending() == {}
    s.add({"total": 8_000.0}, 60_000.0)             # 无参照 → 仍按首段 4s
    chunk = s.release(64_000.0)
    assert abs(chunk["total"] - 8_000.0) < 0.01
