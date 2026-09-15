"""current 单测:合成 leveldb 字节片段,验证键值扫描与降级。

不读真实 localStorage 目录;真目录解析失败必须静默返回空候选。
"""

import current


SID_A = "sess_11111111-2222-3333-4444-555555555555"
SID_B = "sess_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

# 模拟 leveldb 记录:键前缀 + 路径 + 记录框字节 + 值(ASCII 形态)
REC_ASCII = (b"_file://\x00\x01zcode-v4-last-session:v1:D:\\proj"
             b"\x2a\x08" + SID_A.encode() + b"\x00\x01")
# UTF-16LE 形态(键与值都是宽字符)
REC_U16 = ("_file://\x00\x01zcode-v4-last-session:v1:D:\\工作区"
           "\x2a\x08" + SID_B).encode("utf-16-le")


# 真实形态:键 UTF-16LE、值 ASCII(Chromium 键值各自独立选编码)
REC_MIXED = "zcode-v4-last-session:v1:D:\\工作区".encode("utf-16-le") \
    + b"\x08\x00" + SID_B.encode("ascii")


def _write(directory, name, data):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(data)


def test_scan_ascii_and_utf16(tmp_path):
    _write(tmp_path, "000001.ldb", REC_ASCII)
    _write(tmp_path, "000002.log", REC_U16)
    assert set(current.scan_candidates(tmp_path)) == {SID_A, SID_B}


def test_scan_utf16_key_with_ascii_value(tmp_path):
    _write(tmp_path, "000001.log", REC_MIXED)
    assert current.scan_candidates(tmp_path) == [SID_B]


def test_scan_dedup(tmp_path):
    _write(tmp_path, "000001.log", REC_ASCII + REC_ASCII)
    assert current.scan_candidates(tmp_path) == [SID_A]


def test_scan_ignores_bare_session_ids(tmp_path):
    """没有 last-session 键前缀的 sess_* 出现不算候选。"""
    _write(tmp_path, "000001.log", b"composer-drafts sess_"
           + b"12345678-2222-3333-4444-555555555555")
    assert current.scan_candidates(tmp_path) == []


def test_scan_missing_dir(tmp_path):
    assert current.scan_candidates(tmp_path / "不存在") == []


def test_scan_skips_unreadable_files(tmp_path):
    """空文件/无匹配文件混在目录里不影响有效候选。"""
    _write(tmp_path, "000001.ldb", REC_ASCII)
    _write(tmp_path, "000002.log", b"")
    _write(tmp_path, "000003.log", b"whatever without keys")
    assert current.scan_candidates(tmp_path) == [SID_A]


G = "sess_00000000-0000-0000-0000-000000000000"   # 占位主会话 ID
Y = "sess_11111111-1111-1111-1111-111111111111"
Z = "sess_22222222-2222-2222-2222-222222222222"


def _resolver():
    return current.SessionResolver()


def test_resolve_first_poll_no_override():
    """首轮只建档:候选里有别的会话也不触发覆盖,返回库内最近活跃。"""
    r = _resolver()
    assert r.resolve([Y], G, 1000, 5000.0) == G


def test_resolve_fresh_candidate_overrides():
    """轮询中出现新会话 ID(切换动作)→ 立即跟随切换目标。"""
    r = _resolver()
    r.resolve([Y], G, 1000, 5000.0)
    assert r.resolve([Y, Z], G, 1000, 9000.0) == Z


def test_override_holds_while_g_quiet():
    """覆盖期间库内主会话无新活动 → 持续跟随切换目标(纯翻看场景)。"""
    r = _resolver()
    r.resolve([], G, 1000, 5000.0)
    r.resolve([Y], G, 1000, 9000.0)
    assert r.resolve([Y], G, 1000, 60000.0) == Y


def test_override_cleared_when_g_active():
    """切换之后主会话又产生活动(用户切回去用了)→ 回到主会话。"""
    r = _resolver()
    r.resolve([], G, 1000, 5000.0)
    r.resolve([Y], G, 1000, 9000.0)
    assert r.resolve([Y], G, 20000, 25000.0) == G


def test_override_cleared_when_override_becomes_latest():
    """在覆盖目标里继续聊天(它成了最近活跃)→ 正常显示它。"""
    r = _resolver()
    r.resolve([], G, 1000, 5000.0)
    r.resolve([Y], G, 1000, 9000.0)
    assert r.resolve([Y], Y, 20000, 25000.0) == Y


def test_resolve_fresh_equal_latest_no_override():
    """新出现的候选就是主会话本身 → 无需覆盖。"""
    r = _resolver()
    r.resolve([], G, 1000, 5000.0)
    assert r.resolve([G], G, 1000, 9000.0) == G


def test_resolve_none_when_no_sessions():
    assert _resolver().resolve([Y], None, 0, 0.0) is None
