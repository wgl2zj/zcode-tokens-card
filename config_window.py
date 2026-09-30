"""套餐 API Key 配置窗口:托盘图标右键「配置…」打开,独立窗口不占用卡片空间。

三档互斥来源(见 build_rows):自动发现(默认,= 现状 opencode-go-chat)、ZCode
供应商配置里发现的 key、手动输入。保存写本机 state.json 的 quota_api_key 并
回读校验——写不进去时窗口如实报错且不关闭,不谎报"已保存"。对 ~/.zcode 只读。
窗口为纸感皮肤的无边框自绘窗口(与卡片同一视觉语言:同投影、同圆角、同色板);
唯一的真控件是手动输入用的 QLineEdit(要输入法与粘贴)。色值全部取自 theme。
"""

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import QLineEdit, QWidget

import config as cfg
import quota as Q
import theme as T

# —— 布局常量(px,内容坐标系;窗口四周另加 SHADOW_PAD 画投影) ——
W = T.KEYWIN_W
PAD = 18                          # 内容左右边距
TITLE_CY = 26                     # 标题行中心
CLOSE_RECT = (W - 34, 16, 20, 20)  # 「×」命中区
INFO1_CY, INFO2_CY = 56, 74       # 「当前使用」「上次取数」两行中心
DIVIDER_Y = 92                    # 细分隔线
SECT_CY = 108                     # 「选择来源」栏目标签
ROWS_TOP = 120                    # 选项区首行上缘
ROW_H = T.KEYWIN_ROW_H
DOT_X = PAD + 7                   # 单选圈中心 x
LABEL_X = DOT_X + 15              # 选项主文字左端
# 主文字列宽 96px:实测最宽主文字「自动发现（默认）」88px(粗体)、脱敏 key 定长
# 74px,列宽给到 96 才不会压到右侧 providerId 附注(附注列仍有 246px 容得下 UUID)
FIELD_X = LABEL_X + 96            # 附注/手动输入框左端
FIELD_H = 20                      # 输入框高(行高内居中)
HINT_GAP = 12                     # 选项区到第一行说明的间距
BTN_GAP = 10                      # 两按钮间距
STATUS_H = 18                     # 状态/报错行预留高
CLICK_MAX_MOVE = 4                # 按下→释放位移 ≤ 该值视为点击,否则视为拖动

HINTS = ("保存后立即生效（停掉旧轮询、立刻重取一次，不等下一个 60 秒周期）",
         "仅存本机 state.json；非 OpenCode Go 的 key 会取数失败并在套餐页如实显示")

KIND_AUTO, KIND_KEY, KIND_MANUAL = "auto", "key", "manual"


def _font(family: str, px: float, bold: bool = False,
          spacing: float = 0.0, weight: int = -1) -> QFont:
    """与卡片同一套字号约定(px 取整 +0.5 四舍五入),保证两窗口字体一致。"""
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


# —— 选项模型(纯逻辑,便于单测锁"选了哪一项 = 存哪个值") ——

def build_rows(candidates: list) -> list[dict]:
    """选项行:自动发现(默认) → ZCode 配置发现的 key → 手动输入(恒为末行)。"""
    rows = [{"kind": KIND_AUTO}]
    rows += [{"kind": KIND_KEY, "cand": c} for c in candidates]
    rows.append({"kind": KIND_MANUAL})
    return rows


def row_index_for(rows: list[dict], configured: str) -> int:
    """按已保存的配置值回填选中行:空 = 自动发现;命中某个 key = 该行;否则 = 手动输入。"""
    text = (configured or "").strip()
    if not text:
        return 0
    for i, row in enumerate(rows):
        if row["kind"] == KIND_KEY and row["cand"].api_key == text:
            return i
    return len(rows) - 1


def selected_value(rows: list[dict], index: int, manual_text: str) -> str:
    """选中行对应的配置值:自动发现 = 空串(回落到自动发现);key 行 = 该 key;手动 = 输入。"""
    if not 0 <= index < len(rows):
        return ""
    row = rows[index]
    if row["kind"] == KIND_AUTO:
        return ""
    if row["kind"] == KIND_KEY:
        return row["cand"].api_key
    return (manual_text or "").strip()


def layout(row_count: int) -> dict:
    """按选项行数算出各区块 y 与窗口高(滚轮只作用于选项区,其余区块不动)。"""
    visible = max(1, min(row_count, T.KEYWIN_ROWS_MAX))
    rows_h = visible * ROW_H
    hint1 = ROWS_TOP + rows_h + HINT_GAP
    hint2 = hint1 + 14
    status = hint2 + 16
    btn_y = status + STATUS_H
    return {"visible": visible, "rows_h": rows_h, "hint1_y": hint1,
            "hint2_y": hint2, "status_y": status, "btn_y": btn_y,
            "height": btn_y + T.KEYWIN_BTN_H + PAD}


def save_configured(value: str) -> bool:
    """写入本机 state.json 的 quota_api_key 并回读校验;失败返回 False(调用方如实提示)。

    config.save 自身对写失败静默(配置非关键路径),这里补一次回读,
    使"保存了却没生效"不会被界面谎报成成功。
    """
    cfg.save(quota_api_key=value)
    return (cfg.load().get("quota_api_key") or "") == value


class KeyConfigWindow(QWidget):
    """套餐 API Key 配置窗口;保存成功后发 key_saved(新值,空串 = 自动发现)。"""

    key_saved = Signal(str)

    def __init__(self, candidates: list | None = None,
                 configured: str = "", resolved=None, fetch_note: str = "",
                 fetch_problem: bool = False):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.rows = build_rows(list(candidates
                                    if candidates is not None
                                    else Q.discover_keys()))
        self.resolved = resolved or Q.ResolvedKey()
        self.fetch_note = fetch_note
        self.fetch_problem = fetch_problem
        self.status = ""              # 窗口内报错/提示(空 = 不画)
        self.status_error = False
        self.scroll = 0
        self.sel = row_index_for(self.rows, configured)
        self.manual_text = ""
        text = (configured or "").strip()
        if self.sel == len(self.rows) - 1:
            self.manual_text = text      # 选中的是"手动输入"行 → 回填明文便于核对

        self.line = QLineEdit(self)
        self.line.setStyleSheet(
            f"QLineEdit {{ background: {T.C_CARD_BG};"
            f" border: 1px solid {T.C_CARD_BORDER}; border-radius: 4px;"
            f" padding: 0 6px; color: {T.C_TEXT_VALUE};"
            f" selection-background-color: {T.C_ACCENT};"
            f" font-family: '{T.F_MONO}';"
            f" font-size: {int(T.FS_SET_HINT)}px; }}"
            f"QLineEdit:focus {{ border: 1px solid {T.C_ACCENT}; }}"
            f"QLineEdit:disabled {{ background: {T.C_DIVIDER};"
            f" border: 1px solid {T.C_CARD_BORDER};"
            f" color: {T.C_TEXT_LABEL}; }}")
        self.line.setPlaceholderText("粘贴 API Key")
        self.line.returnPressed.connect(self._save)
        self.line.textEdited.connect(self._on_manual_edited)

        self._press = None
        self._drag = None
        self._geo = layout(len(self.rows))
        self._sync_geometry()
        self._sync_selection()

    # —— 打开/刷新 ——
    def refresh(self, candidates: list | None = None, configured: str = "",
                resolved=None, fetch_note: str = "", fetch_problem: bool = False):
        """按当前配置重新回填(窗口复用:重复打开只更新内容,不新开一个)。"""
        if candidates is not None:
            self.rows = build_rows(list(candidates))
        self.resolved = resolved or Q.ResolvedKey()
        self.fetch_note = fetch_note
        self.fetch_problem = fetch_problem
        self.status, self.status_error, self.scroll = "", False, 0
        self.sel = row_index_for(self.rows, configured)
        text = (configured or "").strip()
        self.manual_text = text if self.sel == len(self.rows) - 1 else ""
        self._geo = layout(len(self.rows))
        self._sync_geometry()
        self._sync_selection()

    def _sync_geometry(self) -> None:
        self.setFixedSize(W + T.SHADOW_PAD * 2,
                          self._geo["height"] + T.SHADOW_PAD * 2)
        top, h = ROWS_TOP, self._geo["rows_h"]
        manual = self._row_y(len(self.rows) - 1)
        if manual is None or not top <= manual <= top + h:
            self.line.hide()               # 手动输入行被滚出视野时不显示输入框
            return
        self.line.setGeometry(FIELD_X + T.SHADOW_PAD, manual + T.SHADOW_PAD,
                              W - PAD - FIELD_X, FIELD_H)
        self.line.setVisible(True)

    def _sync_selection(self) -> None:
        manual = self.rows[self.sel]["kind"] == KIND_MANUAL if self.rows else False
        self.line.setEnabled(manual)
        if manual:
            if self.line.text() != self.manual_text:
                self.line.setText(self.manual_text)
            self.line.setFocus()
        else:
            self.line.setText("")
        self.update()

    def _on_manual_edited(self, text: str) -> None:
        self.manual_text = text
        if self.status:
            self.status, self.status_error = "", False
            self.update()

    def _row_y(self, index: int) -> int | None:
        """该行在内容坐标系里的顶边 y;被滚出可见区返回 None。"""
        offset = index - self.scroll
        if not 0 <= offset < self._geo["visible"]:
            return None
        return ROWS_TOP + offset * ROW_H

    @staticmethod
    def row_at(pos: QPoint, row_count: int, scroll: int) -> int | None:
        """内容坐标 → 选项行下标;不在选项区内返回 None(纯几何,便于单测)。"""
        if not ROWS_TOP <= pos.y() < ROWS_TOP + T.KEYWIN_ROWS_MAX * ROW_H:
            return None
        index = scroll + (pos.y() - ROWS_TOP) // ROW_H
        return index if 0 <= index < row_count else None

    def _scroll_max(self) -> int:
        return max(0, len(self.rows) - self._geo["visible"])

    @staticmethod
    def _btn_rects(height: int) -> dict:
        """底部两按钮矩形:取消贴右边距,保存在其左。"""
        y = height - PAD - T.KEYWIN_BTN_H
        right = W - PAD
        return {"cancel": QRect(right - T.KEYWIN_BTN_W, y,
                                T.KEYWIN_BTN_W, T.KEYWIN_BTN_H),
                "save": QRect(right - T.KEYWIN_BTN_W * 2 - BTN_GAP, y,
                              T.KEYWIN_BTN_W, T.KEYWIN_BTN_H)}

    @staticmethod
    def btn_at(pos: QPoint, height: int) -> str | None:
        for name, rect in KeyConfigWindow._btn_rects(height).items():
            if rect.contains(pos):
                return name
        return None

    # —— 交互 ——
    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            pos = ev.globalPosition().toPoint()
            self._press = pos
            self._drag = pos - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:
        if self._drag is not None and (ev.buttons() & Qt.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag)
            ev.accept()

    def mouseReleaseEvent(self, ev) -> None:
        """位移小视为点击(选行/按钮/关闭),位移大才是拖动窗口。"""
        if self._drag is None:
            return
        release = ev.globalPosition().toPoint()
        press, self._press, self._drag = self._press, None, None
        if press is None or (release - press).manhattanLength() > CLICK_MAX_MOVE:
            ev.accept()
            return
        local = ev.position().toPoint()
        pos = QPoint(local.x() - T.SHADOW_PAD, local.y() - T.SHADOW_PAD)
        if QRect(*CLOSE_RECT).contains(pos):
            self.hide()
            return
        btn = self.btn_at(pos, self._geo["height"])
        if btn == "cancel":
            self.hide()
            return
        if btn == "save":
            self._save()
            return
        index = self.row_at(pos, len(self.rows), self.scroll)
        if index is not None:
            self.sel = index
            self.status, self.status_error = "", False
            self._sync_selection()

    def wheelEvent(self, ev) -> None:
        """滚轮翻选项区(候选多于 KEYWIN_ROWS_MAX 时才有效)。"""
        step = -1 if ev.angleDelta().y() > 0 else 1
        new = max(0, min(self._scroll_max(), self.scroll + step))
        if new != self.scroll:
            self.scroll = new
            self._sync_geometry()
            self.update()

    def keyPressEvent(self, ev) -> None:
        if ev.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(ev)

    def _save(self) -> None:
        """保存:手动输入不能为空;写盘失败如实报错且不关闭。"""
        value = selected_value(self.rows, self.sel, self.manual_text)
        if self.rows[self.sel]["kind"] == KIND_MANUAL and not value:
            self.status, self.status_error = "手动输入不能为空", True
            self.update()
            return
        if not save_configured(value):
            self.status, self.status_error = \
                "写入 state.json 失败：本次运行生效，但重启后会丢失", True
            self.update()
            return
        self.hide()
        self.key_saved.emit(value)

    # —— 绘制 ——
    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.translate(T.SHADOW_PAD, T.SHADOW_PAD)
        self._draw_shadow(p)
        self._draw_card(p)
        self._draw_head(p)
        self._draw_info(p)
        p.setPen(QPen(_color(T.C_DIVIDER), 1))
        p.drawLine(PAD, DIVIDER_Y, W - PAD, DIVIDER_Y)
        self._draw_rows(p)
        self._draw_hints(p)
        self._draw_status(p)
        self._draw_buttons(p)

    def _draw_shadow(self, p: QPainter) -> None:
        """与卡片同一套落地柔影(多层圆角矩形向外扩、alpha 递减)。"""
        h = self._geo["height"]
        p.setPen(Qt.NoPen)
        for i in range(6, 0, -1):
            expand = i * 2.2
            alpha = T.A_SHADOW_MAX - (i - 1) * 0.007
            p.setBrush(_color(T.C_SHADOW, alpha))
            p.drawRoundedRect(
                QRectF(-expand, -expand + 1, W + expand * 2, h + expand * 2),
                T.RADIUS + expand, T.RADIUS + expand)

    def _draw_card(self, p: QPainter) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, W - 1, self._geo["height"] - 1),
                            T.RADIUS, T.RADIUS)
        p.fillPath(path, _color(T.C_CARD_BG))
        p.setPen(QPen(_color(T.C_CARD_BORDER), T.BORDER_W))
        p.drawPath(path)

    def _draw_head(self, p: QPainter) -> None:
        p.setPen(_color(T.C_TEXT_HEAD))
        p.setFont(_font(T.F_UI, T.FS_SET_TITLE, weight=QFont.DemiBold))
        p.drawText(QRect(PAD, TITLE_CY - 10, W - PAD * 2 - 30, 20),
                   Qt.AlignLeft | Qt.AlignVCenter, "套餐 API Key")
        # 关闭叉(命中区 CLOSE_RECT;绘制居中于该区)
        p.setPen(_color(T.C_TEXT_LABEL))
        f = _font(T.F_MONO, T.FS_SET_TITLE)
        p.setFont(f)
        p.drawText(QRect(*CLOSE_RECT), Qt.AlignCenter, "×")

    def _draw_info(self, p: QPainter) -> None:
        """当前使用 / 上次取数:重开窗口即可确认配置是否真的生效(脱敏显示)。"""
        fm_font = _font(T.F_UI, T.FS_SET_HINT)
        fm = QFontMetrics(fm_font)
        p.setFont(fm_font)
        key = self.resolved.masked or "—"
        p.setPen(_color(T.C_TEXT_LABEL))
        p.drawText(QRect(PAD, INFO1_CY - 8, W - PAD * 2, 16),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(f"当前使用：{key}（{self.resolved.source_label}）",
                                 Qt.ElideRight, W - PAD * 2))
        note = self.fetch_note or "尚未取到数据"
        p.setPen(_color(T.C_ERROR if self.fetch_problem else T.C_TEXT_LABEL))
        p.drawText(QRect(PAD, INFO2_CY - 8, W - PAD * 2, 16),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(f"上次取数：{note}", Qt.ElideRight, W - PAD * 2))

    def _draw_rows(self, p: QPainter) -> None:
        p.setPen(_color(T.C_TEXT_LABEL))
        p.setFont(_font(T.F_UI, T.FS_SET_HINT, spacing=2.5))
        p.drawText(QRect(PAD, SECT_CY - 8, W - PAD * 2, 16),
                   Qt.AlignLeft | Qt.AlignVCenter, "选择来源")
        top, h = ROWS_TOP, self._geo["rows_h"]
        p.setClipRect(0, top, W, h)
        fm_hint = _font(T.F_UI, T.FS_SET_HINT)
        fm_h = QFontMetrics(fm_hint)
        for i, row in enumerate(self.rows):
            cy = self._row_y(i)
            if cy is None:
                continue
            cy += ROW_H // 2
            active = i == self.sel
            # 单选圈:选中 = 橙实心点 + 橙圈,未选中 = 灰圈
            p.setPen(QPen(_color(T.C_ACCENT if active else T.C_TEXT_LABEL),
                          1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(DOT_X - 4.5, cy - 4.5, 9, 9))
            if active:
                p.setPen(Qt.NoPen)
                p.setBrush(_color(T.C_ACCENT))
                p.drawEllipse(QRectF(DOT_X - 2.2, cy - 2.2, 4.4, 4.4))
            # 主文字 + 附注
            if row["kind"] == KIND_AUTO:
                main, sub = "自动发现（默认）", Q.SOURCE_LABELS["zcode"]
            elif row["kind"] == KIND_KEY:
                main, sub = row["cand"].label, row["cand"].provider_id
            else:
                main, sub = "手动输入", ""
            p.setPen(_color(T.C_TEXT_VALUE))
            p.setFont(_font(T.F_UI, T.FS_SET_EACH,
                            weight=QFont.DemiBold if active else -1))
            room_main = FIELD_X - LABEL_X - 8
            p.drawText(QRect(LABEL_X, cy - 9, room_main, 18),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(main, Qt.ElideRight,
                                                         room_main))
            if sub:
                p.setPen(_color(T.C_TEXT_LABEL))
                p.setFont(fm_hint)
                room = W - PAD - FIELD_X
                p.drawText(QRect(FIELD_X, cy - 8, room, 16),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           fm_h.elidedText(sub, Qt.ElideMiddle, room))
        p.setClipping(False)
        # 候选多于可视行数时在栏目标签右侧提示可滚轮翻看
        if self._scroll_max() > 0:
            p.setPen(_color(T.C_TEXT_LABEL))
            p.setFont(fm_hint)
            p.drawText(QRect(W - PAD - 130, SECT_CY - 8, 130, 16),
                       Qt.AlignRight | Qt.AlignVCenter,
                       f"共 {len(self.rows)} 项 · 滚轮翻看")

    def _draw_hints(self, p: QPainter) -> None:
        font = _font(T.F_UI, T.FS_SET_HINT)
        fm = QFontMetrics(font)
        p.setFont(font)
        p.setPen(_color(T.C_TEXT_LABEL))
        for text, y in zip(HINTS, (self._geo["hint1_y"], self._geo["hint2_y"])):
            p.drawText(QRect(PAD, y, W - PAD * 2, 14),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(text, Qt.ElideRight, W - PAD * 2))

    def _draw_status(self, p: QPainter) -> None:
        if not self.status:
            return
        font = _font(T.F_UI, T.FS_SET_HINT)
        fm = QFontMetrics(font)
        p.setFont(font)
        p.setPen(_color(T.C_ERROR if self.status_error else T.C_TEXT_LABEL))
        p.drawText(QRect(PAD, self._geo["status_y"], W - PAD * 2, 16),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.status, Qt.ElideRight, W - PAD * 2))

    def _draw_buttons(self, p: QPainter) -> None:
        rects = self._btn_rects(self._geo["height"])
        font = _font(T.F_UI, T.FS_SET_EACH, weight=QFont.DemiBold)
        # 保存:橙实心主按钮;取消:描边次按钮
        p.setPen(Qt.NoPen)
        p.setBrush(_color(T.C_ACCENT))
        p.drawRoundedRect(QRectF(rects["save"]), 5, 5)
        p.setPen(_color(T.C_CARD_BG))
        p.setFont(font)
        p.drawText(rects["save"], Qt.AlignCenter, "保存")
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_color(T.C_CARD_BORDER), 1))
        p.drawRoundedRect(QRectF(rects["cancel"]).adjusted(0.5, 0.5, -0.5, -0.5),
                          5, 5)
        p.setPen(_color(T.C_TEXT_VALUE))
        p.drawText(rects["cancel"], Qt.AlignCenter, "取消")
