"""本地配置持久化:窗口几何等运行状态。

路径按运行形态分流:源码模式存仓库内 state.json;打包(冻结)模式下
程序目录不可靠(onefile 每次运行解压到临时目录,写入会丢),改存
%APPDATA%/ZCodeTokensCard/state.json。
"""

import json
import os
import sys
from pathlib import Path

_APP_DIR_NAME = "ZCodeTokensCard"


def config_path() -> Path:
    """当前形态下的状态文件路径;冻结模式确保其父目录存在。"""
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("APPDATA") or Path.home()) / _APP_DIR_NAME
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return base / "state.json"
    return Path(__file__).resolve().parent / "state.json"


def load(path: Path | None = None) -> dict:
    try:
        return json.loads((path or config_path()).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save(path: Path | None = None, **kv) -> None:
    """增量更新并写回;写失败静默(配置非关键路径)。"""
    p = path or config_path()
    data = load(p)
    data.update(kv)
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    except OSError:
        pass
