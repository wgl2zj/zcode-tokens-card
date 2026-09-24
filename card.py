"""横卡窗口:QPainter 全量自绘(布局、动画、拖动、tab 切换交互)。

纸感浅色皮肤(选型稿 01 号):296x218,暖白纸底 + 细灰线 + 橙强调。
顶行右侧两格 tab:0 = 用量(今日 TOKENS 三列 + 模型 TOP3 + 当前对话行),
1 = 套餐(OpenCode Go 三窗口额度)。tab 0 为默认页,内容与坐标自始未动。
数值显示走 drip 摊放:每段增量按其产生时长 2~4s 一跳分步释放(封顶 10 分钟)。
底部"当前对话"行例外:不走池、无飘字,每轮轮询整值直显(用户约定)。
"""

import datetime
import math
import time

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import QWidget

import config as cfg
import drip
import quota as Q
import stats as S
import theme as T

# —— 布局常量(px,296x218) ——
BIG_RECT = (16, 34, 116, 36)          # 今日大数字
CAP_RECT = (16, 72, 130, 14)          # "今日 TOKENS"
BIG_INC_RIGHT = 138                   # 大飘字右端(竖分隔线左侧)
BIG_INC_TOP = 32
DIVIDER_V_X = 142                     # 主区竖分隔线
DIVIDER_V_Y = (38, 92)
MI_ROW_CY = (39, 60, 81)              # 三列行中心
MI_LABEL_X = 148                      # 三列标签 x(贴近分隔线,给数字让位)
MI_VALUE_X, MI_VALUE_W = 176, 102     # 数值左对齐区(亿级11位数+缓存占比不溢出)
MI_INC_RIGHT = 282                    # 右栏飘字右端
DIVIDER_H_Y = 96                      # 模型区横分隔线
MODEL_ROW_CY = (117, 142, 167)        # 模型行中心
M_DOT_X, M_DOT_SIZE = 16, 8
M_NAME_X, M_NAME_W = 32, 92
M_TRACK_X, M_TRACK_W, M_TRACK_H = 132, 78, 6
M_VAL_RIGHT = 282
TOP_DOT = (16, 17, 8, 8)              # 呼吸灯
TOP_TEXT_X = 38
TOP_RIGHT = 282
DIVIDER_H2_Y = 180                    # 底部"当前对话"行上方的细分隔线
CUR_ROW_CY = 198                      # 当前对话行中心
CUR_X0, CUR_RIGHT = 16, 282           # 当前行可用横向范围
MI_KEYS = ("输入", "输出", "缓存")
TWEEN_KEYS = ("total", "input", "output", "cache", "m0", "m1", "m2")

# —— tab 切换(顶行右侧分段控件;放在日期与"次数"之间的空白带,不改两处既有坐标) ——
TAB_BOX = (156, 12, 64, 18)           # x, y, w, h;两格等宽
TAB_LABELS = ("用量", "套餐")
CLICK_MAX_MOVE = 4                    # 按下→释放位移 ≤ 该值视为点击,否则视为拖动

# —— tab 1:套餐额度布局(复用 tab 0 的行几何,保持同一视觉语言) ——
Q_ROW_CY = (110, 138, 166)            # 三个额度窗口行中心
Q_BAR_X, Q_BAR_W, Q_BAR_H = 132, 60, 6
Q_PCT_RIGHT = 236                     # 百分比右端(留给倒计时)
Q_CD_RIGHT = 282                      # 倒计时右端
Q_NUM_W = 50                          # 百分比数值列宽
Q_CD_W = 44                           # 倒计时列宽(容得下 28d23h)
Q_CAP_RECT = (16, 72, 220, 14)        # tab 1 cap 文案


def is_click(press: QPoint, release: QPoint) -> bool:
    """按下→释放位移不超过 CLICK_MAX_MOVE 视为点击(与拖动区分)。"""
    return (release - press).manhattanLength() <= CLICK_MAX_MOVE



def _font(family: str, px: float, bold: bool = False,
          spacing: float = 0.0, weight: int = -1) -> QFont:
    f = QFont(family)
    f.setPixelSize(int(px + 0.5))
    if weight >= 0:
        f.setWeight(weight)
    else:
        f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def _color(hexstr: str, alpha: float = 1.0) -> QColor:
    c = QColor(hexstr)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


class _Tween:
    """数值补间:easeOutCubic,与设计稿过渡曲线一致。"""

    def __init__(self, value: float = 0.0):
        self._frm = self._to = float(value)
        self._t0 = time.monotonic()
        self._dur = 0.0

    def snap(self, value: float) -> None:
        self._frm = self._to = float(value)
        self._dur = 0.0

    def to(self, value: float, dur: int = T.TWEEN_MS) -> None:
        self._frm = self.value()
        self._to = float(value)
        self._t0 = time.monotonic()
        self._dur = max(1, dur)

    def end(self) -> float:
        return self._to

    def value(self, now: float | None = None) -> float:
        if self._dur <= 0:
            return self._to
        now = now if now is not None else time.monotonic()
        p = min(1.0, (now - self._t0) / (self._dur / 1000))
        return self._frm + (self._to - self._frm) * (1 - (1 - p) ** 3)


class FloatCard(QWidget):
    """324x246 无边框置顶横卡。数据入口:set_data / set_error。"""

    def __init__(self):
        # Qt.Tool:不进任务栏、不进 Alt-Tab,仅托盘交互(用户要求)
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 窗口比卡片大一圈(SHADOW_PAD):四周透明区用于画落地投影
        self.setFixedSize(T.WIN_W, T.WIN_H)

        self.reqs_text = "读取中…"
        self.error_text = ""
        self.tw = {k: _Tween(0.0) for k in TWEEN_KEYS}
        self._shown: dict[str, float] = {}    # 已释放到的显示目标
        self._last_real: dict[str, float] = {}  # 上次轮询真实值(算增量用)
        self._sched = drip.DripScheduler(
            T.SMOOTH_TICK_MIN_MS, T.SMOOTH_TICK_MAX_MS,
            T.SMOOTH_MAX_DURATION_MS, T.SMOOTH_JITTER_MIN, T.SMOOTH_JITTER_MAX)
        self.models: list[tuple[str, int]] = []
        self.cur: dict | None = None   # 当前对话用量(整值直显,不走池)
        self.bar_w = [0.0, 0.0, 0.0]
        self.inc_big = None            # (text, t0)
        self.inc_mi = [None, None, None]
        self._first = True
        self.tab = 0                   # 0 = 用量(默认,既有页) 1 = 套餐
        self.quota_windows: list = []  # quota.Window 列表(空 = 尚无额度数据)
        self.quota_fetched_at = 0.0    # 上次成功取数的 epoch 秒
        self.quota_error = ""          # 非空 = 异常/未配置文案
        self.quota_error_kind = ""     # "config" = 未配置(灰字,非故障)
        self.q_tw = {f"q{i}": _Tween(0.0) for i in range(3)}
        self.q_tw["qbig"] = _Tween(0.0)
        self._q_first = True
        self._drag_offset = None
        self._press_pos = None

        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start(T.FRAME_MS)

    # —— 数据入口 ——
    @staticmethod
    def _now_ms() -> float:
        """单调毫秒时钟;独立成方法便于测试注入假时钟。"""
        return time.monotonic() * 1000.0

    def set_data(self, d: dict) -> None:
        """d:{"count","input","output","cache","total","models":[(名称,总量)]}。

        首帧直接显示真实值;此后每轮把增量交给 drip 池,由帧循环分步释放,
        每段摊放时长=该段产生间隔(封顶 SMOOTH_MAX_DURATION_MS)。
        """
        models = d.get("models", [])
        values = {
            "total": d["total"], "input": d["input"], "output": d["output"],
            "cache": d["cache"],
            "m0": models[0][1] if len(models) > 0 else 0.0,
            "m1": models[1][1] if len(models) > 1 else 0.0,
            "m2": models[2][1] if len(models) > 2 else 0.0,
        }
        if self._first:
            for k, tw in self.tw.items():
                tw.snap(values[k])
            self.bar_w = list(self._bar_targets())
            self._shown = dict(values)
            self._last_real = dict(values)
            self._first = False
        elif values["total"] < self._last_real["total"]:
            # 当日累计回退 = 跨零点(或上游修正):清池并把显示直接对齐新值,
            # 否则负增量被钳零、显示会永远冻结在昨天的量上
            self._sched.reset()
            for k, tw in self.tw.items():
                tw.snap(values[k])
            self.bar_w = list(self._bar_targets())
            self._shown = dict(values)
            self._last_real = dict(values)
        else:
            delta = {k: max(0.0, values[k] - self._last_real[k])
                     for k in values}
            self._last_real = dict(values)
            if any(delta.values()):
                self._sched.add(delta, self._now_ms())
        self.models = models
        # 当前对话数字按用户约定不进 drip 池、不补间:每轮直接整值替换,
        # 切换会话/刷新立即反映真实汇总。
        self.cur = d.get("cur")
        self.reqs_text = f"{d['count']} 次"
        self.error_text = ""

    def set_error(self, msg: str) -> None:
        """数据源异常:保留上次显示值,状态行与呼吸灯提示异常。"""
        self.error_text = msg
        self.reqs_text = "数据源异常"

    # —— 额度数据入口(tab 1:OpenCode Go 套餐) ——
    def set_quota(self, windows: list, fetched_at: float = 0.0) -> None:
        """额度到账:更新三窗口数值并清除异常标记。

        首帧直接落位(不从 0 爬升),此后走 T.TWEEN_MS 补间,与卡片既有动效
        语言一致;额度变化以分钟计,故不进 drip 池、不产生飘字。
        """
        if windows:
            self.quota_windows = list(windows)
            self.quota_fetched_at = float(fetched_at or time.time())
        self.quota_error = ""
        self.quota_error_kind = ""
        for i in range(3):
            tw = self.q_tw[f"q{i}"]
            target = (self.quota_windows[i].percent or 0.0
                      if i < len(self.quota_windows) else 0.0)
            if self._q_first:
                tw.snap(target)
            else:
                tw.to(target)
        hottest = Q.hottest(self.quota_windows)
        big = hottest.percent if hottest else 0.0
        if self._q_first:
            self.q_tw["qbig"].snap(big)
        else:
            self.q_tw["qbig"].to(big)
        self._q_first = False

    def set_quota_error(self, msg: str, kind: str = "io") -> None:
        """额度异常:保留上次数值(若有),只改状态标记。

        kind="config" 表示尚未配置 API Key(灰字提示,不算故障);
        其余(kind="io")按故障处理,状态文字与呼吸灯转警示色。
        """
        self.quota_error = msg
        self.quota_error_kind = kind

    def _bar_targets(self) -> list[float]:
        sh = S.shares(self.models)
        return [max(M_TRACK_W * 0.02, sh[i] * M_TRACK_W)
                if i < len(sh) else 0.0
                for i in range(3)]

    # —— 帧循环 ——
    def _on_frame(self) -> None:
        self._drip()
        targets = self._bar_targets()
        for i in range(3):
            self.bar_w[i] += (targets[i] - self.bar_w[i]) * 0.12
        self.update()

    def _drip(self) -> None:
        """释放池中增量:每跳把 tween 目标推进一小步并触发对应飘字。"""
        now_ms = self._now_ms()
        while self._sched.due(now_ms):
            chunk = self._sched.release(now_ms)
            now = time.monotonic()
            if chunk.get("total", 0.0) >= 1:
                self.inc_big = (f"+{chunk['total']:,.0f}", now)
            for i, key in enumerate(("input", "output", "cache")):
                if chunk.get(key, 0.0) >= 1:
                    self.inc_mi[i] = (f"+{chunk[key]:,.0f}", now)
            for k, val in chunk.items():
                self._shown[k] += val
                self.tw[k].to(self._shown[k])

    # —— 绘制 ——
    def paintEvent(self, ev) -> None:
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        # 平移到卡片坐标系:左上透明边距留给投影
        p.translate(T.SHADOW_PAD, T.SHADOW_PAD)
        self._draw_shadow(p)
        self._draw_card(p)
        self._draw_top(p, now)
        if self.tab == 1:
            self._draw_quota(p, now)
        else:
            self._draw_main(p, now)
            self._draw_models(p, now)
            self._draw_cur(p)

    def _draw_shadow(self, p: QPainter) -> None:
        """落地投影:多层圆角矩形向外扩、alpha 递减,贴近设计稿 5% 柔影。"""
        p.setPen(Qt.NoPen)
        for i in range(6, 0, -1):
            expand = i * 2.2
            alpha = T.A_SHADOW_MAX - (i - 1) * 0.007
            p.setBrush(_color(T.C_SHADOW, alpha))
            p.drawRoundedRect(
                QRectF(-expand, -expand + 1, T.CARD_W + expand * 2,
                       T.CARD_H + expand * 2),
                T.RADIUS + expand, T.RADIUS + expand)

    def _draw_card(self, p: QPainter) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, T.CARD_W - 1, T.CARD_H - 1),
                            T.RADIUS, T.RADIUS)
        p.fillPath(path, _color(T.C_CARD_BG))
        p.setPen(QPen(_color(T.C_CARD_BORDER), T.BORDER_W))
        p.drawPath(path)

    def _top_problem(self) -> bool:
        """顶行警示态来源随 tab 走:tab 0 看用量数据源,tab 1 看额度状态。"""
        if self.tab == 1:
            if self.quota_error and self.quota_error_kind != "config":
                return True
            return bool(self.quota_windows) and Q.is_stale(
                self.quota_fetched_at, time.time(), T.QUOTA_MAX_AGE_S)
        return bool(self.error_text)

    def _draw_tabs(self, p: QPainter) -> None:
        """顶行右侧两格 tab:激活格橙字 + 橙淡填充,未激活灰字。"""
        x, y, w, h = TAB_BOX
        cw = w // 2
        for i, label in enumerate(TAB_LABELS):
            cell = QRect(x + i * cw, y, cw, h)
            active = i == self.tab
            if active:
                p.setPen(Qt.NoPen)
                p.setBrush(_color(T.C_ACCENT, 0.14))
                p.drawRoundedRect(QRectF(cell), 4, 4)
            p.setPen(_color(T.C_ACCENT if active else T.C_TEXT_LABEL))
            p.setFont(_font(T.F_UI, T.FS_TAB,
                            weight=QFont.DemiBold if active else -1))
            p.drawText(cell, Qt.AlignCenter, label)

    def _draw_top(self, p: QPainter, now: float) -> None:
        # 呼吸灯:2.4s 周期,中点最暗(0.4),异常态变红橙
        phase = (now * 1000 % T.BREATH_MS) / T.BREATH_MS
        a = 1 - 0.6 * math.sin(math.pi * phase)
        core = T.C_ERROR if self._top_problem() else T.C_ACCENT
        cx, cy = TOP_DOT[0] + 4, TOP_DOT[1] + 4
        p.setPen(Qt.NoPen)
        for r, fa in ((14, 0.15), (10, 0.30)):
            p.setBrush(_color(core, fa * a))
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.setBrush(_color(core, a))
        p.drawEllipse(QRectF(TOP_DOT[0], TOP_DOT[1],
                             TOP_DOT[2], TOP_DOT[3]))
        # 日期标签(每帧按当前日期生成,跨零点自动换日) + 24h 时钟
        p.setPen(_color(T.C_TEXT_HEAD))
        p.setFont(_font(T.F_UI, T.FS_HEAD, weight=QFont.DemiBold))
        p.drawText(QRect(TOP_TEXT_X, 12, 210, 18),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   f"{S.today_label()}  {time.strftime('%H:%M')}")
        if self.tab == 0:
            # 次数/状态(仅用量页;套餐页的状态由底部状态行承担)
            p.setPen(_color(T.C_TEXT_DIM if not self.error_text
                            else T.C_ERROR))
            p.setFont(_font(T.F_MONO, T.FS_REQ))
            p.drawText(QRect(TOP_RIGHT - 150, 12, 150, 18),
                       Qt.AlignRight | Qt.AlignVCenter, self.reqs_text)
        self._draw_tabs(p)

    def _draw_main(self, p: QPainter, now: float) -> None:
        # 大数字 + cap
        p.setPen(_color(T.C_TEXT_BIG))
        p.setFont(_font(T.F_MONO, T.FS_BIG, True, 1.0))
        p.drawText(QRect(*BIG_RECT), Qt.AlignLeft | Qt.AlignVCenter,
                   S.cny(self.tw["total"].value(now)))
        p.setPen(_color(T.C_TEXT_LABEL))
        p.setFont(_font(T.F_UI, T.FS_CAP, spacing=2.5))
        p.drawText(QRect(*CAP_RECT), Qt.AlignLeft | Qt.AlignVCenter,
                   "今日 TOKENS")
        # 大飘字
        if self.inc_big:
            if not self._draw_rise(p, self.inc_big, now, T.INC_RISE_MS,
                                   QRect(BIG_INC_RIGHT - 96,
                                         BIG_INC_TOP, 96, 20),
                                   T.FS_INC, start_dy=8, end_dy=-14):
                self.inc_big = None
        # 竖分隔线
        p.setPen(QPen(_color(T.C_DIVIDER), 1))
        p.drawLine(DIVIDER_V_X, DIVIDER_V_Y[0],
                   DIVIDER_V_X, DIVIDER_V_Y[1])
        # 三列:标签 | 完整千分位数字(左对齐,小数额跳动可感知) | 右侧飘字;
        # 缓存行占比小字紧跟数字右侧
        for i, key in enumerate(("input", "output", "cache")):
            cy = MI_ROW_CY[i]
            p.setPen(_color(T.C_TEXT_LABEL))
            p.setFont(_font(T.F_UI, T.FS_MI_K))
            p.drawText(QRect(MI_LABEL_X, cy - 9, 22, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, MI_KEYS[i])
            val = self.tw[key].value(now)
            text = S.full(val)
            rect = QRect(MI_VALUE_X, cy - 9, MI_VALUE_W, 18)
            p.setPen(_color(T.C_TEXT_VALUE))
            p.setFont(_font(T.F_MONO, T.FS_MI_V, True))
            num_w = p.fontMetrics().horizontalAdvance(text)
            p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)
            if key == "cache":
                tot = self.tw["total"].value(now)
                if tot > 0:
                    pct = f"{round(val / tot * 100)}%"
                    p.setPen(_color(T.C_TEXT_LABEL))
                    p.setFont(_font(T.F_UI, T.FS_PCT))
                    p.drawText(
                        QRect(rect.x() + num_w + 3, rect.y(),
                              rect.width() - num_w - 3, rect.height()),
                        Qt.AlignLeft | Qt.AlignVCenter, pct)
            if self.inc_mi[i]:
                if not self._draw_rise(p, self.inc_mi[i], now,
                                       T.INC2_RISE_MS,
                                       QRect(MI_INC_RIGHT - 80,
                                             int(cy) - 9, 80, 18),
                                       T.FS_INC2, start_dy=6, end_dy=-10):
                    self.inc_mi[i] = None

    def _draw_models(self, p: QPainter, now: float) -> None:
        p.setPen(QPen(_color(T.C_DIVIDER), 1))
        p.drawLine(18, DIVIDER_H_Y, M_VAL_RIGHT, DIVIDER_H_Y)
        fm_name = _font(T.F_UI, T.FS_MNAME, weight=QFont.DemiBold)
        for i, cy in enumerate(MODEL_ROW_CY):
            name, _total = (self.models[i] if i < len(self.models)
                            else ("", 0))
            color = T.MODEL_COLORS[i]
            # 色点
            p.setPen(Qt.NoPen)
            p.setBrush(_color(color))
            p.drawRoundedRect(QRect(M_DOT_X, int(cy) - 4,
                                    M_DOT_SIZE, M_DOT_SIZE), 2, 2)
            # 名(超长省略)
            p.setPen(_color(T.C_TEXT_VALUE))
            p.setFont(fm_name)
            elided = p.fontMetrics().elidedText(
                name, Qt.ElideRight, M_NAME_W)
            p.drawText(QRect(M_NAME_X, int(cy) - 9, M_NAME_W, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, elided)
            # 占比条
            p.setPen(Qt.NoPen)
            p.setBrush(_color(T.C_DIVIDER))
            p.drawRoundedRect(QRect(M_TRACK_X, int(cy) - 3,
                                    M_TRACK_W, M_TRACK_H), 3, 3)
            w = max(3, min(M_TRACK_W, self.bar_w[i])) if name else 0
            if w > 0:
                p.setBrush(_color(color))
                p.drawRoundedRect(QRect(M_TRACK_X, int(cy) - 3,
                                        int(w), M_TRACK_H), 3, 3)
            # 数值
            p.setPen(_color(T.C_TEXT_MODEL_VAL))
            p.setFont(_font(T.F_MONO, T.FS_MVAL, True))
            val = self.tw[f"m{i}"].value(now)
            p.drawText(QRect(M_VAL_RIGHT - 60, int(cy) - 9, 60, 18),
                       Qt.AlignRight | Qt.AlignVCenter,
                       S.cny(val) if name else "")

    # —— tab 1:套餐额度(OpenCode Go 三窗口) ——
    def _quota_status(self, stale: bool) -> tuple[str, str]:
        """底部状态行内容:(文案, 颜色);未配置是灰字,故障是警示色。"""
        when = time.strftime("%H:%M", time.localtime(self.quota_fetched_at))
        if self.quota_error:
            color = (T.C_TEXT_LABEL if self.quota_error_kind == "config"
                     else T.C_ERROR)
            if self.quota_windows:
                return f"{self.quota_error} · 显示 {when} 数据", color
            return self.quota_error, color
        if not self.quota_windows:
            return "等待额度数据…", T.C_TEXT_LABEL
        if stale:
            return f"数据陈旧 · 最后更新 {when}", T.C_ERROR
        return f"套餐额度 · 更新于 {when}", T.C_TEXT_LABEL

    def _draw_quota(self, p: QPainter, now: float) -> None:
        """三窗口已用百分比 + 进度条 + 重置倒计时,底部一行状态。

        大数字取"已用最高"的窗口(最值得关注的那个),达 QUOTA_WARN_PCT 转
        警示色;行几何与 tab 0 的模型行对齐,保持同一视觉语言。
        """
        windows = self.quota_windows
        stale = Q.is_stale(self.quota_fetched_at, time.time(),
                           T.QUOTA_MAX_AGE_S)
        hottest = Q.hottest(windows)
        big = self.q_tw["qbig"].value(now)
        warn = hottest is not None and big >= T.QUOTA_WARN_PCT
        p.setPen(_color(T.C_ERROR if warn else T.C_TEXT_BIG))
        p.setFont(_font(T.F_MONO, T.FS_BIG, True, 1.0))
        p.drawText(QRect(*BIG_RECT), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{round(big)}%" if hottest else "--")
        p.setPen(_color(T.C_TEXT_LABEL))
        p.setFont(_font(T.F_UI, T.FS_CAP, spacing=2.5))
        cap = (f"{hottest.label}额度已用" if hottest
               else (self.quota_error or "套餐额度"))
        p.drawText(QRect(*Q_CAP_RECT), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(cap, Qt.ElideRight,
                                              Q_CAP_RECT[2]))
        # 横分隔线(与 tab 0 模型区同位)
        p.setPen(QPen(_color(T.C_DIVIDER), 1))
        p.drawLine(18, DIVIDER_H_Y, M_VAL_RIGHT, DIVIDER_H_Y)
        fm_name = _font(T.F_UI, T.FS_MNAME, weight=QFont.DemiBold)
        for i, cy in enumerate(Q_ROW_CY):
            win = windows[i] if i < len(windows) else None
            label = win.label if win else Q.WINDOW_KEYS[i][1]
            color = T.MODEL_COLORS[i]
            # 色点(窗口标识,与模型行同形)
            p.setPen(Qt.NoPen)
            p.setBrush(_color(color))
            p.drawRoundedRect(QRect(M_DOT_X, int(cy) - 4,
                                    M_DOT_SIZE, M_DOT_SIZE), 2, 2)
            # 窗口名
            p.setPen(_color(T.C_TEXT_VALUE))
            p.setFont(fm_name)
            p.drawText(QRect(M_NAME_X, int(cy) - 9, M_NAME_W, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, label)
            # 进度条(底 + 已用填充)
            p.setPen(Qt.NoPen)
            p.setBrush(_color(T.C_DIVIDER))
            p.drawRoundedRect(QRect(Q_BAR_X, int(cy) - 3,
                                    Q_BAR_W, Q_BAR_H), 3, 3)
            val = self.q_tw[f"q{i}"].value(now)
            if win is not None and win.percent is not None:
                fill = max(3.0, min(float(Q_BAR_W), Q_BAR_W * val / 100.0))
                p.setBrush(_color(T.C_ERROR if val >= T.QUOTA_WARN_PCT
                                  else color))
                p.drawRoundedRect(QRect(Q_BAR_X, int(cy) - 3,
                                        int(fill), Q_BAR_H), 3, 3)
            # 已用百分比
            p.setPen(_color(T.C_TEXT_MODEL_VAL))
            p.setFont(_font(T.F_MONO, T.FS_Q_PCT, True))
            p.drawText(QRect(Q_PCT_RIGHT - Q_NUM_W, int(cy) - 9,
                             Q_NUM_W, 18),
                       Qt.AlignRight | Qt.AlignVCenter,
                       f"{round(val)}%" if (win and win.percent is not None)
                       else "--")
            # 重置倒计时
            p.setPen(_color(T.C_TEXT_LABEL))
            p.setFont(_font(T.F_MONO, T.FS_Q_CD))
            p.drawText(QRect(Q_CD_RIGHT - Q_CD_W, int(cy) - 9,
                             Q_CD_W, 18),
                       Qt.AlignRight | Qt.AlignVCenter,
                       Q.countdown(win.resets_at) if win else "")
        # 底部状态行
        text, color = self._quota_status(stale)
        p.setPen(QPen(_color(T.C_DIVIDER), 1))
        p.drawLine(18, DIVIDER_H2_Y, CUR_RIGHT, DIVIDER_H2_Y)
        font = _font(T.F_UI, T.FS_CUR)
        p.setPen(_color(color))
        p.setFont(font)
        p.drawText(QRect(CUR_X0, CUR_ROW_CY - 9, CUR_RIGHT - CUR_X0, 18),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(font).elidedText(text, Qt.ElideRight,
                                                 CUR_RIGHT - CUR_X0))

    def _draw_cur(self, p: QPainter) -> None:
        """底部当前对话行:左标题(截断),右消耗量 + 缓存占比。

        用户约定不显示冒号与"总"字标签;标题吃行首剩余宽度(省略号
        截断),数字不走 drip 池(set_data 已整值直显),这里只做静态排版。
        """
        if self.cur is None:
            return
        c = self.cur
        val = lambda k: float(c.get(k, 0) or 0)
        total = val("total")
        pct = round(val("cache") / total * 100) if total > 0 else 0
        nums = _font(T.F_MONO, T.FS_CUR, True)
        lab = _font(T.F_UI, T.FS_CUR)

        def adv(font: QFont, text: str) -> float:
            return QFontMetrics(font).horizontalAdvance(text)

        # 先量数字段总宽,标题吃剩余
        num_text = S.cny(total)
        suffix_w = adv(nums, num_text) + 4 + adv(lab, f"（{pct}%）")
        title = str(c.get("title") or "").strip() or "—"
        title_w = max(10.0, CUR_RIGHT - CUR_X0 - suffix_w)
        title_font = _font(T.F_UI, T.FS_CUR, weight=QFont.DemiBold)
        fm_t = QFontMetrics(title_font)
        elided = fm_t.elidedText(title, Qt.ElideRight, int(title_w))

        x = float(CUR_X0)
        p.setPen(QPen(_color(T.C_DIVIDER), 1))
        p.drawLine(18, DIVIDER_H2_Y, CUR_RIGHT, DIVIDER_H2_Y)
        p.setPen(_color(T.C_TEXT_VALUE))
        p.setFont(title_font)
        p.drawText(QRect(int(x), CUR_ROW_CY - 9, int(title_w), 18),
                   Qt.AlignLeft | Qt.AlignVCenter, elided)
        x += title_w
        p.setPen(_color(T.C_TEXT_VALUE))
        p.setFont(nums)
        p.drawText(QRect(int(x), CUR_ROW_CY - 9,
                         int(adv(nums, num_text)) + 2, 18),
                   Qt.AlignLeft | Qt.AlignVCenter, num_text)
        x += adv(nums, num_text) + 4
        p.setPen(_color(T.C_TEXT_LABEL))
        p.setFont(lab)
        p.drawText(QRect(int(x), CUR_ROW_CY - 9,
                         int(adv(lab, f"（{pct}%）")) + 2, 18),
                   Qt.AlignLeft | Qt.AlignVCenter, f"（{pct}%）")

    @staticmethod
    def _draw_rise(p: QPainter, inc: tuple, now: float, dur_ms: int,
                   rect: QRect, fs: float, start_dy: float,
                   end_dy: float) -> bool:
        """飘字:0% 淡入下缘 → 20% 全亮 → 100% 上浮淡出。返回 False 表示已结束。"""
        text, t0 = inc
        age = (now - t0) * 1000
        if age > dur_ms:
            return False
        ph = age / dur_ms
        if ph < 0.2:
            alpha = ph / 0.2
            dy = (1 - ph / 0.2) * start_dy
        else:
            alpha = 1 - (ph - 0.2) / 0.8
            dy = end_dy * (ph - 0.2) / 0.8
        p.setPen(_color(T.C_ACCENT, alpha))
        p.setFont(_font(T.F_MONO, fs, True))
        p.drawText(QRect(rect.x(), int(rect.y() + dy), rect.width(),
                         rect.height()), Qt.AlignRight | Qt.AlignVCenter, text)
        return True

    # —— 拖动 / 点击 ——
    @staticmethod
    def tab_at(pos: QPoint) -> int | None:
        """卡片坐标判断落在哪一格 tab;不在控件内返回 None。"""
        x, y, w, h = TAB_BOX
        if x <= pos.x() <= x + w and y <= pos.y() <= y + h:
            return 0 if pos.x() < x + w / 2 else 1
        return None

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            pos = ev.globalPosition().toPoint()
            self._press_pos = pos
            self._drag_offset = pos - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:
        if self._drag_offset is not None and (ev.buttons() & Qt.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag_offset)
            ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        """位移小视为点击(tab 切换或忽略),位移大才是拖动并保存位置。"""
        if self._drag_offset is not None:
            release = ev.globalPosition().toPoint()
            press, self._drag_offset = self._press_pos, None
            self._press_pos = None
            if press is not None and is_click(press, release):
                local = ev.position().toPoint()
                hit = self.tab_at(QPoint(local.x() - T.SHADOW_PAD,
                                         local.y() - T.SHADOW_PAD))
                if hit is not None:
                    self.tab = hit
                    self.update()
            else:
                cfg.save(pos_x=self.x(), pos_y=self.y())
            ev.accept()

    def save_pos(self) -> None:
        cfg.save(pos_x=self.x(), pos_y=self.y())
