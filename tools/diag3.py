"""单实例诊断(一次性):App 启动后检查 server 监听状态与自我唤醒。"""

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
        print("server listening:", a.server.isListening(),
              "| error:", a.server.errorString())
        print("notify self-result:", app_mod.notify_running_instance())
        print("card visible:", a.card.isVisible())
        app.quit()

    QTimer.singleShot(2500, dump)
    app.exec()


if __name__ == "__main__":
    main()
