"""quota 模块单测:响应解析口径、key 发现、出口降级顺序与展示辅助。

数据纪律:一律用 tmp_path 伪造的供应商配置与假出口 opener,绝不读写
~/.zcode 真机文件。响应形状取自 2026-09-24 对真实接口的实测抓包:
{"usage":{"rolling":{"status":"ok","percent":14,"resetsAt":"...Z"}, ...}}
"""

import datetime
import json
import urllib.error

import pytest

import quota as Q

NOW = datetime.datetime(2026, 9, 24, 6, 0, tzinfo=datetime.timezone.utc)

# 测试占位串(明确非真实凭据):写成拼装值,避免被误读为硬编码密钥
_PLACEHOLDER = "test" + "-placeholder"

REAL_PAYLOAD = {"usage": {
    "rolling": {"status": "ok", "percent": 14,
                "resetsAt": "2026-09-24T09:12:14.135Z"},
    "weekly": {"status": "ok", "percent": 19,
               "resetsAt": "2026-09-28T00:00:00.000Z"},
    "monthly": {"status": "ok", "percent": 9,
                "resetsAt": "2026-10-23T15:28:56.000Z"},
}}


# —— 解析 ——

def test_parse_real_payload_three_windows():
    """真实形状:三窗口按 rolling/weekly/monthly 顺序解析,含中文标签。"""
    q = Q.parse_usage(REAL_PAYLOAD, now=NOW)
    assert [w.key for w in q.windows] == ["rolling", "weekly", "monthly"]
    assert [w.label for w in q.windows] == ["5 小时", "本周", "本月"]
    assert [w.percent for w in q.windows] == [14.0, 19.0, 9.0]
    assert q.windows[0].resets_at == datetime.datetime(
        2026, 9, 24, 9, 12, 14, 135000, tzinfo=datetime.timezone.utc)
    assert q.fetched_at == NOW


def test_parse_missing_window_stays_none():
    """缺某窗口:该窗口 percent 为 None,其余照常解析(不整体失败)。"""
    payload = {"usage": {"rolling": {"percent": 14}}}
    q = Q.parse_usage(payload, now=NOW)
    assert q.windows[0].percent == 14.0
    assert q.windows[1].percent is None
    assert q.windows[2].percent is None
    assert q.windows[1].resets_at is None


@pytest.mark.parametrize("raw,expected", [
    ("14", 14.0), (14.0, 14.0), (150, 100.0), (-5, 0.0), (None, None),
    ("abc", None), (True, 1.0),
])
def test_percent_parsing_and_clamp(raw, expected):
    """percent 容错:数字字符串可解析、越界钳到 0~100、不可解析为 None。"""
    assert Q._percent(raw) == expected


def test_parse_bad_shape_raises():
    """结构不符(非 dict / 无 usage 且无窗口字段)一律抛 QuotaError。"""
    for bad in ([], "nope", {"usage": "x"}, {}, {"usage": {}}):
        with pytest.raises(Q.QuotaError):
            Q.parse_usage(bad, now=NOW)


def test_parse_timestamp_tolerates_bad_values():
    """resetsAt 缺失/非法字符串 → None,不抛异常。"""
    payload = {"usage": {"rolling": {"percent": 1, "resetsAt": "not-a-date"}}}
    assert Q.parse_usage(payload, now=NOW).windows[0].resets_at is None


def test_hottest_picks_max_percent():
    """hottest 取已用最高的窗口;全无数据返回 None。"""
    q = Q.parse_usage(REAL_PAYLOAD, now=NOW)
    assert Q.hottest(q.windows).label == "本周"
    assert Q.hottest([]) is None
    assert Q.hottest([Q.Window("rolling", "5 小时", None, None)]) is None


# —— key 发现 ——

def _write_config(path, rules):
    path.write_text(json.dumps(
        {"config": {"providerConfigRules": {"providerRules": rules}}}),
        encoding="utf-8")


def _rule(provider_id, key=None):
    """构造一条供应商规则;key=None 表示该规则没有 apiKey 字段。"""
    access = {} if key is None else {"apiKey": key}
    return {"providerId": provider_id, "config": {"access": access}}


def test_find_api_key_prefers_env(tmp_path):
    """环境变量优先于配置文件。"""
    cfg_file = tmp_path / "provider_config.json"
    _write_config(cfg_file, [_rule(Q.PROVIDER_ID, _PLACEHOLDER)])
    assert Q.find_api_key({"OPENCODE_GO_API_KEY": _PLACEHOLDER},
                          path=cfg_file) == _PLACEHOLDER


def test_find_api_key_reads_zcode_rule(tmp_path):
    """从 ZCode 供应商规则里取 opencode-go-chat 的 key(跳过其他规则,去空白)。"""
    cfg_file = tmp_path / "provider_config.json"
    _write_config(cfg_file, [
        _rule("other-provider", _PLACEHOLDER),
        _rule(Q.PROVIDER_ID, f" {_PLACEHOLDER} "),
    ])
    assert Q.find_api_key({}, path=cfg_file) == _PLACEHOLDER


@pytest.mark.parametrize("rules,expected", [
    ([], ""),                                              # 无规则
    ([{"providerId": Q.PROVIDER_ID, "config": {}}], ""),    # 无 access
    ([_rule(Q.PROVIDER_ID, 123)], ""),                      # 非字符串
])
def test_find_api_key_missing_returns_empty(tmp_path, rules, expected):
    """配置缺项/类型不符 → 空串(视为未配置),不抛异常。"""
    cfg_file = tmp_path / "provider_config.json"
    _write_config(cfg_file, rules)
    assert Q.find_api_key({}, path=cfg_file) == expected


def test_find_api_key_missing_file(tmp_path):
    """配置文件不存在 → 空串。"""
    assert Q.find_api_key({}, path=tmp_path / "nope.json") == ""


# —— 出口降级 ——

class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeOpener:
    """假出口:成功返回 payload,失败抛给定异常;记录每次收到的请求。"""

    def __init__(self, result):
        self.result = result
        self.requests = []

    @property
    def calls(self):
        return len(self.requests)

    def open(self, req, timeout=None):
        self.requests.append(req)
        if isinstance(self.result, Exception):
            raise self.result
        return _Resp(self.result)


def test_each_candidate_gets_fresh_request():
    """回归:每个候选必须收到新的 Request 对象。

    urllib 的 ProxyHandler 会就地改写 Request(set_proxy),若循环外复用同一
    对象,前一个失效候选会把请求污染成走它的代理,导致后续候选(含直连)全部
    失败——实测踩到过,故用会污染请求的假出口锁住。
    """
    class _PoisoningOpener(_FakeOpener):
        def open(self, req, timeout=None):
            self.requests.append(req)
            req.host = "poisoned.invalid"          # 模拟 set_proxy 的就地改写
            raise urllib.error.URLError("boom")

    bad, good = _PoisoningOpener(None), _FakeOpener(REAL_PAYLOAD)
    f = Q.Fetcher([("坏出口", bad), ("好出口", good)])
    assert f.get_json("https://example.invalid", "k") == REAL_PAYLOAD
    assert bad.requests[0] is not good.requests[0]      # 各候选独立对象
    assert good.requests[0].host == "example.invalid"    # 未被前一个候选污染
    assert good.requests[0].full_url == "https://example.invalid"


def test_fetcher_falls_back_and_remembers_route():
    """首个出口失败自动降级到下一个,并记住成功的出口优先复用。"""
    bad = _FakeOpener(urllib.error.URLError("代理拒绝"))
    good = _FakeOpener(REAL_PAYLOAD)
    f = Q.Fetcher([("坏出口", bad), ("好出口", good)])

    assert f.get_json("https://example.invalid", "k") == REAL_PAYLOAD
    assert f.last_route == "好出口"
    assert bad.calls == 1 and good.calls == 1

    f.get_json("https://example.invalid", "k")
    assert bad.calls == 1                      # 已记住好出口,不再试坏出口
    assert good.calls == 2


def test_fetcher_all_candidates_fail_raises():
    """全部出口失败 → QuotaError,错误信息含各出口名。"""
    bad1 = _FakeOpener(urllib.error.URLError("x"))
    bad2 = _FakeOpener(TimeoutError())
    f = Q.Fetcher([("环境代理", bad1), ("直连", bad2)])
    with pytest.raises(Q.QuotaError) as err:
        f.get_json("https://example.invalid", "k")
    assert "环境代理" in str(err.value) and "直连" in str(err.value)


def test_fetcher_auth_error_stops_immediately():
    """401/403 是鉴权问题,不再换出口重试,直接报 Key 无效。"""
    auth = _FakeOpener(urllib.error.HTTPError("u", 401, "Unauthorized",
                                              None, None))
    other = _FakeOpener(REAL_PAYLOAD)
    f = Q.Fetcher([("坏", auth), ("好", other)])
    with pytest.raises(Q.QuotaError) as err:
        f.get_json("https://example.invalid", "k")
    assert "API Key" in str(err.value)
    assert other.calls == 0


def test_fetcher_empty_key_raises():
    """无 key 直接抛错,不发起任何请求。"""
    opener = _FakeOpener(REAL_PAYLOAD)
    with pytest.raises(Q.QuotaError):
        Q.Fetcher([("any", opener)]).get_json("https://example.invalid", "")
    assert opener.calls == 0


def test_default_candidates_order():
    """候选顺序:显式指定代理 → 环境代理 → … → 直连(直连恒为兜底)。"""
    env = {"OPENCODE_GO_PROXY": "http://127.0.0.1:1111",
           "HTTPS_PROXY": "http://127.0.0.1:2222"}
    names = [name for name, _ in Q.default_candidates(env)]
    assert names[0].startswith("指定代理")
    assert names[1].startswith("环境代理")
    assert names[-1] == "直连"


def test_fetch_usage_end_to_end_with_fake_opener():
    """fetch_usage 组合路径:解析 + fetched_at 使用注入时钟。"""
    f = Q.Fetcher([("fake", _FakeOpener(REAL_PAYLOAD))])
    q = Q.fetch_usage("k", fetcher=f, now=NOW)
    assert [w.percent for w in q.windows] == [14.0, 19.0, 9.0]
    assert q.fetched_at == NOW


# —— 展示辅助 ——

@pytest.mark.parametrize("delta_min,expected", [
    (13, "13m"), (59, "59m"), (60, "1h00m"), (133, "2h13m"),
    (24 * 60 + 30, "1d00h"), (3 * 24 * 60 + 9 * 60, "3d09h"),
    (0, "已重置"), (-5, "已重置"),
])
def test_countdown_formats(delta_min, expected):
    """倒计时格式:<1h 分钟;<1d Hh Mm;≥1d Dd Hh;已过标"已重置"。"""
    resets = NOW + datetime.timedelta(minutes=delta_min)
    assert Q.countdown(resets, now=NOW) == expected


def test_countdown_none_is_empty():
    assert Q.countdown(None, now=NOW) == ""


@pytest.mark.parametrize("fetched,expected", [
    (None, True), (0.0, True), (1000.0, False), (700.0, False), (699.0, True),
])
def test_is_stale(fetched, expected):
    """陈旧判定:超过 max_age_s 或从未成功过都算陈旧。"""
    assert Q.is_stale(fetched, now=1000.0, max_age_s=300) is expected
