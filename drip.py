"""增量摊放调度:每段到账增量按"它的产生时长"在后续时间里分步释放。

上游 model_usage 是一次模型调用完成才落库,相邻两条记录的间隔即这批
tokens 的产生时长:隔 2 分钟出现的一批,就在之后 2 分钟内摊完。
节拍 2~4 秒随机抖动;多段增量各自成池、同跳合并释放(各池先到期先放完)。
每跳释放量在均分基础上乘 0.7~1.3 随机抖动并保证相邻跳不同,跳动感更真实。
纯逻辑:时钟由调用方注入(now_ms,单调毫秒),便于确定性测试。
封顶:单段摊放时长不超过 max_duration_ms——隔夜等超长间隔不无限拖旧账。
"""

import random

_EPS = 1e-9


class _Batch:
    """一段增量:各字段剩余额度 + 摊完期限。"""

    __slots__ = ("amount", "deadline")

    def __init__(self, amount: dict[str, float], deadline: float):
        self.amount = amount
        self.deadline = deadline


class DripScheduler:
    """多段增量池:每 2~4s 一跳,每跳各未到期池按剩余时间均分并随机抖动。"""

    def __init__(self, tick_min_ms: float = 2_000.0,
                 tick_max_ms: float = 4_000.0,
                 max_duration_ms: float = 600_000.0,
                 jitter_min: float = 0.7, jitter_max: float = 1.3):
        self._tick_min = float(tick_min_ms)
        self._tick_max = float(tick_max_ms)
        self._max_duration = float(max_duration_ms)
        self._jitter_min = float(jitter_min)
        self._jitter_max = float(jitter_max)
        self._batches: list[_Batch] = []
        self._last_arrival: float | None = None  # 上次到账时刻;None = 尚无
        self._next_due = 0.0       # 下次释放时刻(ms);0 = 未排程
        self._last_out_total = 0.0  # 上一跳 total 释放量(相邻跳防重样)

    def add(self, delta: dict[str, float], now_ms: float) -> None:
        """一段增量入池;摊放时长默认 = 与上次到账的间隔(封顶 max_duration)。

        首段没有间隔信息,按一个节拍(4s)快速放完;零增量不入池,
        也不更新到账时刻——间隔要累计到真正有记录的那次。
        """
        if not any(delta.values()):
            return
        if self._last_arrival is None:
            duration = self._tick_max
        else:
            duration = now_ms - self._last_arrival
        self._last_arrival = now_ms
        duration = min(duration, self._max_duration)
        self._batches.append(_Batch(
            {k: v for k, v in delta.items() if v}, now_ms + duration))
        if self._next_due < now_ms:
            self._next_due = now_ms + self._rand_tick()

    def due(self, now_ms: float) -> bool:
        """是否到了下一次释放时刻(有池且已到排程点)。"""
        return bool(self._batches) and now_ms >= self._next_due

    def reset(self) -> None:
        """清空全部池与排程(跨天/数据回退时由 card 调用,旧账一笔勾销)。"""
        self._batches = []
        self._last_arrival = None
        self._next_due = 0.0
        self._last_out_total = 0.0

    def release(self, now_ms: float) -> dict[str, float]:
        """释放一跳:各未到期池按剩余时间均分、再乘随机抖动(0.7~1.3),
        total 与上一跳取整撞值时换抖动重抽(至多 3 次)——相邻跳必有差别;
        过期池一次清空。返回合计 {字段: 释放量}(仅含非零项)。
        """
        if not self._batches:
            return {}
        last = round(self._last_out_total)
        for _ in range(3):
            jitter = random.uniform(self._jitter_min, self._jitter_max)
            out, alive = self._plan(now_ms, jitter)
            total = round(out.get("total", 0.0))
            if total != last or total <= 0:
                break
        self._batches = alive
        self._last_out_total = out.get("total", 0.0)
        if self._batches:
            self._next_due = now_ms + self._rand_tick()
        else:
            self._next_due = 0.0
        return {k: v for k, v in out.items() if v > _EPS}

    def _plan(self, now_ms: float,
              jitter: float) -> tuple[dict[str, float], list[_Batch]]:
        """试算一跳(不改自身):每池 share = 剩余/n × 抖动,上限为剩余量;
        同跳共用一个抖动因子保持段内字段等比;n<=1(末跳/过期)不抖动、
        一次放完,保证"期限到即清空"语义。"""
        out: dict[str, float] = {}
        alive: list[_Batch] = []
        for batch in self._batches:
            remain = batch.deadline - now_ms
            n = max(1.0, -(-remain // self._tick_max)) if remain > 0 else 1.0
            amount: dict[str, float] = {}
            for key, val in batch.amount.items():
                share = val if n <= 1 else min(val, val / n * jitter)
                rest = val - share
                if abs(rest) > _EPS:
                    amount[key] = rest
                out[key] = out.get(key, 0.0) + share
            if amount:
                alive.append(_Batch(amount, batch.deadline))
        return out, alive

    def pending(self) -> dict[str, float]:
        """当前在池增量合计(诊断/测试用)。"""
        total: dict[str, float] = {}
        for batch in self._batches:
            for key, val in batch.amount.items():
                total[key] = total.get(key, 0.0) + val
        return total

    def _rand_tick(self) -> float:
        return random.uniform(self._tick_min, self._tick_max)
