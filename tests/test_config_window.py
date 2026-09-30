"""配置窗口测试:选项模型(选哪行 = 存哪个值)、回填、几何与保存链路。

数据纪律:一律用合成占位 key 与 tmp_path 状态文件;既不读 ~/.zcode 真机配置
(构造窗口时显式传入候选),也不写本机真实 state.json。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

import config
import config_window as CW
import quota as Q


def _fake_key(tag: str) -> str:
    """合成占位 key:拼装生成(明确非真实凭据,也避开"硬编码凭据"扫描的误判)。"""
    return tag + "-" + "placeholder"


CANDIDATES = [Q.KeyCandidate("opencode-go-chat", _fake_key("go")),
              Q.KeyCandidate("275257b2-0e9e-4fb8-a69f-09876a076c46",
                             _fake_key("k2"))]


@pytest.fixture(scope="module")
def qapp():
    """offscreen 平台的 QApplication(模块级单例,不进事件循环)。"""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    return CW.KeyConfigWindow(CANDIDATES, "", Q.ResolvedKey())


# —— 选项模型(纯逻辑) ——

def test_rows_order_is_auto_keys_manual():
    """行序固定:自动发现(默认,首行)→ ZCode 配置发现的 key → 手动输入(末行)。"""
    rows = CW.build_rows(CANDIDATES)
    assert [r["kind"] for r in rows] == [CW.KIND_AUTO, CW.KIND_KEY,
                                         CW.KIND_KEY, CW.KIND_MANUAL]
    assert CW.build_rows([]) == [{"kind": CW.KIND_AUTO},
                                 {"kind": CW.KIND_MANUAL}]


def test_row_index_backfills_from_configured():
    """回填:空/空白 = 自动发现;命中某个发现的 key = 该行;未知值 = 手动输入行。"""
    rows = CW.build_rows(CANDIDATES)
    assert CW.row_index_for(rows, "") == 0
    assert CW.row_index_for(rows, "   ") == 0
    assert CW.row_index_for(rows, CANDIDATES[1].api_key) == 2
    assert CW.row_index_for(rows, _fake_key("huh")) == len(rows) - 1


@pytest.mark.parametrize("index,text,expected", [
    (0, "ignored", ""),                                    # 自动发现 → 存空值
    (1, "ignored", CANDIDATES[0].api_key),                 # key 行 → 存该 key
    (2, "ignored", CANDIDATES[1].api_key),
    (3, "  typed  ", "typed"),                             # 手动 → 存输入(去空白)
    (3, "", ""),
    (99, "typed", ""),                                     # 越界保守取空
])
def test_selected_value_maps_row_to_value(index, text, expected):
    """选中行 → 配置值:自动发现存空串(回落自动发现),不存明文以外的任何加工值。"""
    rows = CW.build_rows(CANDIDATES)
    assert CW.selected_value(rows, index, text) == expected


def test_layout_grows_with_rows_and_caps():
    """行数增长时窗口变高;超过 KEYWIN_ROWS_MAX 时按上限封顶(其余靠滚轮)。"""
    short = CW.layout(2)
    long = CW.layout(6)
    assert long["height"] > short["height"]
    assert long["visible"] == 6
    assert CW.layout(50)["visible"] == CW.T.KEYWIN_ROWS_MAX
    assert CW.layout(50)["rows_h"] == CW.T.KEYWIN_ROWS_MAX * CW.ROW_H


def test_row_at_hit_test_and_scroll():
    """行命中判定:选项区外返回 None,区内按行高折算,滚轮偏移参与计算。"""
    top = CW.ROWS_TOP
    assert CW.KeyConfigWindow.row_at(QPoint(60, top - 1), 4, 0) is None
    assert CW.KeyConfigWindow.row_at(QPoint(60, top + 1), 4, 0) == 0
    assert CW.KeyConfigWindow.row_at(QPoint(60, top + CW.ROW_H + 1), 4, 0) == 1
    assert CW.KeyConfigWindow.row_at(QPoint(60, top + 1), 4, 1) == 1
    # 区内但超出实际行数(行数少于可视行数时的空白带)不误命中
    assert CW.KeyConfigWindow.row_at(QPoint(60, top + 3 * CW.ROW_H), 2, 0) is None


def test_btn_at_hit_test():
    """两按钮命中区互不重叠,以外区域不命中(点击分派依赖它)。"""
    h = CW.layout(len(CW.build_rows(CANDIDATES)))["height"]
    save = CW.KeyConfigWindow._btn_rects(h)["save"]
    cancel = CW.KeyConfigWindow._btn_rects(h)["cancel"]
    assert not save.intersects(cancel)
    assert CW.KeyConfigWindow.btn_at(save.center(), h) == "save"
    assert CW.KeyConfigWindow.btn_at(cancel.center(), h) == "cancel"
    assert CW.KeyConfigWindow.btn_at(QPoint(save.left() - 5, save.center().y()),
                                     h) is None


# —— 窗口状态 ——

def test_field_enabled_only_for_manual_row(win):
    """输入框只在选中"手动输入"行时可用;切走即清空并置灰。"""
    assert win.sel == 0 and win.line.isEnabled() is False
    win.sel = len(win.rows) - 1
    win.manual_text = _fake_key("typed")
    win._sync_selection()
    assert win.line.isEnabled() is True
    assert win.line.text() == _fake_key("typed")
    win.sel = 0
    win._sync_selection()
    assert win.line.isEnabled() is False
    assert win.line.text() == ""


def test_refresh_rebackfills_configured(win, tmp_path):
    """刷新(重复打开):按最新配置值回填选中行与输入框。"""
    win.refresh(CANDIDATES, CANDIDATES[0].api_key, Q.ResolvedKey())
    assert win.sel == 1
    win.refresh(CANDIDATES, _fake_key("mystery"), Q.ResolvedKey())
    assert win.sel == len(win.rows) - 1
    assert win.line.text() == _fake_key("mystery")
    win.refresh(CANDIDATES, "", Q.ResolvedKey())
    assert win.sel == 0


@pytest.mark.parametrize("sel,expected", [(0, "auto"), (3, "manual")])
def test_renders_every_selection_state(win, sel, expected):
    """三种选中态都能完整渲染不抛异常(截图验收的自动化前置)。"""
    win.sel = sel
    win.manual_text = _fake_key("typed")
    win._sync_selection()
    win.status = "示例提示" if expected == "manual" else ""
    win.grab()


# —— 保存链路(状态文件落在 tmp_path) ——

@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """把状态文件指向 tmp_path:保存链路可测,且不碰本机真实 state.json。"""
    path = tmp_path / "state.json"
    monkeypatch.setattr(config, "config_path", lambda: path)
    return path


def test_save_persists_and_emits(win, tmp_state):
    """保存:写 state.json 的 quota_api_key、发 key_saved(新值)、关闭窗口。"""
    got = []
    win.key_saved.connect(got.append)
    win.sel = 1
    win._save()
    assert config.load(tmp_state)["quota_api_key"] == CANDIDATES[0].api_key
    assert got == [CANDIDATES[0].api_key]
    assert win.isVisible() is False


def test_save_auto_row_clears_configured_key(win, tmp_state):
    """选「自动发现」保存 = 写入空值(回落自动发现),不是把当前 key 再存一遍。"""
    config.save(tmp_state, quota_api_key=CANDIDATES[0].api_key)
    got = []
    win.key_saved.connect(got.append)
    win.refresh(CANDIDATES, CANDIDATES[0].api_key, Q.ResolvedKey())
    win.sel = 0
    win._save()
    assert config.load(tmp_state)["quota_api_key"] == ""
    assert got == [""]


def test_save_manual_value(win, tmp_state):
    """手动输入行保存:写入去空白后的明文。"""
    got = []
    win.key_saved.connect(got.append)
    win.sel = len(win.rows) - 1
    win.manual_text = f"  {_fake_key('typed')}  "
    win._save()
    assert config.load(tmp_state)["quota_api_key"] == _fake_key("typed")
    assert got == [_fake_key("typed")]


def test_save_empty_manual_is_blocked(win, tmp_state):
    """手动输入为空:不保存、不关窗、不发信号,窗口内如实提示。"""
    got = []
    win.key_saved.connect(got.append)
    win.sel = len(win.rows) - 1
    win.manual_text = "   "
    win._save()
    assert got == [] and win.status_error is True and win.status
    assert "quota_api_key" not in config.load(tmp_state)


def test_save_failure_is_reported_not_faked(win, tmp_path, monkeypatch):
    """写盘失败(父目录不存在):不谎报成功——不关窗、不发信号、状态行转报错。"""
    monkeypatch.setattr(config, "config_path",
                        lambda: tmp_path / "no_dir" / "state.json")
    got = []
    win.key_saved.connect(got.append)
    win.sel = 1
    win._save()
    assert got == []
    assert win.status_error is True and "state.json" in win.status
