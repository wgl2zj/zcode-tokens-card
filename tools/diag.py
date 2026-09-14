"""窗口显示诊断(一次性):启动后 dump widget 可见性/几何/平台信息。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import main as app_mod


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    a = app_mod.App(app)

    def dump() -> None:
        c = a.card
        wh = c.windowHandle()
        print("isVisible:", c.isVisible())
        print("geometry:", c.geometry())
        print("frameGeometry:", c.frameGeometry())
        print("size:", c.size(), "fixed:", c.minimumSize(), c.maximumSize())
        print("windowHandle:", bool(wh),
              "visible:", wh.isVisible() if wh else None,
              "geo:", wh.geometry() if wh else None)
        print("dpr:", wh.devicePixelRatio() if wh else None)
        print("platform:", app.platformName())
        print("tray visible:", a.tray.isVisible())
        app.quit()

    QTimer.singleShot(3000, dump)
    app.exec()


if __name__ == "__main__":
    main()
