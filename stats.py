"""统计聚合与单位换算:纯函数,无 IO,可独立单测。"""

import datetime

_WEEK = "一二三四五六日"

# —— 生成速率口径 ——
RATE_MIN_WINDOW_MS = 100      # 生成窗口短于此值视为异常样本(防上游写入异常)
RATE_MAX_TOK_S = 2000.0       # 速度上限,超过视为异常样本
RATE_MAX_SHOWN = 999          # 显示钳制上限(槽位有限,超过显示 "999+")


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


def speed_of(output: int, first_token_at, completed_at,
             min_window_ms: int = RATE_MIN_WINDOW_MS,
             max_tok_s: float = RATE_MAX_TOK_S) -> float | None:
    """单次调用的生成速度(tok/s);样本不可信返回 None。

    分母取 completed_at - first_token_at:这才是真实生成窗口。不能用
    duration_ms——它含首字等待,实测 TTFT 常占整轮一半(某轮 13.8s 里 7.9s
    在等首字),用它会把速度系统性低估一半。
    窗口短于 min_window_ms 或速度超过 max_tok_s,都判为上游写入异常。
    """
    if not output or not first_token_at or not completed_at:
        return None
    window_ms = completed_at - first_token_at
    if window_ms < min_window_ms:
        return None
    v = output / (window_ms / 1000.0)
    return v if v <= max_tok_s else None


def gen_rates(rows, now_ms: float, fresh_ms: int,
              min_window_ms: int = RATE_MIN_WINDOW_MS,
              max_tok_s: float = RATE_MAX_TOK_S
              ) -> tuple[float | None, dict[str, float], set[str]]:
    """(顶行当前速率, 各模型最后速率, 正在生成的模型集合)。

    rows 为 (model_id, output, first_token_at, completed_at) 序列,须按
    completed_at 倒序,且每个模型给出最近若干条候选(reader.fetch_last_gen_rows)。
    每个模型各取自己最近一次可信样本——多模型可并行生成,不是"最近一条通吃";
    候选里最近一条不可信时退到该模型更早的候选。

    两个口径分开:顶行当前速率只在新鲜期(fresh_ms)内取,超期返回 None(显示
    "空闲");各模型速率是"最后一次"的读数,不限新鲜期——空闲时仍可回顾刚才
    跑多快,是否还在跑由 active 集合标记(样本仍在新鲜期内)。
    """
    last: dict[str, float] = {}
    active: set[str] = set()
    latest: float | None = None
    for mid, output, first_token_at, completed_at in rows:
        if mid in last:
            continue                        # 该模型已取到最近可信样本
        v = speed_of(output, first_token_at, completed_at,
                     min_window_ms, max_tok_s)
        if v is None:
            continue                        # 坏样本:退到该模型更早的候选
        last[mid] = v
        if now_ms - completed_at <= fresh_ms:
            active.add(mid)
            if latest is None:
                latest = v                  # 倒序:第一条新鲜可信样本即全局最新
    return latest, last, active


def fmt_rate(v: float | None, unit: str = "",
             max_shown: int = RATE_MAX_SHOWN) -> str:
    """速率显示:无样本 → "空闲";取整;超过 max_shown 钳成 "999+"。

    单位由调用方决定:顶行带 t/s;模型行与累计共处一列,按约定不带。
    """
    if v is None:
        return "空闲"
    n = int(round(v))
    text = f"{max_shown}+" if n > max_shown else str(n)
    return f"{text} {unit}" if unit else text


def fmt_count(n: int) -> str:
    """轮次显示:4 位及以内 "5124次";达万改用中文单位 "1万次"(不带小数)。

    cap 行右侧槽位实测仅 39px:"5124次" 35px、"99999次" 41px、"1.0万次"
    40px 都放不下,故万级不带小数("1万次" 28px、"12万次" 34px)。
    """
    if n >= 10000:
        return f"{n // 10000}万次"
    return f"{n}次"
