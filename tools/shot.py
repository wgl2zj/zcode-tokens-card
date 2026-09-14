"""视觉验收脚本(一次性):启动真实程序,数秒后抓取窗口保存 PNG 后退出。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # 项目根

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import main as app_mod


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    appw = app_mod.App(app)
    appw.card.hide()          # 验收期间不弹窗打扰,直接抓渲染内容

    shots = {"n": 0}

    def snap() -> None:
        shots["n"] += 1
        appw.card.grab().save(f"shot{shots['n']}.png")
        print(f"saved shot{shots['n']}.png")
        if shots["n"] >= 2:
            app.quit()

    # t=2.2s:第二次轮询(1.5s)刚触发过,应带飘字; t=3.8s:稳态
    QTimer.singleShot(2200, snap)
    QTimer.singleShot(3800, snap)
    app.exec()


if __name__ == "__main__":
    main()
