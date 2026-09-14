"""reader 单测:临时库自建数据,断言只读纪律与查询口径。

夹具自证:使用的库路径在 tmp 目录,与真实库(~/.zcode)无关。
"""

import sqlite3

import pytest

import reader
import stats as S

REAL_DB_MARKER = "db.sqlite"


@pytest.fixture
def tmp_conn(tmp_path):
    """临时 SQLite 库:建表 + 造三条今日数据、一条昨日数据。"""
    path = tmp_path / "usage_test.sqlite"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE model_usage (model_id TEXT, started_at INTEGER,"
        " input_tokens INT, output_tokens INT, cache_read_input_tokens INT,"
        " computed_total_tokens INT)")
    start = S.today_start_ms()
    conn.executemany(
        "INSERT INTO model_usage VALUES (?,?,?,?,?,?)",
        [
            ("GLM-5.3-Flash", start + 1000, 100, 10, 50, 160),
            ("GLM-5.3-Flash", start + 2000, 200, 20, 80, 300),
            ("k3", start + 3000, 50, 5, 10, 65),
            ("GLM-5.3", start - 86400000, 999, 999, 999, 2997),  # 昨日,应排除
        ])
    conn.commit()
    yield conn
    conn.close()
    assert REAL_DB_MARKER not in str(path)


def test_open_ro_blocks_writes(tmp_path):
    """只读纪律:mode=ro 打开后写入必须失败。"""
    path = tmp_path / "ro_test.sqlite"
    setup = sqlite3.connect(str(path))
    setup.execute("CREATE TABLE t (a INT)")
    setup.commit()
    setup.close()
    ro = reader.open_ro(path)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO t VALUES (1)")


def test_open_ro_missing_file(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        reader.open_ro(tmp_path / "不存在.sqlite")


def test_fetch_day_rows_excludes_yesterday(tmp_conn):
    rows = reader.fetch_day_rows(tmp_conn, S.today_start_ms())
    assert len(rows) == 3
    assert sum(r[3] for r in rows) == 525


def test_fetch_top_models(tmp_conn):
    """今日只有 2 个模型有量 → TOP3 返回 2 条(不足按实际数量)。"""
    top = reader.fetch_top_models(tmp_conn, S.today_start_ms(), 3)
    assert top[0] == ("GLM-5.3-Flash", 460)
    assert top == [("GLM-5.3-Flash", 460), ("k3", 65)]
