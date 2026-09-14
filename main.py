"""入口:应用装配(单实例唤醒、系统托盘、数据轮询、窗口位置恢复)。"""

import sys

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
        act_toggle = QAction("显示 / 隐藏", menu)
        act_toggle.triggered.connect(self._toggle_card)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_toggle)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("ZCode 用量")
        self.tray.show()
        self.app.aboutToQuit.connect(self._cleanup)

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
            x = screen.right() - CARD_W - 40
            y = screen.top() + 60
        self.card.move(x, y)

    @staticmethod
    def _on_screen(x: int, y: int) -> bool:
        wr = QRect(x, y, CARD_W, CARD_H)
        return any(s.geometry().intersects(wr) for s in QApplication.screens())

    # —— 托盘 / 生命周期 ——
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
    App(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
