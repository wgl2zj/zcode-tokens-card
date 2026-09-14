"""增量摊放调度:把每轮到账的用量增量在窗口期内分多次小步释放显示。

目的:悬浮窗数字不必等每次模型调用完成才跳一大下(上游 model_usage 是
调用完成才落库,间隔十几二十秒),而是每 3~4 秒放一小步、约 30 秒内摊完;
期间新增量并入同一池子,显示值最多落后真实值一个窗口期。

纯逻辑模块:时间由调用方注入(now_ms,单调毫秒),便于确定性测试;
释放间隔带 3~4s 随机抖动,避免跳动的机械感。
"""

import random

_EPS = 1e-9


class DripScheduler:
    """按"剩余窗口均分"释放的增量池:add 进池,due 到点,release 取一份。"""

    def __init__(self, window_ms: float = 30_000.0,
                 tick_min_ms: float = 3_000.0, tick_max_ms: float = 4_000.0):
        self._window = float(window_ms)
        self._tick_min = float(tick_min_ms)
        self._tick_max = float(tick_max_ms)
        self._pool: dict[str, float] = {}
        self._deadline = 0.0   # 池子清空期限(ms);0 = 当前无池
        self._next_due = 0.0   # 下次可释放时刻(ms);0 = 未排程

    def add(self, delta: dict[str, float], now_ms: float) -> None:
        """新到账增量并入池;空池时开启新窗口并排程首跳。

        窗口未到期时到达的新增量的 deadline 不顺延——池子必须在原窗口内
        放完,这是"显示最多落后真实值一个窗口期"的保证。
        """
        for key, val in delta.items():
            if val:
                self._pool[key] = self._pool.get(key, 0.0) + val
        if self._pool and now_ms >= self._deadline:
            self._deadline = now_ms + self._window
        if self._pool and self._next_due < now_ms:
            self._next_due = now_ms + self._rand_tick()

    def due(self, now_ms: float) -> bool:
        """是否到了下一次释放时刻(有池且已到排程点)。"""
        return bool(self._pool) and now_ms >= self._next_due

    def release(self, now_ms: float) -> dict[str, float]:
        """释放一份:各字段按"剩余窗口可跳次数"均分,比例保持池内比例。

        返回 {字段: 释放量}(仅含非零项);池放空后清除排程,等下一次 add。
        """
        if not self._pool:
            return {}
        remain = self._deadline - now_ms
        # 剩余时间按最长节拍折算可跳次数,保证窗口内放完;过期则一次清空
        n = max(1, -(-remain // self._tick_max)) if remain > 0 else 1
        out = {key: val / n for key, val in self._pool.items()}
        self._pool = {key: val - out[key] for key, val in self._pool.items()}
        self._pool = {key: val for key, val in self._pool.items()
                      if abs(val) > _EPS}
        if self._pool:
            self._next_due = now_ms + self._rand_tick()
        else:
            self._pool = {}
            self._deadline = 0.0
            self._next_due = 0.0
        return {key: val for key, val in out.items() if val > _EPS}

    def pending(self) -> dict[str, float]:
        """当前在池增量(诊断/测试用)。"""
        return dict(self._pool)

    def _rand_tick(self) -> float:
        return random.uniform(self._tick_min, self._tick_max)
