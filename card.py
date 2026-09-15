"""横卡窗口:QPainter 全量自绘(布局、动画、拖动交互)。

纸感浅色皮肤(选型稿 01 号):312x218,暖白纸底 + 细灰线 + 橙强调。
数值显示走 drip 摊放:每段增量按其产生时长 2~4s 一跳分步释放(封顶 10 分钟)。
底部"当前对话"行例外:不走池、无飘字,每轮轮询整值直显(用户约定)。
"""

import math
import time

from PySide6.QtCore import QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import QWidget

import config as cfg
import drip
import stats as S
import theme as T

# —— 布局常量(px,312x218) ——
BIG_RECT = (16, 34, 116, 36)          # 今日大数字
CAP_RECT = (16, 72, 130, 14)          # "今日 TOKENS"
BIG_INC_RIGHT = 138                   # 大飘字右端(竖分隔线左侧)
BIG_INC_TOP = 32
DIVIDER_V_X = 142                     # 主区竖分隔线
DIVIDER_V_Y = (38, 92)
MI_ROW_CY = (39, 60, 81)              # 三列行中心
MI_LABEL_X = 148                      # 三列标签 x(贴近分隔线,给数字让位)
MI_VALUE_X, MI_VALUE_W = 179, 115     # 数值左对齐区(与标签留 10px 间隙)
MI_INC_RIGHT = 298                    # 右栏飘字右端
DIVIDER_H_Y = 96                      # 模型区横分隔线
MODEL_ROW_CY = (117, 142, 167)        # 模型行中心
M_DOT_X, M_DOT_SIZE = 16, 8
M_NAME_X, M_NAME_W = 32, 92
M_TRACK_X, M_TRACK_W, M_TRACK_H = 132, 78, 6
M_VAL_RIGHT = 298
TOP_DOT = (16, 17, 8, 8)              # 呼吸灯
TOP_TEXT_X = 38
TOP_RIGHT = 298
DIVIDER_H2_Y = 180                    # 底部"当前对话"行上方的细分隔线
CUR_ROW_CY = 198                      # 当前对话行中心
CUR_X0, CUR_RIGHT = 16, 298           # 当前行可用横向范围
MI_KEYS = ("输入", "输出", "缓存")
TWEEN_KEYS = ("total", "input", "output", "cache", "m0", "m1", "m2")


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
    """340x246 无边框置顶横卡。数据入口:set_data / set_error。"""

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
        self._drag_offset = None

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

    def _draw_top(self, p: QPainter, now: float) -> None:
        # 呼吸灯:2.4s 周期,中点最暗(0.4),异常态变红橙
        phase = (now * 1000 % T.BREATH_MS) / T.BREATH_MS
        a = 1 - 0.6 * math.sin(math.pi * phase)
        core = T.C_ERROR if self.error_text else T.C_ACCENT
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
        # 次数/状态
        p.setPen(_color(T.C_TEXT_DIM if not self.error_text else T.C_ERROR))
        p.setFont(_font(T.F_MONO, T.FS_REQ))
        p.drawText(QRect(TOP_RIGHT - 150, 12, 150, 18),
                   Qt.AlignRight | Qt.AlignVCenter, self.reqs_text)

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

    def _draw_cur(self, p: QPainter) -> None:
        """底部当前对话行:标题(截断)：总N（缓存P%）。

        用户约定只显示总计与缓存占比(字号 FS_CUR);标题吃行首剩余
        宽度(省略号截断),数字段靠右;数字不走 drip 池(set_data 已
        整值直显),这里只做静态排版。
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
        suffix_w = (adv(lab, "总") + adv(nums, num_text)
                    + 4 + adv(lab, f"（{pct}%）"))
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
        p.setPen(_color(T.C_TEXT_LABEL))
        p.setFont(lab)
        for text, font, color in (("：", lab, T.C_TEXT_LABEL),
                                  ("总", lab, T.C_TEXT_LABEL),
                                  (num_text, nums, T.C_TEXT_VALUE),
                                  (f"（{pct}%）", lab, T.C_TEXT_LABEL)):
            p.setPen(_color(color))
            p.setFont(font)
            p.drawText(QRect(int(x), CUR_ROW_CY - 9,
                             int(adv(font, text)) + 2, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, text)
            x += adv(font, text)

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

    # —— 拖动 ——
    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._drag_offset = (ev.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:
        if self._drag_offset is not None and (ev.buttons() & Qt.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag_offset)
            ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            cfg.save(pos_x=self.x(), pos_y=self.y())
            ev.accept()

    def save_pos(self) -> None:
        cfg.save(pos_x=self.x(), pos_y=self.y())
