"""视觉验收脚本:抓取"用量"与"套餐"两个 tab 的渲染结果。

真实启动 App(含额度后台轮询),卡片保持 hide 不打扰桌面,直接 grab 渲染内容。
用法:`python tools/shot_tabs.py` → out/shot_tab_usage.png / _quota.png / _quota_error.png
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # 项目根

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import main as app_mod

OUT = Path(__file__).parent.parent / "out"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    a = app_mod.App(app)
    a.card.hide()             # 验收期间不弹窗

    def snap_usage() -> None:
        a.card.tab = 0
        a.card.grab().save(str(OUT / "shot_tab_usage.png"))
        print("saved shot_tab_usage.png  count =", a.card.reqs_text)

    def snap_quota() -> None:
        a.card.tab = 1
        a.card.grab().save(str(OUT / "shot_tab_quota.png"))
        print("saved shot_tab_quota.png  额度 =",
              [(w.label, w.percent) for w in a.card.quota_windows],
              "err =", repr(a.card.quota_error))

    def snap_quota_error() -> None:
        # 模拟取数失败(保留上次数值)与未配置两种降级外观
        a.card.set_quota_error("连接失败")
        a.card.grab().save(str(OUT / "shot_tab_quota_error.png"))
        print("saved shot_tab_quota_error.png")
        app.quit()

    # 额度首次取数含失效代理旁路(约 4~5s),故套餐页快照放到 7.5s 之后
    QTimer.singleShot(3000, snap_usage)
    QTimer.singleShot(7500, snap_quota)
    QTimer.singleShot(8000, snap_quota_error)
    app.exec()


if __name__ == "__main__":
    main()
