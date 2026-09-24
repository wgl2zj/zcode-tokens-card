"""card tab 切换与套餐页(tab 1)行为测试。

预期来源(用户要求):既有"用量"页作为 tab 0 保持不动,新增 tab 1 承载
OpenCode Go 套餐额度,点击切换、拖动仍照旧。这里锁三件事:
  1) tab 0 的数值与 drip 摊放池不因切 tab 改变(正向对照组);
  2) tab 1 在"无数据 / 有数据 / 异常 / 陈旧"各状态下都能完整渲染;
  3) 命中判定与点击阈值是纯几何逻辑,点击/拖动分派可复核。
"""

import datetime
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QFontMetrics, QMouseEvent
from PySide6.QtWidgets import QApplication

import card as card_mod
import quota as Q

UTC = datetime.timezone.utc


@pytest.fixture(scope="module")
def qapp():
    """offscreen 平台的 QApplication(模块级单例,不进事件循环)。"""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def card(qapp):
    return card_mod.FloatCard()


def _day(total):
    return {"count": 1, "input": total, "output": 0, "cache": 0,
            "total": total, "models": []}


def _windows(percent=(14, 19, 9)):
    """构造三窗口数据:重置时间分别为 2h13m / 3d / 28d 之后。"""
    now = datetime.datetime.now(UTC)
    offsets = (133, 3 * 24 * 60, 28 * 24 * 60)
    return [Q.Window(key, label, pct, now + datetime.timedelta(minutes=m))
            for (key, label), pct, m in zip(Q.WINDOW_KEYS, percent, offsets)]


def _click(card, x, y):
    """在卡片坐标 (x, y) 处模拟一次完整的按下→释放(带 SHADOW_PAD 偏移)。"""
    wx, wy = x + 14, y + 14
    local = QPointF(wx, wy)
    glob = QPointF(card.mapToGlobal(QPoint(wx, wy)))
    card.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, local, glob,
                                     Qt.LeftButton, Qt.LeftButton,
                                     Qt.NoModifier))
    card.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, local, glob,
                                       Qt.LeftButton, Qt.NoButton,
                                       Qt.NoModifier))


# —— tab 命中与点击阈值 ——

def test_default_tab_is_usage(card):
    """默认停在既有"用量"页,启动画面与改动前一致。"""
    assert card.tab == 0


def test_tab_at_hit_test():
    """命中判定:左格 → 0,右格 → 1,控件外 → None。"""
    x = card_mod.tab_x("9月24日 周四 15:15")
    cy = card_mod.TAB_Y + card_mod.TAB_H // 2
    assert card_mod.FloatCard.tab_at(QPoint(x + 4, cy), x) == 0
    assert card_mod.FloatCard.tab_at(
        QPoint(x + card_mod.TAB_W // 2 + 4, cy), x) == 1
    assert card_mod.FloatCard.tab_at(QPoint(x - 10, cy), x) is None
    assert card_mod.FloatCard.tab_at(
        QPoint(x + 4, card_mod.TAB_Y + card_mod.TAB_H + 10), x) is None


def test_tab_centered_between_head_and_count():
    """tab 居中:与左侧日期时钟、右侧次数的间距相等(误差 ≤1px),且比兜底位右移。"""
    head = "9月24日 周四 15:15"
    x = card_mod.tab_x(head)
    fm_head = QFontMetrics(card_mod._font(card_mod.T.F_UI, card_mod.T.FS_HEAD,
                                          weight=QFont.DemiBold))
    fm_req = QFontMetrics(card_mod._font(card_mod.T.F_MONO, card_mod.T.FS_REQ))
    left_end = card_mod.TOP_TEXT_X + fm_head.horizontalAdvance(head)
    right_start = (card_mod.TOP_RIGHT
                   - fm_req.horizontalAdvance(card_mod.TAB_RIGHT_REF))
    gap_left = x - left_end
    gap_right = right_start - (x + card_mod.TAB_W)
    assert abs(gap_left - gap_right) <= 1
    assert x >= card_mod.TAB_DEFAULT_X


def test_tab_x_tracks_head_text_width():
    """居中位置随左侧文本宽度变化(长文本 → tab 右移),但右侧参照不随次数位数抖动。"""
    short = card_mod.tab_x("9月1日 周一 9:05")
    long = card_mod.tab_x("12月24日 周四 15:15")
    assert long > short
    assert card_mod.tab_x("9月24日 周四 15:15") == card_mod.tab_x(
        "9月24日 周四 15:15")          # 同文本同结果(纯函数)


@pytest.mark.parametrize("dx,dy,expected", [
    (0, 0, True), (3, 0, True), (2, 2, True), (4, 0, True), (5, 0, False),
    (0, 9, False),
])
def test_is_click_threshold(dx, dy, expected):
    """位移 ≤4px 视为点击,超过视为拖动。"""
    assert card_mod.is_click(QPoint(100, 100),
                             QPoint(100 + dx, 100 + dy)) is expected


def test_click_on_tab_switches_and_click_does_not_save_pos(card, monkeypatch):
    """点击 tab 切页;纯点击不写窗口位置(只有拖动才保存)。"""
    saved = []
    monkeypatch.setattr(card_mod.cfg, "save",
                        lambda **kv: saved.append(kv))
    x = card_mod.tab_x()
    cy = card_mod.TAB_Y + card_mod.TAB_H // 2
    _click(card, x + card_mod.TAB_W // 2 + 4, cy)
    assert card.tab == 1
    _click(card, x + 4, cy)
    assert card.tab == 0
    assert saved == []


def test_drag_keeps_tab_and_saves_pos(card, monkeypatch):
    """位移超过阈值按拖动处理:不切页,松手后保存位置。"""
    saved = []
    monkeypatch.setattr(card_mod.cfg, "save",
                        lambda **kv: saved.append(kv))
    x = card_mod.tab_x()
    cy = card_mod.TAB_Y + card_mod.TAB_H // 2
    wx, wy = x + card_mod.TAB_W // 2 + 4 + 14, cy + 14
    local = QPointF(wx, wy)
    glob = QPointF(card.mapToGlobal(QPoint(wx, wy)))
    card.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, local, glob,
                                     Qt.LeftButton, Qt.LeftButton,
                                     Qt.NoModifier))
    card.mouseReleaseEvent(QMouseEvent(
        QEvent.MouseButtonRelease, QPointF(wx + 30, wy + 30),
        QPointF(glob.x() + 30, glob.y() + 30),
        Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
    assert card.tab == 0
    assert len(saved) == 1


# —— tab 0 不受影响(正向对照) ——

def test_tab0_numbers_and_pool_untouched_by_tab_switch(card):
    """切到套餐页再切回:真实值照常跟进、增量照常入池,补间目标不被改写。

    注意 tab 切换期间没有帧循环,故 drip 池只累积不释放(set_data 不直接
    改 tw),这里正是要锁"切 tab 不安动 tab 0 的补间与池"。
    """
    card.set_data(_day(1000))
    card.set_data(_day(1600))                      # 增量 600 入池
    assert card._sched.pending().get("total") == 600
    target_before = card.tw["total"].end()

    card.tab = 1
    card.grab()                                    # 渲染套餐页
    card.set_data(_day(2000))                      # 套餐页期间增量照常入池
    assert card._sched.pending().get("total") == 1000
    assert card._last_real["total"] == 2000        # 真实值照常跟进
    assert card.tw["total"].end() == target_before  # 补间目标未被切 tab 改写

    card.tab = 0
    card.grab()


def test_quota_values_never_enter_drip_pool(card):
    """反向:额度数值不走 drip 池(额度以分钟级变化,不需要摊放)。"""
    card.set_quota(_windows(), time.time())
    assert card._sched.pending() == {}


# —— tab 1 数据与渲染 ——

def test_quota_first_set_snaps_then_tweens(card):
    """首帧落位(不从 0 爬升),其后走补间打到新目标。"""
    card.set_quota(_windows(percent=(14, 19, 9)), time.time())
    assert card.q_tw["q0"].value() == 14.0
    assert card.q_tw["qbig"].value() == 19.0        # 大数字取已用最高的窗口

    card.set_quota(_windows(percent=(60, 19, 9)), time.time())
    assert card.q_tw["q0"].end() == 60.0            # 目标已更新
    assert card.q_tw["q0"].value() < 60.0           # 仍在补间中途
    assert card.q_tw["qbig"].end() == 60.0


def test_quota_error_keeps_last_values(card):
    """异常只改状态:上次数值与取数时刻保留,供"显示 X 时刻数据"用。"""
    ts = time.time() - 30
    card.set_quota(_windows(), ts)
    card.set_quota_error("连接失败")
    assert [w.percent for w in card.quota_windows] == [14.0, 19.0, 9.0]
    assert card.quota_fetched_at == ts
    assert card.quota_error == "连接失败"
    assert card.quota_error_kind == "io"
    card.tab = 1
    assert card._top_problem() is True               # 套餐页上呼吸灯转警示色


def test_light_follows_current_tab(card):
    """呼吸灯语义随当前页走:套餐异常不影响用量页的灯(反之亦然)。"""
    card.set_data(_day(1000))                        # 用量页数据源正常
    card.set_quota_error("连接失败")
    assert card._top_problem() is False              # tab 0:只看用量数据源
    card.tab = 1
    assert card._top_problem() is True               # tab 1:只看额度状态
    card.tab = 0
    card.set_error("OperationalError")               # 用量数据源异常
    card.set_quota(_windows(), time.time())          # 额度恢复正常
    assert card._top_problem() is True
    card.tab = 1
    assert card._top_problem() is False


def test_quota_config_error_is_not_problem(card):
    """未配置(无 Key)按提示处理,不当作故障:灯不转红、状态行灰字。"""
    card.set_quota_error("未配置 OpenCode Go（需 API Key）", kind="config")
    assert card._top_problem() is False
    text, color = card._quota_status(stale=False)
    assert text.startswith("未配置")
    assert color == card_mod.T.C_TEXT_LABEL


def test_stale_marks_problem_and_status(card):
    """取数超过 QUOTA_MAX_AGE_S 视为陈旧:状态行转警示色。"""
    card.tab = 1
    card.set_quota(_windows(), time.time() - card_mod.T.QUOTA_MAX_AGE_S - 5)
    assert card._top_problem() is True
    text, color = card._quota_status(stale=True)
    assert "陈旧" in text
    assert color == card_mod.T.C_ERROR


@pytest.mark.parametrize("state", ["empty", "ok", "io_error", "stale",
                                   "config_error"])
def test_quota_page_renders_every_state(card, state):
    """套餐页在各状态下完整渲染不抛异常(截图验收的自动化前置)。"""
    card.tab = 1
    if state == "empty":
        pass
    elif state == "ok":
        card.set_quota(_windows(), time.time())
    elif state == "io_error":
        card.set_quota(_windows(), time.time() - 10)
        card.set_quota_error("连接失败")
    elif state == "stale":
        card.set_quota(_windows(), time.time() - 3600)
    elif state == "config_error":
        card.set_quota_error("未配置 OpenCode Go（需 API Key）", kind="config")
    card.grab()


def test_quota_warn_color_at_threshold(card):
    """已用达 QUOTA_WARN_PCT 时大数字走警示色(阈值取自主题常量)。"""
    card.set_quota(_windows(percent=(95, 19, 9)), time.time())
    assert card.q_tw["qbig"].value() >= card_mod.T.QUOTA_WARN_PCT
