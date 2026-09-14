"""入口:应用装配(单实例唤醒、系统托盘、数据轮询、窗口位置恢复、ZCode 聚焦联动)。"""

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QMenu, QSystemTrayIcon)

import card as card_mod
import config as cfg
import reader
import stats as S
from theme import CARD_H, CARD_W, POLL_MS

SERVER_NAME = "zcode-tokens-float-card"
FOCUS_CHECK_MS = 400

_u32 = ctypes.windll.user32
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


def foreground_process_name() -> str:
    """前台窗口所属进程的 exe 全路径;取不到返回空串。"""
    hwnd = _u32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    h = _k32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        _k32.CloseHandle(h)


def make_tray_icon() -> QIcon:
    """自绘托盘图标(深底圆角 + 绿色 Z),不依赖图片文件。"""
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor("#262a31"))
    p.setBrush(QColor("#0f1115"))
    p.drawRoundedRect(1, 1, 30, 30, 7, 7)
    p.setPen(QColor("#3ddc84"))
    f = QFont("Consolas")
    f.setPixelSize(16)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "Z")
    p.end()
    return QIcon(pm)


def notify_running_instance() -> bool:
    """已有实例在运行时向其发"show"并返回 True;否则 False。"""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show\n")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


class App:
    """装配卡片、托盘、轮询与单实例服务。"""

    def __init__(self, app: QApplication):
        self.app = app
        self.card = card_mod.FloatCard()
        self._restore_pos()
        self.card.show()

        # 托盘
        self.tray = QSystemTrayIcon(make_tray_icon())
        menu = QMenu()
        self.follow = QAction("仅 ZCode 聚焦时显示", menu, checkable=True)
        self.follow.toggled.connect(self._apply_focus)
        self.follow.setChecked(True)
        act_toggle = QAction("显示 / 隐藏", menu)
        act_toggle.triggered.connect(self._toggle_card)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(self.follow)
        menu.addAction(act_toggle)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("ZCode 用量")
        self.tray.show()
        self.app.aboutToQuit.connect(self._cleanup)

        # 聚焦联动:ZCode.exe(或卡片自身)为前台 → 显示,否则隐藏
        self.focus_timer = QTimer(self.app)
        self.focus_timer.timeout.connect(self._apply_focus)
        self.focus_timer.start(FOCUS_CHECK_MS)

        # 单实例服务:收到 "show" 唤醒窗口
        QLocalServer.removeServer(SERVER_NAME)
        self.server = QLocalServer()
        self.server.newConnection.connect(self._on_connection)
        self.server.listen(SERVER_NAME)

        # 数据轮询
        self.conn = None
        self.poll = QTimer(self.app)
        self.poll.timeout.connect(self._poll)
        self._poll()
        self.poll.start(POLL_MS)

    # —— 窗口位置 ——
    def _restore_pos(self) -> None:
        pos = cfg.load()
        x, y = pos.get("pos_x"), pos.get("pos_y")
        if not isinstance(x, int) or not isinstance(y, int) \
                or not self._on_screen(x, y):
            screen = self.card.screen().availableGeometry()
            # 默认落位:主屏右下角(任务栏上方),贴近 ZCode 最大化时的右下空白区
            x = screen.right() - CARD_W - 20
            y = screen.bottom() - CARD_H - 14
        self.card.move(x, y)

    @staticmethod
    def _on_screen(x: int, y: int) -> bool:
        wr = QRect(x, y, CARD_W, CARD_H)
        return any(s.geometry().intersects(wr) for s in QApplication.screens())

    # —— 托盘 / 生命周期 ——
    def _apply_focus(self) -> None:
        """跟随模式:ZCode 或卡片自身为前台 → 显示,否则隐藏;拖动中不打断。"""
        if not self.follow.isChecked():
            if not self.card.isVisible():
                self.card.show()
            return
        if self.card._drag_offset is not None:
            return
        fg = _u32.GetForegroundWindow()
        if fg == int(self.card.winId()):
            visible = True
        else:
            exe = foreground_process_name().lower()
            visible = exe.endswith("zcode.exe")
        if visible and not self.card.isVisible():
            self.card.show()
        elif not visible and self.card.isVisible():
            self.card.hide()

    def _toggle_card(self) -> None:
        if self.card.isVisible():
            self.card.hide()
        else:
            self.card.show()
            self.card.raise_()

    def _on_connection(self) -> None:
        sock = self.server.nextPendingConnection()
        sock.readyRead.connect(
            lambda: (sock.readAll() == b"show\n" and self._show_card()))
        sock.disconnected.connect(sock.deleteLater)

    def _show_card(self) -> None:
        self.card.show()
        self.card.raise_()

    def _cleanup(self) -> None:
        self.card.save_pos()
        self.tray.hide()
        if self.conn is not None:
            self.conn.close()

    def quit(self) -> None:
        self.app.quit()

    # —— 数据轮询 ——
    def _poll(self) -> None:
        try:
            if self.conn is None:
                self.conn = reader.open_ro()
            start = S.today_start_ms()
            d = S.aggregate(reader.fetch_day_rows(self.conn, start))
            d["models"] = reader.fetch_top_models(self.conn, start, 3)
            self.card.set_data(d)
        except Exception as exc:  # 库锁/schema 变化/路径缺失 → 降级显示
            self.conn = None
            self.card.set_error(f"{type(exc).__name__}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("ZCode 用量")
    if notify_running_instance():
        sys.exit(0)
    a = App(app)
    if not a.server.isListening():
        # 兜底:监听失败说明存在并发实例(极端时序),唤醒对方并退出自己,
        # 绝不出现两个完整实例并存。
        if notify_running_instance():
            sys.exit(0)
        sys.exit(1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
