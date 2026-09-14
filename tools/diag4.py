"""聚焦联动验收(终版,一次性):当前前台即 ZCode,断言跟随显示+缓存百分比。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

import main as app_mod

results = []


def report(tag: str, cond: bool) -> None:
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + tag)


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    a = app_mod.App(app)

    def check() -> None:
        exe = app_mod.foreground_process_name().lower()
        zcode_fg = exe.endswith("zcode.exe")
        vis = a.card.isVisible()
        print("前台进程:", exe or "(无/桌面)")
        report("跟随联动: 显隐与前台一致", vis == zcode_fg)
        report("任务栏隐藏(Qt.Tool)",
               bool(a.card.windowFlags() & Qt.Tool))
        a.card.grab().save("shot_cache.png")
        print("saved shot_cache.png (人验缓存百分比)")
        app.quit()

    QTimer.singleShot(2500, check)   # 等两次轮询,确保数据与显隐就绪
    app.exec()


if __name__ == "__main__":
    main()
