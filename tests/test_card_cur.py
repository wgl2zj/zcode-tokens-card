"""card 当前对话行反向测试:数字整值直显,绝不进 drip 摊放池。

预期来源(用户约定):当前对话用量"不加跳跃数字动效,也不跟着增量池走,
每次刷新直接显示当前汇总的真实数字"。当日数字走池是既有行为,用正向
对照组锁住,防止反向实现时误伤。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

import card as card_mod


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


def test_cur_not_in_tween_keys():
    """结构保证:当前对话字段不在补间/池字段表里。"""
    assert "cur" not in card_mod.TWEEN_KEYS


def test_cur_bypasses_drip_and_displays_real_value(card):
    """当前对话增量不入池,显示立即等于真实汇总。"""
    cur1 = {"title": "甲", "total": 100, "input": 90, "output": 5,
            "cache": 80}
    card.set_data({**_day(1000), "cur": cur1})
    card.set_data({**_day(1000), "cur": {**cur1, "total": 150, "input": 140}})
    assert card._sched.pending() == {}          # 反向:没进池
    assert card.cur["total"] == 150             # 正向:直显新真实值


def test_day_delta_still_enters_drip(card):
    """正向对照:当日增量照旧进池(反向实现没有误伤既有摊放)。"""
    cur = {"title": "甲", "total": 1, "input": 1, "output": 0, "cache": 0}
    card.set_data({**_day(1000), "cur": cur})
    card.set_data({**_day(1600), "cur": cur})
    pending = card._sched.pending()
    assert pending.get("total") == 600


def test_cur_missing_renders_nothing(card):
    """无会话数据时该行整体不画(cur 为 None),完整渲染不抛异常。"""
    card.set_data(_day(1000))
    assert card.cur is None
    card.grab()
