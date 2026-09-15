"""当前会话候选解析:扫 ZCode 桌面端 localStorage(Chromium leveldb)。

ZCode 桌面端把"每个工作区最后打开的会话"存在 localStorage,键形如
`zcode-v4-last-session:v1:<工作区路径>`,值为 `sess_<uuid>`;用户切换
对话时该值随之更新,是"当前查看对话"的界面侧事实来源。

实现是启发式扫描而非完整 leveldb 解析:按键前缀与值模式在原始字节里
定位。Chromium 对键/值各自独立选编码(实测 UTF-16 键后可跟 ASCII 值),
所以键和值各按两种形态扫描、自由组合。解析失败(目录不存在/读文件
失败)一律返回空候选,不视为致命错误。

裁决策略(SessionResolver)以数据库"最近活跃会话"为主信号;仅当扫描
发现候选里首次出现一个新会话 ID(= 捕获到一次真实的切换动作)时才
临时覆盖,避免陈旧/缺失的界面记录在主场景下答错。
"""

import os
import re
from pathlib import Path

_KEY = b"zcode-v4-last-session:v1:"
_KEY_U16 = _KEY.decode("ascii").encode("utf-16-le")

_SESS = re.compile(
    rb"sess_[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
# UTF-16LE 里 ASCII 字符变为 <字符>\x00,按字节展开同样的模式
# (注意连字符也带 NUL:8-4-4-4-12 分组间是 -\x00)
_SESS_U16 = re.compile(
    rb"s\x00e\x00s\x00s\x00_\x00(?:[0-9a-f]\x00){8}"
    rb"(?:-\x00(?:[0-9a-f]\x00){4}){3}"
    rb"-\x00(?:[0-9a-f]\x00){12}")
# 键记录与值记录相邻落盘,值不会离键太远;超出视为无关内容
# (Chromium 对键/值各自独立选编码:实测 UTF-16 键后面跟 ASCII 值,
# 所以键的两种形态都要同时配两种值的形态来找)
_LOOKAHEAD = 400


def leveldb_dir() -> Path:
    """ZCode 桌面端 localStorage 目录(%APPDATA%,缺失时按默认盘推)。"""
    base = os.environ.get("APPDATA") or str(
        Path.home() / "AppData" / "Roaming")
    return Path(base) / "ZCode" / "session" / "Local Storage" / "leveldb"


def scan_candidates(directory: str | Path | None = None) -> list[str]:
    """扫描全部 leveldb 文件,返回去重后的会话 ID 候选(顺序无意义)。

    .log 是最新写入(WAL),排在 .ldb(压实产物)之后处理,同键冲突时
    新值覆盖旧值;失败静默返回空表。
    """
    d = Path(directory) if directory else leveldb_dir()
    out: list[str] = []
    try:
        files = sorted(d.glob("*.ldb")) + sorted(d.glob("*.log"))
    except OSError:
        return out
    for f in files:
        try:
            data = f.read_bytes()
        except OSError:
            continue
        for key_pat in (_KEY, _KEY_U16):
            for key in re.finditer(re.escape(key_pat), data):
                window = data[key.end():key.end() + _LOOKAHEAD]
                for pat, width in ((_SESS, 1), (_SESS_U16, 2)):
                    for val in pat.finditer(window):
                        sid = val.group()[::width].decode("ascii")
                        if sid not in out:
                            out.append(sid)
    return out


class SessionResolver:
    """当前会话裁决:库内最近活跃为主,捕获到的"切换动作"可临时覆盖。

    覆盖触发条件(三者同时满足才认):扫描候选里首次出现一个新会话 ID、
    该 ID 不是库内最近活跃会话、且不是首轮(首轮只建档,无"变化"可言)。
    覆盖持续到:库内最近活跃会话在该切换时刻之后又有新活动(用户切了
    回去并使用),或覆盖目标本身就是新的最近活跃会话。
    """

    def __init__(self):
        self._seen: set[str] | None = None   # 已见过的候选;None = 尚未建档
        self._override: str | None = None    # 切换动作覆盖的会话
        self._override_at_ms = 0.0           # 切换时刻(epoch 毫秒)

    def resolve(self, candidates: list[str], latest_sid: str | None,
                latest_active_ms: int, now_ms: float) -> str | None:
        """返回当前应显示的会话 ID;库内无任何会话时返回 None。"""
        if latest_sid is None:
            return None
        if self._seen is None:
            self._seen = set(candidates)
        else:
            fresh = [c for c in candidates if c not in self._seen]
            self._seen.update(candidates)
            for sid in fresh:   # .log 后扫,列表末尾即最新写入,取最后一个
                if sid != latest_sid:
                    self._override = sid
                    self._override_at_ms = float(now_ms)
        if (self._override is not None and self._override != latest_sid
                and latest_active_ms < self._override_at_ms):
            return self._override
        self._override = None
        return latest_sid
