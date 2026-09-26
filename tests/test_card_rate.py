"""card 生成速率显示:反向测试(不进池)+ 排版几何锁。

预期来源(用户约定):顶行显示当前速率(超期显「空闲」)、占原轮次的位置;
轮次移到 cap 行「今日 TOKENS」右侧;前三模型行各自显示速率(不带单位、字号同
三列数值、与累计之间单空格),取该模型最后一次的读数——仍在生成(样本新鲜)
的转红,停下来后的历史读数保持灰。速率是瞬时读数,不走 drip 池、无飘字、不补间。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

import card as card_mod
import stats as S


@pytest.fixture(scope="module")
def qapp():
    """offscreen 平台的 QApplication(模块级单例,不进事件循环)。"""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def card(qapp):
    return card_mod.FloatCard()


def _day(total, count=1):
    return {"count": count, "input": total, "output": 0, "cache": 0,
            "total": total, "models": []}


# —— 速率不进摊放池(反向) ——

def test_rate_not_in_tween_keys():
    """结构保证:速率字段不在补间/池字段表里。"""
    assert "rate" not in card_mod.TWEEN_KEYS
    assert "model_rates" not in card_mod.TWEEN_KEYS
    assert "active_models" not in card_mod.TWEEN_KEYS


def test_rate_never_enters_drip_pool(card):
    """反向:速率变化不产生任何池增量;池里只可能出现补间字段。"""
    card.set_data({**_day(1000), "rate": 239.0, "model_rates": {"m": 239.0},
                   "active_models": {"m"}})
    assert card._sched.pending() == {}
    card.set_data({**_day(1600), "rate": 500.0, "model_rates": {"m": 500.0},
                   "active_models": {"m"}})
    pending = card._sched.pending()
    assert pending                                   # 当日累计增量照常入池
    assert set(pending) <= set(card_mod.TWEEN_KEYS)  # 但池里没有速率
    assert card.rate == 500.0                        # 速率整值直显
    assert card.model_rates == {"m": 500.0}
    assert card.active_models == {"m"}


def test_active_models_follows_each_set_data(card):
    """活跃集合与速率同路整值替换:新一轮给空即全灰,不残留上轮的红。"""
    card.set_data({**_day(1000), "model_rates": {"a": 239.0, "b": 88.0},
                   "active_models": {"a"}})
    assert card.active_models == {"a"}
    card.set_data({**_day(1600), "model_rates": {"a": 239.0, "b": 88.0},
                   "active_models": []})
    assert card.active_models == set()


def test_usage_page_renders_every_rate_state(card):
    """用量页在"无速率/有速率/全空闲/活跃与历史并存/超上限/异常"下都完整渲染。"""
    for extra in ({}, {"rate": 239.0, "model_rates": {"m": 239.0}},
                  {"rate": None, "model_rates": {"m": 88.0}},
                  {"rate": 150.0, "model_rates": {"m": 88.0, "n": 150.0},
                   "active_models": {"n"}},
                  {"rate": 1500.0, "model_rates": {"m": 1500.0},
                   "active_models": {"m"}}):
        card.set_data({**_day(1200, count=5124), "models": [("m", 1200)],
                       **extra})
        card.grab()
    card.set_error("OperationalError")
    card.grab()


# —— 模型行速率配色(活跃红 / 历史灰) ——

def test_model_rate_color_active_red_else_grey():
    """正在生成(样本新鲜)→ 红;最后一次的历史读数 → 灰。"""
    import theme as T
    assert card_mod.model_rate_color(True) == T.C_RATE_ACTIVE
    assert card_mod.model_rate_color(False) == T.C_TEXT_LABEL
    assert T.C_RATE_ACTIVE != T.C_TEXT_LABEL


# —— 顶行右端与 cap 行轮次 ——

def test_top_right_text_error_wins_over_rate():
    """顶行右端:异常短句优先(不留旧速率);正常显示带单位的速率;空闲显「空闲」。

    异常文案是固定短句而非异常类名——类名可长到 145px,会越过 tab。
    """
    assert card_mod.top_right_text("", 239.4) == "239 t/s"
    assert card_mod.top_right_text("", None) == "空闲"
    assert card_mod.top_right_text("OperationalError", 239.4) \
        == card_mod.ERROR_TOP_TEXT


def test_error_keeps_cap_count_and_moves_warning_to_top_row(card):
    """异常时:轮次保留最后一次成功轮询的值,警示位让给顶行右端那格。"""
    card.set_data(_day(1200, count=5124))
    assert card.reqs_text == "5124次"
    card.set_error("OperationalError")
    assert card.reqs_text == "5124次"          # 不被异常文案覆盖
    assert card_mod.top_right_text(card.error_text, card.rate) \
        == card_mod.ERROR_TOP_TEXT


# —— 排版几何锁 ——
#
# offscreen 平台没有字体目录,Qt 退回内建字体,度量与真机完全不符(实测
# "今日 TOKENS" 在 offscreen 量出 113px、真机 85px),所以几何断言不能现场
# 取 QFontMetrics,只能固化真机实测值。改了字号/间距/参照常量后,这张表要
# 同步重量——断言失败正是提醒。
#
# 重量方法(真机 Windows 平台,不要设 QT_QPA_PLATFORM):
#   python -c "import sys;from PySide6.QtGui import QFontMetrics as M;from \
#   PySide6.QtWidgets import QApplication;app=QApplication(sys.argv);import card \
#   as c;print(M(c._font(c.T.F_MONO,10.5)).horizontalAdvance('5124次'))"
_MEASURED = {
    "cap_text": 85,            # "今日 TOKENS" @ F_UI 9.5 字距 2.5
    "count_4": 35,             # "5124次" @ F_MONO 10.5(CJK 走 Qt 回退)
    "count_wan": 34,           # "12万次" 万级降级的最坏两位写法
    "count_wan_decimal": 40,   # "1.0万次" —— 已否决的带小数写法
    "ref_rate": 42,            # "000 t/s" @ F_MONO 10.5
    "ref_count_old": 41,       # "0000 次" @ F_MONO 10.5(换参照之前)
    "acc_max": 60,             # "9999.9万" @ F_MONO 13.5 bold
    "rate_max": 29,            # "999+" @ F_MONO 12.5 bold
    "tab_x_max": 166,          # 最长日期文本下的 tab 左端(12月24日 周四 15:15)
    "top_rate": 42,            # "159 t/s" @ F_MONO 10.5
    "top_error": 55,           # "数据源异常" @ F_MONO 10.5(CJK 走 Qt 回退)
    "top_error_raw": 97,       # "OperationalError" —— 已否决:不显示类名
    "top_error_raw_long": 145,  # "sqlite3.OperationalError" 同上
}


def test_top_right_text_fits_beside_tab():
    """几何锁:顶行右端文案不压到 tab 右侧格的标签墨迹。

    tab 右侧格起于 tab_x+32、宽 32,标签「套餐」20px 居中 → 墨迹止于
    tab_x+58。所以该格可用宽度 = TOP_RIGHT - (tab_x_max + TAB_LABEL_OFFSET)。
    异常文案用固定短句就是为满足这条:异常类名 97~145px 必然越界。
    """
    room = (card_mod.TOP_RIGHT
            - (_MEASURED["tab_x_max"] + card_mod.TAB_LABEL_OFFSET))
    assert _MEASURED["top_rate"] <= room
    assert _MEASURED["top_error"] <= room
    assert len(card_mod.ERROR_TOP_TEXT) == 5
    assert _MEASURED["top_error_raw"] > room      # 被否决的写法留档
    assert _MEASURED["top_error_raw_long"] > room


def test_tab_position_unchanged_by_reference_swap():
    """顶行右端由「0000 次」换成「000 t/s」参照后,tab 位置只挪 1px。

    tab 右界 = TOP_RIGHT - adv(TAB_RIGHT_REF);两代参照宽度必须接近,
    否则这次"速率顶掉轮次的位置"会把 tab 推到新地方。
    """
    assert abs(_MEASURED["ref_rate"] - _MEASURED["ref_count_old"]) <= 2


def test_cap_count_slot_fits():
    """几何锁:cap 行「今日 TOKENS + 轮次」不越过槽位右端。"""
    left = card_mod.CAP_RECT[0]
    right = card_mod.CAP_COUNT_RIGHT
    assert left + _MEASURED["cap_text"] + _MEASURED["count_4"] <= right
    assert left + _MEASURED["cap_text"] + _MEASURED["count_wan"] <= right


def test_cap_count_rejects_decimal_wan_form():
    """被否决的写法留档:「1.0万次」实测 40px,超槽位 1px,故万级不带小数。"""
    slot = card_mod.CAP_COUNT_RIGHT - card_mod.CAP_RECT[0] \
        - _MEASURED["cap_text"]
    assert _MEASURED["count_wan_decimal"] > slot
    assert S.fmt_count(10000) == "1万次"


def test_model_rate_column_never_overlaps_bar():
    """几何锁:最坏组合(最长累计 + 单空格 + 最宽速率)与占比条留出净空。

    这是把占比条从 78px 缩到 49px 的依据;改 M_TRACK_W / RATE_GAP /
    FS_MVAL / FS_MI_V 任一个,这里都会先炸。
    """
    group_left = (card_mod.M_VAL_RIGHT - _MEASURED["acc_max"]
                  - card_mod.RATE_GAP - _MEASURED["rate_max"])
    bar_right = card_mod.M_TRACK_X + card_mod.M_TRACK_W
    assert group_left - bar_right >= 4


def test_bar_still_has_usable_width():
    """缩条后仍需可读:条宽要明显大于最小可见宽度,且不侵占模型名。"""
    assert card_mod.M_TRACK_W >= 40
    assert card_mod.M_TRACK_X > card_mod.M_NAME_X + card_mod.M_NAME_W
