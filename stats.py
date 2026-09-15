"""统计聚合与单位换算:纯函数,无 IO,可独立单测。"""

import datetime

_WEEK = "一二三四五六日"


def cny(v: float) -> str:
    """中文进制单位:≥1亿 → X.XX亿;≥1万 → X.X万;否则千分位整数。"""
    if v >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if v >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{round(v):,}"


def full(v: float) -> str:
    """完整千分位整数字符串(无单位):三列显示用,小数额跳动也可感知。"""
    return f"{round(v):,}"


def today_start_ms(now: datetime.datetime | None = None) -> int:
    """本地时区今日 0 点的 epoch 毫秒(model_usage.started_at 的比较基准)。"""
    d = now or datetime.datetime.now()
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


def today_label(now: datetime.datetime | None = None) -> str:
    """顶行日期标签:"9月14日 周一"(时间由 card 拼接;288 宽卡顶行放不下
    "今日 · "前缀与次数并排,今日语义由"今日 TOKENS"小标承担)。"""
    d = now or datetime.datetime.now()
    return f"{d.month}月{d.day}日 周{_WEEK[d.weekday()]}"


def aggregate(rows) -> dict:
    """聚合 model_usage 当日行。

    rows: (input_tokens, output_tokens, cache_read_input_tokens,
           computed_total_tokens) 元组序列。
    """
    return {
        "count": len(rows),
        "input": sum(r[0] for r in rows),
        "output": sum(r[1] for r in rows),
        "cache": sum(r[2] for r in rows),
        "total": sum(r[3] for r in rows),
    }


def top_models(rows, limit: int = 3) -> list[tuple[str, int]]:
    """分模型当日用量倒序前 limit。

    rows: (model_id, computed_total_tokens) 元组序列。
    """
    agg: dict[str, int] = {}
    for mid, total in rows:
        agg[mid] = agg.get(mid, 0) + total
    return sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:limit]


def shares(models: list[tuple[str, int]]) -> list[float]:
    """各模型占当日总量比例(0~1);总量为 0 时全 0。"""
    total = sum(v for _, v in models)
    if total <= 0:
        return [0.0] * len(models)
    return [v / total for _, v in models]
