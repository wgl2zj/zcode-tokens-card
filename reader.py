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
