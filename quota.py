"""OpenCode Go 套餐额度取数:key 发现、HTTP 拉取、响应解析、倒计时格式化。

纯逻辑模块(不含 Qt),便于单测锁口径。对 ZCode 配置目录只读访问,绝不写入;
网络失败一律抛 QuotaError 或返回错误描述,由调用方降级显示。
key 裁决(见 resolve_key):界面配置 > 环境变量 > ZCode 配置自动发现——界面里
显式选的必须生效,否则"配了没反应";环境变量与自动发现都是无界面时的兜底。
出口策略见 Fetcher:环境变量代理 → Windows 系统代理 → 直连,首个成功者复用
(实测本机 env 代理端口已失效而系统代理可用,故不能只依赖 env)。
"""

import datetime
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROVIDER_ID = "opencode-go-chat"                 # ZCode 里 OpenCode Go(Chat)供应商 id
ENV_KEY = "OPENCODE_GO_API_KEY"                  # 无界面时的 key 兜底口
DEFAULT_URL = "https://opencode.ai/zen/go/v1/usage"
TIMEOUT_S = 10.0
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
# 三窗口顺序即显示顺序:5 小时 / 本周 / 本月(接口键名 → 中文标签)
WINDOW_KEYS = (("rolling", "5 小时"), ("weekly", "本周"), ("monthly", "本月"))
WINDOW_LABELS = dict(WINDOW_KEYS)


class QuotaError(Exception):
    """取数失败(网络/HTTP/结构不符);调用方据此进入降级显示。"""


@dataclass
class Window:
    """单个额度窗口:percent 为已用百分比(0~100),None 表示接口未给。"""

    key: str
    label: str
    percent: float | None
    resets_at: datetime.datetime | None
    status: str = ""


@dataclass
class Quota:
    """一次成功取数的结果。"""

    windows: list
    fetched_at: datetime.datetime


# —— key 发现与来源裁决 ——

# 脱敏保留的首尾字符数:够认出"是哪一个 key",又不足以还原完整凭据
MASK_HEAD, MASK_TAIL = 6, 4
# 来源标识:config = 界面配置(优先级最高),env = 环境变量,zcode = 只读自动发现
SOURCE_LABELS = {
    "config": "界面配置",
    "env": f"环境变量 {ENV_KEY}",
    "zcode": f"ZCode 配置 · {PROVIDER_ID}",
    "none": "未配置",
}


def config_path() -> Path:
    """ZCode 供应商配置文件路径(可用 ZCODE_PROVIDER_CONFIG 覆盖,便于测试)。"""
    override = os.environ.get("ZCODE_PROVIDER_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".zcode" / "v2" / "provider_config.json"


def mask(key: str) -> str:
    """脱敏展示:首 6 + 尾 4,中间省略号;过短(< 11 位)一律全掩,不泄露原值。"""
    text = (key or "").strip()
    if not text:
        return ""
    if len(text) < MASK_HEAD + MASK_TAIL + 1:
        return "•" * max(3, len(text))
    return f"{text[:MASK_HEAD]}…{text[-MASK_TAIL:]}"


@dataclass
class KeyCandidate:
    """ZCode 配置里发现的一条供应商凭据(providerId + 明文 key)。"""

    provider_id: str
    api_key: str

    @property
    def label(self) -> str:
        return mask(self.api_key)


@dataclass
class ResolvedKey:
    """一次裁决的结果:实际使用的 key + 来源(供界面说明"当前用的是哪个")。"""

    key: str = ""
    source: str = "none"          # config / env / zcode / none
    provider_id: str = ""

    @property
    def masked(self) -> str:
        return mask(self.key)

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)


def _provider_rules(path: Path | None = None) -> list:
    """ZCode 供应商规则列表;文件缺失/损坏/结构不符一律返回空表(视为未配置)。"""
    try:
        data = json.loads((path or config_path()).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    rules = (data.get("config", {}).get("providerConfigRules", {})
             .get("providerRules", []))
    return [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) \
        else []


def discover_keys(path: Path | None = None) -> list[KeyCandidate]:
    """ZCode 配置里**所有**带 key 的供应商,顺序即文件顺序。

    供配置窗口列表展示:仅读取,不判断该 key 是否适用于 OpenCode Go 端点
    (能否取数只有真请求才知道,界面据此如实提示)。
    """
    out = []
    for rule in _provider_rules(path):
        config = rule.get("config")
        access = config.get("access", {}) if isinstance(config, dict) else {}
        value = access.get("apiKey") if isinstance(access, dict) else None
        if isinstance(value, str) and value.strip():
            out.append(KeyCandidate(str(rule.get("providerId") or ""),
                                    value.strip()))
    return out


def resolve_key(configured: str = "", environ: dict | None = None,
                path: Path | None = None) -> ResolvedKey:
    """生效 key 的裁决:界面配置 > 环境变量 > ZCode 配置自动发现。

    界面配置优先是刻意的:用户在窗口里显式选过就必须生效,否则
    "配了没反应";环境变量与自动发现只在没有界面配置时起作用。
    任何读取/解析失败都退化为"未配置"(空 key),不抛异常。
    """
    env = os.environ if environ is None else environ
    preferred = (configured or "").strip()
    if preferred:
        return ResolvedKey(preferred, "config")
    key = (env.get(ENV_KEY) or "").strip()
    if key:
        return ResolvedKey(key, "env")
    for cand in discover_keys(path):
        if cand.provider_id == PROVIDER_ID:
            return ResolvedKey(cand.api_key, "zcode", cand.provider_id)
    return ResolvedKey("", "none")


def find_api_key(environ: dict | None = None, path: Path | None = None,
                 configured: str = "") -> str:
    """生效 key 的字符串形态(兼容入口,裁决规则见 resolve_key)。"""
    return resolve_key(configured, environ, path).key


# —— 出口候选(env 代理 → 系统代理 → 直连) ——

def _env_proxy_spec(env: dict) -> str:
    """环境变量里的代理地址(优先 https),无则空串。"""
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy",
                 "HTTP_PROXY", "http_proxy"):
        value = (env.get(name) or "").strip()
        if value:
            return value
    return ""


def _system_proxy_spec() -> str:
    """Windows 系统代理(注册表 WinINET 设置);未开启或读取失败返回空串。"""
    if os.name != "nt":
        return ""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        ) as key:
            enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            if not enabled:
                return ""
            server = str(winreg.QueryValueEx(key, "ProxyServer")[0])
    except (OSError, ImportError, IndexError):
        return ""
    # ProxyServer 可能是 "host:port",也可能是 "http=h:p;https=h:p" 形式
    if "=" in server:
        parts = dict(p.split("=", 1) for p in server.split(";") if "=" in p)
        server = parts.get("https") or parts.get("http") or ""
    server = server.strip()
    if not server:
        return ""
    return server if "://" in server else f"http://{server}"


def _proxy_opener(spec: str):
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": spec, "https": spec}))


def default_candidates(environ: dict | None = None):
    """出口候选列表 [(名称, opener)],按优先级排列;不可用的候选自动跳过。

    OPENCODE_GO_PROXY 可显式指定代理(排在最前,便于用户手动兜底)。
    """
    env = os.environ if environ is None else environ
    out = []
    pinned = (env.get("OPENCODE_GO_PROXY") or "").strip()
    if pinned:
        out.append((f"指定代理 {pinned}", _proxy_opener(pinned)))
    spec = _env_proxy_spec(env)
    if spec and spec != pinned:
        out.append((f"环境代理 {spec}", _proxy_opener(spec)))
    spec = _system_proxy_spec()
    if spec:
        out.append((f"系统代理 {spec}", _proxy_opener(spec)))
    # 直连(显式清空代理,避免 env 代理失效时被反复拖慢)
    out.append(("直连", urllib.request.build_opener(
        urllib.request.ProxyHandler({}))))
    return out


class Fetcher:
    """按候选出口取数,记住首个成功的出口供后续复用。"""

    def __init__(self, candidates=None):
        self._candidates = (default_candidates() if candidates is None
                            else list(candidates))
        self._preferred: str | None = None
        self.last_route = ""

    def _ordered(self):
        if self._preferred is None:
            return self._candidates
        head = [c for c in self._candidates if c[0] == self._preferred]
        tail = [c for c in self._candidates if c[0] != self._preferred]
        return head + tail

    def _request(self, url: str, key: str) -> urllib.request.Request:
        """每候选一份新 Request:ProxyHandler 会就地改写 Request(set_proxy),
        复用同一对象会让前一个候选的代理设置污染后续候选。"""
        return urllib.request.Request(url, headers={
            "Authorization": f"Bearer {key}",
            "x-api-key": key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })

    def get_json(self, url: str, key: str, timeout: float = TIMEOUT_S) -> dict:
        """发起 GET 并解析 JSON;全部候选失败时抛 QuotaError。"""
        if not key:
            raise QuotaError("未配置 API Key")
        errors = []
        for name, opener in self._ordered():
            try:
                with opener.open(self._request(url, key),
                                 timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as exc:
                # 有 HTTP 响应说明出口是通的:鉴权/限流错误不必再换出口
                if exc.code in (401, 403):
                    raise QuotaError(f"API Key 无效或无权限(HTTP {exc.code})")
                errors.append(f"{name}: HTTP {exc.code}")
                continue
            except Exception as exc:                       # 超时/连接被拒/DNS 等
                errors.append(f"{name}: {type(exc).__name__} "
                              f"{str(exc).strip()[:60]}".strip())
                continue
            self._preferred = name
            self.last_route = name
            return payload
        raise QuotaError("; ".join(errors) or "无可用网络出口")


# —— 解析 ——

def _percent(value) -> float | None:
    """百分比解析:接受数字或数字字符串,钳到 0~100;不可解析返回 None。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:                    # NaN
        return None
    return max(0.0, min(100.0, num))


def _timestamp(value) -> datetime.datetime | None:
    """ISO8601(带 Z 或 +08:00)解析为带时区时间;不可解析返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def parse_usage(payload, now: datetime.datetime | None = None) -> Quota:
    """把接口响应解析成 Quota;三窗口全缺时抛 QuotaError。"""
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        usage = payload if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        raise QuotaError("响应结构不符合预期")
    windows = []
    for key, label in WINDOW_KEYS:
        raw = usage.get(key)
        if not isinstance(raw, dict):
            windows.append(Window(key, label, None, None))
            continue
        windows.append(Window(
            key, label, _percent(raw.get("percent")),
            _timestamp(raw.get("resetsAt")), str(raw.get("status") or "")))
    if all(w.percent is None for w in windows):
        raise QuotaError("响应缺少额度字段")
    return Quota(windows, now or datetime.datetime.now(datetime.timezone.utc))


def fetch_usage(key: str, url: str = DEFAULT_URL, timeout: float = TIMEOUT_S,
                fetcher: Fetcher | None = None,
                now: datetime.datetime | None = None) -> Quota:
    """取一次额度;key 为空或请求失败抛 QuotaError。"""
    payload = (fetcher or Fetcher()).get_json(url, key, timeout)
    return parse_usage(payload, now)


# —— 展示辅助(纯函数) ——

def countdown(resets_at: datetime.datetime | None,
              now: datetime.datetime | None = None) -> str:
    """重置倒计时:<1h → "13m";<1d → "2h13m";≥1d → "3d09h";已过 → "已重置"。"""
    if resets_at is None:
        return ""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    seconds = (resets_at - now).total_seconds()
    if seconds <= 0:
        return "已重置"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"


def is_stale(fetched_at: float | None, now: float, max_age_s: float) -> bool:
    """取数时刻(epoch 秒)距 now 超过 max_age_s 视为陈旧。"""
    if not fetched_at:
        return True
    return (now - fetched_at) > max_age_s


def hottest(windows) -> Window | None:
    """已用百分比最高的窗口(大数字与告警取它);全无数据返回 None。"""
    known = [w for w in windows if w.percent is not None]
    if not known:
        return None
    return max(known, key=lambda w: w.percent)
