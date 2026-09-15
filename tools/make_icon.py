"""生成 exe 图标(icon.ico):与托盘图标同款(深底圆角+绿色 Z),一次性工具。"""

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def paint(size: int) -> QPixmap:
    """按 32px 托盘图标(main.make_tray_icon)的比例放大绘制。"""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    m = size // 32                     # 边距
    r = size * 7 / 32                  # 圆角半径
    p.setPen(QColor("#262a31"))
    p.setBrush(QColor("#0f1115"))
    p.drawRoundedRect(m, m, size - 2 * m, size - 2 * m, r, r)
    p.setPen(QColor("#3ddc84"))
    f = QFont("Consolas")
    f.setPixelSize(size // 2)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "Z")
    p.end()
    return pm


def main() -> None:
    app = QApplication(sys.argv + ["-platform", "offscreen"])
    out = Path(__file__).resolve().parent.parent / "icon.ico"
    ok = paint(256).save(str(out), "ICO")
    print(("saved " if ok else "FAILED ") + str(out))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
