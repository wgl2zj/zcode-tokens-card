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
        print("saved shot_tab_usage.png  轮次 =", a.card.reqs_text,
              " 当前速率 =", a.card.rate, " 各模型 =", a.card.model_rates)

    def snap_usage_error() -> None:
        # 用量页数据源异常态:顶行右端应显示固定短句「数据源异常」而非异常类名
        # (类名可长到 145px,会压到 tab);轮次与其余数值保留最后一次成功值。
        # 不打断轮询:set_error 后立即 grab,下一次 _poll 会自行恢复。
        a.card.set_error("OperationalError")
        a.card.grab().save(str(OUT / "shot_tab_usage_error.png"))
        print("saved shot_tab_usage_error.png  顶行右端 =",
              a.card.error_text or "（无）")

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
    QTimer.singleShot(4500, snap_usage_error)
    QTimer.singleShot(7500, snap_quota)
    QTimer.singleShot(8000, snap_quota_error)
    app.exec()


if __name__ == "__main__":
    main()
