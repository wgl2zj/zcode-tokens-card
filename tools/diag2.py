"""决定性诊断(一次性):真窗口 show 后截取整个屏幕,看窗口在不在画面里。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

import main as app_mod


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    a = app_mod.App(app)

    def snap() -> None:
        screen = QGuiApplication.primaryScreen()
        pm = screen.grabWindow(0)          # 全屏(逻辑坐标)
        pm.save("fullscreen.png")
        print("fullscreen saved:", pm.width(), "x", pm.height())
        print("card visible:", a.card.isVisible(),
              "geo:", a.card.geometry())
        app.quit()

    QTimer.singleShot(4500, snap)
    app.exec()


if __name__ == "__main__":
    main()
