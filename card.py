"""横卡窗口:QPainter 全量自绘(布局、动画、拖动交互)。

布局坐标按 design/横卡设计稿.html 的 CSS 盒模型换算(逻辑像素)。
"""

import math
import time

from PySide6.QtCore import QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

import config as cfg
import stats as S
import theme as T

# —— 布局常量(px,源自设计稿换算) ——
BIG_RECT = (18, 34, 185, 38)          # 今日大数字
CAP_RECT = (18, 73, 185, 14)          # "今日 TOKENS"
BIG_INC_RIGHT = 203                   # 大飘字右端
BIG_INC_TOP = 32
DIVIDER_V_X = 212                     # 主区竖分隔线
DIVIDER_V_Y = (38, 92)
MI_ROW_CY = (39, 60, 81)              # 三列行中心
MI_LABEL_X = 228                      # 三列标签 x
MI_VALUE_X, MI_VALUE_W = 258, 104     # 数值居中区
MI_INC_RIGHT = 360                    # 右栏飘字右端
DIVIDER_H_Y = 96                      # 模型区横分隔线
MODEL_ROW_CY = (114, 138, 162)        # 模型行中心
M_DOT_X, M_DOT_SIZE = 18, 8
M_NAME_X, M_NAME_W = 34, 118
M_TRACK_X, M_TRACK_W, M_TRACK_H = 160, 120, 6
M_VAL_RIGHT = 362
TOP_DOT = (18, 17, 8, 8)              # 呼吸灯
TOP_TEXT_X = 34
TOP_RIGHT = 362
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
    """380x184 无边框置顶横卡。数据入口:set_data / set_error。"""

    def __init__(self):
        # Qt.Tool:不进任务栏、不进 Alt-Tab,仅托盘交互(用户要求)
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(T.CARD_W, T.CARD_H)

        self.label = S.today_label()
        self.reqs_text = "读取中…"
        self.error_text = ""
        self.tw = {k: _Tween(0.0) for k in TWEEN_KEYS}
        self.models: list[tuple[str, int]] = []
        self.bar_w = [0.0, 0.0, 0.0]
        self.inc_big = None            # (text, t0)
        self.inc_mi = [None, None, None]
        self._first = True
        self._drag_offset = None

        self._frame_timer = QTimer(self)
        self._frame_timer.timeout.connect(self._on_frame)
        self._frame_timer.start(T.FRAME_MS)

    # —— 数据入口 ——
    def set_data(self, d: dict) -> None:
        """d:{"count","input","output","cache","total","models":[(名称,总量)]}。"""
        now = time.monotonic()
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
            self._first = False
        else:
            inc = int(values["total"] - self.tw["total"].end())
            deltas = {k: values[k] - self.tw[k].end() for k in values}
            for k, tw in self.tw.items():
                tw.to(values[k])
            if inc > 0:
                self.inc_big = (f"+{inc:,}", now)
            for i, key in enumerate(("input", "output", "cache")):
                if deltas[key] >= 1:
                    self.inc_mi[i] = (f"+{deltas[key]:,.0f}", now)
        self.models = models
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
        targets = self._bar_targets()
        for i in range(3):
            self.bar_w[i] += (targets[i] - self.bar_w[i]) * 0.12
        self.update()

    # —— 绘制 ——
    def paintEvent(self, ev) -> None:
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        self._draw_card(p)
        self._draw_top(p, now)
        self._draw_main(p, now)
        self._draw_models(p, now)

    def _draw_card(self, p: QPainter) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, T.CARD_W - 1, T.CARD_H - 1),
                            T.RADIUS, T.RADIUS)
        p.fillPath(path, _color(T.C_CARD_BG))
        p.setPen(QPen(_color(T.C_CARD_BORDER), T.BORDER_W))
        p.drawPath(path)

    def _draw_top(self, p: QPainter, now: float) -> None:
        # 呼吸灯:2.4s 周期,中点最暗(0.4),异常态变橙
        phase = (now * 1000 % T.BREATH_MS) / T.BREATH_MS
        a = 1 - 0.6 * math.sin(math.pi * phase)
        core = T.C_MODEL3 if self.error_text else T.C_ACCENT
        cx, cy = TOP_DOT[0] + 4, TOP_DOT[1] + 4
        p.setPen(Qt.NoPen)
        for r, fa in ((14, 0.15), (10, 0.30)):
            p.setBrush(_color(core, fa * a))
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.setBrush(_color(core, a))
        p.drawEllipse(QRectF(TOP_DOT[0], TOP_DOT[1],
                             TOP_DOT[2], TOP_DOT[3]))
        # 日期标签
        p.setPen(_color(T.C_TEXT_HEAD))
        p.setFont(_font(T.F_UI, T.FS_HEAD, weight=QFont.DemiBold))
        p.drawText(QRect(TOP_TEXT_X, 12, 260, 18),
                   Qt.AlignLeft | Qt.AlignVCenter, self.label)
        # 次数/状态
        p.setPen(_color(T.C_TEXT_DIM if not self.error_text else T.C_MODEL3))
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
        p.setFont(_font(T.F_UI, T.FS_CAP, spacing=4.0))
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
        # 三列:标签 | 数值居中 | 右侧飘字;缓存行附加当日占比
        for i, key in enumerate(("input", "output", "cache")):
            cy = MI_ROW_CY[i]
            p.setPen(_color(T.C_TEXT_LABEL))
            p.setFont(_font(T.F_UI, T.FS_MI_K))
            p.drawText(QRect(MI_LABEL_X, cy - 9, 30, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, MI_KEYS[i])
            val = self.tw[key].value(now)
            text = S.cny(val)
            if key == "cache":
                tot = self.tw["total"].value(now)
                if tot > 0:
                    text = f"{text} ({round(val / tot * 100)}%)"
            p.setPen(_color(T.C_TEXT_VALUE))
            p.setFont(_font(T.F_MONO, T.FS_MI_V, True))
            p.drawText(QRect(MI_VALUE_X, cy - 9, MI_VALUE_W, 18),
                       Qt.AlignCenter, text)
            if self.inc_mi[i]:
                if not self._draw_rise(p, self.inc_mi[i], now,
                                       T.INC2_RISE_MS,
                                       QRect(MI_INC_RIGHT - 80,
                                             int(cy) - 9, 80, 18),
                                       T.FS_INC2, start_dy=6, end_dy=-10):
                    self.inc_mi[i] = None

    def _draw_models(self, p: QPainter, now: float) -> None:
        p.setPen(QPen(_color(T.C_DIVIDER), 1))
        p.drawLine(18, DIVIDER_H_Y, 362, DIVIDER_H_Y)
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
            p.drawText(QRect(M_VAL_RIGHT - 82, int(cy) - 9, 82, 18),
                       Qt.AlignRight | Qt.AlignVCenter,
                       S.cny(val) if name else "")

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
