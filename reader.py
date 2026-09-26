"""ZCode 用量库只读读取:连接与查询。

纪律(CODING_STANDARDS「外部数据源只读纪律」):只读 URI 打开,
禁止任何写操作;本模块不得出现 execute 的 INSERT/UPDATE/DELETE/DDL。
"""

import sqlite3
from pathlib import Path

DEFAULT_DB = Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"


def open_ro(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    """以只读 URI 打开 SQLite;失败抛 sqlite3.Error / FileNotFoundError。"""
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def fetch_day_rows(conn: sqlite3.Connection, day_start_ms: int) -> list[tuple]:
    """今日全部调用行:(input, output, cache_read, computed_total)。"""
    return conn.execute(
        "SELECT input_tokens, output_tokens, cache_read_input_tokens,"
        " computed_total_tokens FROM model_usage WHERE started_at >= ?",
        (day_start_ms,),
    ).fetchall()


def fetch_top_models(conn: sqlite3.Connection, day_start_ms: int,
                     limit: int = 3) -> list[tuple]:
    """今日分模型总量倒序前 limit:[(model_id, computed_total)]。"""
    return conn.execute(
        "SELECT model_id, IFNULL(SUM(computed_total_tokens), 0) AS s"
        " FROM model_usage WHERE started_at >= ?"
        " GROUP BY model_id ORDER BY s DESC LIMIT ?",
        (day_start_ms, limit),
    ).fetchall()


def fetch_session_usage(conn: sqlite3.Connection,
                        session_id: str) -> tuple[int, int, int, int]:
    """单个会话开天辟地以来的用量合计:(总计, 输入, 输出, 缓存)。

    口径与今日行一致:computed_total_tokens 已含缓存读取。
    """
    row = conn.execute(
        "SELECT IFNULL(SUM(computed_total_tokens), 0),"
        " IFNULL(SUM(input_tokens), 0),"
        " IFNULL(SUM(output_tokens), 0),"
        " IFNULL(SUM(cache_read_input_tokens), 0)"
        " FROM model_usage WHERE session_id = ?", (session_id,)).fetchone()
    return tuple(int(v) for v in row)


def fetch_latest_session(conn: sqlite3.Connection) -> tuple[str, str, int] | None:
    """全库最近活跃会话:(session_id, title, time_updated 毫秒)。

    是"当前对话"的主信号:有 token 产出的会话即用户正在用的会话;
    一个会话都没有(全新环境)时返回 None。
    """
    row = conn.execute(
        "SELECT id, title, time_updated FROM session"
        " ORDER BY time_updated DESC LIMIT 1").fetchone()
    return (row[0], row[1] or "", int(row[2])) if row else None


def fetch_session_title(conn: sqlite3.Connection, session_id: str) -> str:
    """单个会话标题;不存在或为空返回空串(UI 显示占位)。"""
    row = conn.execute("SELECT title FROM session WHERE id = ?",
                       (session_id,)).fetchone()
    return (row[0] or "") if row else ""


def fetch_last_gen_rows(conn: sqlite3.Connection, day_start_ms: int,
                        per_model: int) -> list[tuple]:
    """各模型最近 per_model 条「已完成且有完整生成窗口」的调用行,整体按完成
    时刻倒序:(model_id, output_tokens, first_token_at, completed_at)。

    生成速率的取样口:只有 status='completed' 且两个时间戳齐全、有输出的今日
    行才算得上真实生成窗口。按模型分区各取最近若干条,故返回行数只随当日模型
    数增长(每模型 ≤ per_model),不随 model_usage 行数增长;多取几条是为了让
    上层在最近一条样本不可信时能退到该模型更早的样本。
    """
    return conn.execute(
        "SELECT model_id, output_tokens, first_token_at, completed_at FROM ("
        " SELECT model_id, output_tokens, first_token_at, completed_at,"
        " ROW_NUMBER() OVER (PARTITION BY model_id ORDER BY completed_at DESC)"
        " AS rn FROM model_usage"
        " WHERE started_at >= ? AND status = 'completed'"
        " AND output_tokens > 0 AND first_token_at IS NOT NULL"
        " AND completed_at IS NOT NULL)"
        " WHERE rn <= ? ORDER BY completed_at DESC",
        (day_start_ms, per_model)).fetchall()
