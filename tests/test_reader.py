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
    """临时 SQLite 库:建表 + 造三条今日数据、一条昨日数据、两个会话。"""
    path = tmp_path / "usage_test.sqlite"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE model_usage (model_id TEXT, started_at INTEGER,"
        " input_tokens INT, output_tokens INT, cache_read_input_tokens INT,"
        " computed_total_tokens INT, session_id TEXT)")
    conn.execute(
        "CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT,"
        " time_updated INTEGER)")
    start = S.today_start_ms()
    conn.executemany(
        "INSERT INTO model_usage VALUES (?,?,?,?,?,?,?)",
        [
            ("GLM-5.3-Flash", start + 1000, 100, 10, 50, 160, "sess_a"),
            ("GLM-5.3-Flash", start + 2000, 200, 20, 80, 300, "sess_b"),
            ("k3", start + 3000, 50, 5, 10, 65, "sess_a"),
            ("GLM-5.3", start - 86400000, 999, 999, 999, 2997,
             "sess_a"),  # 昨日,应排除
        ])
    conn.executemany(
        "INSERT INTO session VALUES (?,?,?)",
        [("sess_a", "会话甲", 100), ("sess_b", "会话乙", 200)])
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


def test_fetch_session_usage(tmp_conn):
    """按会话跨天全量合计(含昨日行):(总计, 输入, 输出, 缓存)。"""
    assert reader.fetch_session_usage(tmp_conn, "sess_a") \
        == (160 + 65 + 2997, 100 + 50 + 999, 10 + 5 + 999, 50 + 10 + 999)


def test_fetch_session_usage_empty(tmp_conn):
    assert reader.fetch_session_usage(tmp_conn, "sess_无") == (0, 0, 0, 0)


def test_fetch_latest_session(tmp_conn):
    """全库最近活跃会话:id/title/时间戳三元组。"""
    assert reader.fetch_latest_session(tmp_conn) == ("sess_b", "会话乙", 200)


def test_fetch_latest_session_none(tmp_conn):
    tmp_conn.execute("DELETE FROM session")
    tmp_conn.commit()
    assert reader.fetch_latest_session(tmp_conn) is None


def test_fetch_session_title(tmp_conn):
    assert reader.fetch_session_title(tmp_conn, "sess_a") == "会话甲"
    assert reader.fetch_session_title(tmp_conn, "sess_无") == ""


# —— 生成速率取样(fetch_last_gen_rows) ——

@pytest.fixture
def tmp_gen_conn(tmp_path):
    """临时库(速率取样专用):造合格行与五类应排除行,验证筛选、分区与排序。

    独立于 tmp_conn 的简化表——那张表没有 status/first_token_at/
    completed_at,不动它以免牵连既有测试。
    """
    path = tmp_path / "gen_test.sqlite"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE model_usage (model_id TEXT, started_at INTEGER,"
        " output_tokens INT, first_token_at INT, completed_at INT,"
        " status TEXT)")
    start = S.today_start_ms()
    conn.executemany(
        "INSERT INTO model_usage VALUES (?,?,?,?,?,?)",
        [
            # 模型 a 四条合格(完成时刻递增);per_model=3 时应裁掉最早那条
            ("a", start + 1000, 300, start + 2000, start + 3000, "completed"),
            ("a", start + 4000, 240, start + 5000, start + 6000, "completed"),
            ("a", start + 7000, 210, start + 8000, start + 9000, "completed"),
            ("a", start + 10000, 180, start + 11000, start + 12000,
             "completed"),
            # 模型 b 一条合格(整体最新)
            ("b", start + 13000, 200, start + 14000, start + 15000,
             "completed"),
            # 各排除一类:未完成 / 无首字时刻 / 无输出 / 已取消 / 昨日
            ("running", start + 8000, 500, start + 8500, None, "running"),
            ("no_ft", start + 8000, 500, None, start + 9000, "completed"),
            ("no_out", start + 8000, 0, start + 8500, start + 9000,
             "completed"),
            ("cancel", start + 8000, 500, start + 8500, start + 9000,
             "cancelled"),
            ("yesterday", start - 86400000, 999, start - 86399000,
             start - 86398000, "completed"),
        ])
    conn.commit()
    yield conn
    conn.close()
    assert REAL_DB_MARKER not in str(path)


def test_fetch_last_gen_rows_per_model_and_order(tmp_gen_conn):
    """每模型只取最近 per_model 条,整体按完成时刻倒序(a 的最早一条被裁)。"""
    rows = reader.fetch_last_gen_rows(tmp_gen_conn, S.today_start_ms(), 3)
    assert [r[0] for r in rows] == ["b", "a", "a", "a"]
    assert [r[3] for r in rows] == sorted((r[3] for r in rows), reverse=True)


def test_fetch_last_gen_rows_excludes_unusable(tmp_gen_conn):
    """未完成 / 缺首字时刻 / 无输出 / 已取消 / 昨日 → 一律不作速率样本。"""
    rows = reader.fetch_last_gen_rows(tmp_gen_conn, S.today_start_ms(), 10)
    assert {r[0] for r in rows} == {"a", "b"}


def _fill_gen_conn(path, n_rows: int, n_models: int):
    """造 n_rows 行、n_models 个模型的合格样本(完成时刻随行号递增)。"""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE model_usage (model_id TEXT, started_at INTEGER,"
        " output_tokens INT, first_token_at INT, completed_at INT,"
        " status TEXT)")
    start = S.today_start_ms()
    conn.executemany(
        "INSERT INTO model_usage VALUES (?,?,?,?,?,?)",
        [(f"m{i % n_models}", start + i * 1000, 100,
          start + i * 1000 + 500, start + i * 1000 + 900, "completed")
         for i in range(n_rows)])
    conn.commit()
    return conn


def test_fetch_last_gen_rows_count_bounded_by_models(tmp_path):
    """查询形态回归:返回行数 = 模型数 × per_model 上限,不随总行数增长。

    轮询成本必须与 model_usage 行数脱钩:40 行与 4000 行取回的条数一致。
    """
    small_path, big_path = tmp_path / "小.sqlite", tmp_path / "大.sqlite"
    small = _fill_gen_conn(small_path, 40, 2)
    big = _fill_gen_conn(big_path, 4000, 2)
    try:
        r_small = reader.fetch_last_gen_rows(small, S.today_start_ms(), 3)
        r_big = reader.fetch_last_gen_rows(big, S.today_start_ms(), 3)
        assert len(r_small) == len(r_big) == 2 * 3
        assert {r[0] for r in r_big} == {"m0", "m1"}
    finally:
        small.close()
        big.close()
        assert REAL_DB_MARKER not in str(small_path) + str(big_path)
