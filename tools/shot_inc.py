"""飘字专项验证(一次性):连续两次灌入递增数据,抓增量飘字渲染。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import card as card_mod


def main() -> None:
    app = QApplication(sys.argv)
    c = card_mod.FloatCard()
    c.show()

    base = {"count": 12, "input": 539000, "output": 5593,
            "cache": 469000, "total": 1013521,
            "models": [("GLM-5.3-Flash", 963000), ("GLM-5.3", 43000),
                       ("k3", 7000)]}

    def first() -> None:
        c.set_data(base)          # 首帧落位,不飘

    def bump() -> None:
        grown = dict(base, count=13, input=base["input"] + 9000,
                     output=base["output"] + 200, cache=base["cache"] + 8000,
                     total=base["total"] + 17200,
                     models=[("GLM-5.3-Flash", 963000 + 15000),
                             ("GLM-5.3", 43000 + 1500), ("k3", 7000 + 700)])
        c.set_data(grown)         # 触发补间 + 三处飘字

    def snap() -> None:
        c.grab().save("shot_inc.png")
        print("saved shot_inc.png")
        app.quit()

    QTimer.singleShot(400, first)
    QTimer.singleShot(900, bump)   # 400ms 后灌增量,飘字期 900~2300ms
    QTimer.singleShot(1500, snap)  # 飘字中段抓取
    app.exec()


if __name__ == "__main__":
    main()
