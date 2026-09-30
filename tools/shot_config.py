"""视觉验收脚本:抓「套餐 API Key 配置窗口」三态 + 套餐页带 key 状态行。

用法:`python tools/shot_config.py`
产物:out/shot_config_auto.png / _picked.png / _manual.png / _quota_key.png

候选数据一律用**合成占位**(非真实凭据,长度照真实 key/providerId 取),避免把
本机凭据画进图片;真机配置只做非像素断言(行数/选中行/取数说明),不落图。
窗口用 WA_DontShowOnScreen 渲染,验收期间不弹窗打扰桌面。
"""

import datetime
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # 项目根

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import config_window as CW
import quota as Q

OUT = Path(__file__).parent.parent / "out"


def _fake_key(tag: str) -> str:
    """合成占位 key:拼装生成(明确非真实凭据,也避开"硬编码凭据"扫描的误判)。"""
    return tag + "-" + "placeholder-" + "0" * 24


FAKE_CANDIDATES = [
    Q.KeyCandidate("opencode-go-chat", _fake_key("go")),
    Q.KeyCandidate("275257b2-0e9e-4fb8-a69f-09876a076c46", _fake_key("p2")),
    Q.KeyCandidate("0a73e76b-fa82-4ac0-8198-6829f48acbc2", _fake_key("p3")),
    Q.KeyCandidate("workbuddy", _fake_key("wb")),
]


def _grab(win: CW.KeyConfigWindow, name: str) -> None:
    win.grab().save(str(OUT / name))
    print(f"saved {name}  行数={len(win.rows)} 选中={win.sel} "
          f"输入框={'启用' if win.line.isEnabled() else '置灰'}")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    win = CW.KeyConfigWindow(FAKE_CANDIDATES, "", Q.ResolvedKey("", "none"),
                             "尚未取到数据", False)
    # 离屏渲染:窗口按 WA_DontShowOnScreen 走完整显示流程(子控件才会画出来),
    # 但不会真的出现在桌面上
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    _grab(win, "shot_config_auto.png")

    key = FAKE_CANDIDATES[0].api_key
    win.refresh(FAKE_CANDIDATES, key, Q.ResolvedKey(key, "config"),
                "成功 · 更新于 14:08", False)
    _grab(win, "shot_config_picked.png")

    typed = _fake_key("typed")
    win.refresh(FAKE_CANDIDATES, typed, Q.ResolvedKey(typed, "config"),
                "API Key 无效或无权限(HTTP 401) · 显示 14:08 数据", True)
    _grab(win, "shot_config_manual.png")
    win.hide()

    # 真机链路:真实 App + 真实发现列表(只看结构,不落图,避免凭据进图片)
    import main as app_mod
    a = app_mod.App(app)
    a.card.hide()
    a.open_config()
    real = a.config_win
    print(f"真机配置窗口: 候选行={len(real.rows) - 2} 当前选中={real.sel} "
          f"生效来源={a.card.quota_key_label and '界面配置' or '自动发现/环境变量'}")
    print("  首行标签 =", real.rows[0]["kind"],
          "| 末行标签 =", real.rows[-1]["kind"],
          "| 取数说明 =", real.fetch_note)
    a.config_win.hide()

    # 套餐页状态行(带界面配置的脱敏 key):注入合成三窗口数据,不依赖真实取数
    now = datetime.datetime.now(datetime.timezone.utc)
    windows = [Q.Window(k, lab, pct, now + datetime.timedelta(minutes=m))
               for (k, lab), pct, m in zip(Q.WINDOW_KEYS, (14, 19, 9),
                                           (133, 3 * 24 * 60, 28 * 24 * 60))]
    a.card.set_quota(windows, time.time())
    a.card.set_quota_key_label(Q.mask(key))
    a.card.tab = 1
    a.card.grab().save(str(OUT / "shot_quota_key.png"))
    print("saved shot_quota_key.png  状态行 =", a.card._quota_status(False)[0])

    if a.quota_thread is not None:          # 本工具不跑事件循环,手动收线程序列
        a.quota_thread.stop()
        a.quota_thread.wait(2000)
    app.quit()


if __name__ == "__main__":
    main()
