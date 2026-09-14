"""本地配置持久化:窗口几何等运行状态。"""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "state.json"


def load() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save(**kv) -> None:
    """增量更新并写回;写失败静默(配置非关键路径)。"""
    data = load()
    data.update(kv)
    try:
        CONFIG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    except OSError:
        pass
