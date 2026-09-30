# FEATURE_MAP.md — 功能地图

> 细则文件。记录各功能模块的"行为预期"（该做什么，可验证）和"已知待修问题"（哪里与该做的不一致），用于发现"以为≠实际"的偏差、防止改 A 误伤 B。
> 维护纪律见 `AGENTS.md`「二、功能地图维护」；标记规则：只有【强制】、【应当】、【可选】决定优先级。

## 怎么用这份文档

- **只记变化慢的**：行为预期与待修问题入地图；实现细节（具体函数、字段名等会随代码天天改的东西）不入。
- **用前先核实**：把本地图当作判断依据前，必须回到代码核对当前行为，不得直接采信文字——发现对不上当场修正。
- **谁动谁核**：修改某模块代码前，先读该模块条目对照当前代码。

## 条目格式模板

每个功能模块一条，结构如下（各小节可按模块需要增删，但"行为预期"不可省）：

```markdown
## <模块名>

**主代码**：<主要源码文件路径>
**模型/数据**：<核心数据表/模型>
**关联决策**：<相关 ADR / 版本记录>

### 一句话定位
<这个模块在系统里扮演什么角色，下游谁依赖它>

### 用户入口
| 入口 | 能做什么 |
|---|---|
| <页面/接口> | <能力> |

### 行为预期（可验证，已逐条核实代码）
1. **<预期 1>**：<该做什么，写到可核对程度，标注出处 file:line>。
2. **<预期 2>**：……

### 已知待修问题（发现但暂不动代码）
- **<编号>. <问题>**：<现象、影响、暂定对策；修复后改写为"已修复"并保留修复证据>

### 反直觉/易误解（踩坑预警）
- **<容易以为是 A、实际是 B 的点>**：<一句话说明>
```

## 行为预期的写作要求

- 每条预期**可验证**：能回答"怎么核对这条成立"（看哪个函数、跑哪个操作、观察什么）。
- 核实过代码的预期标注"已逐条核实代码"；凭印象写的必须回代码核实后再标注。
- 预期被测试锁住时，在条目里注明测试文件——预期未经测试锁住只有提醒作用，锁住才是机器保障。
- 模块对外行为改变时，同轮更新预期；发现代码与预期不符且属真 BUG 时，记入"已知待修问题"而非直接改预期迁就代码。

## 示例条目（示意，落地时删除并替换为真实模块）

> 落地顺序建议：按真实模块逐条建立条目，优先建"改 A 易误伤 B"的核心模块（数据源读取、统计聚合口径、窗口渲染、配置持久化）。

---

## 数据源读取（reader.py）

**主代码**：`reader.py`
**模型/数据**：ZCode `~/.zcode/cli/db/db.sqlite` 的 `model_usage` 表与 `session` 表（只读）
**关联决策**：无

### 一句话定位

唯一数据入口：以 `mode=ro` 只读打开 ZCode 用量库供统计聚合；对真实库零写入是本模块与整个项目的安全红线。

### 用户入口

| 入口 | 能做什么 |
|---|---|
| `fetch_day_rows` / `fetch_top_models` | 今日卡片主数字与模型 TOP3 |
| `fetch_last_gen_rows` | 各模型最近几条「已完成且有完整生成窗口」的调用行（生成速率取样口） |
| `fetch_session_usage` | 单会话全部用量合计（当前对话行） |
| `fetch_latest_session` / `fetch_session_title` | 库内最近活跃会话与标题（当前对话主信号） |

### 行为预期（可验证，已逐条核实代码）

1. **连接只读**：`open_ro` 用 URI `?mode=ro` 打开，任何写入抛 OperationalError。出处：`reader.py:open_ro`（`tests/test_reader.py::test_open_ro_blocks_writes` 锁住）。
2. **今日口径**：查询按 `started_at >= 今日0点(本地毫秒)` 过滤，昨日数据不进入统计。出处：`reader.py:fetch_*`（`tests/test_reader.py::test_fetch_day_rows_excludes_yesterday` 锁住）。
3. **模型 TOP3**：`fetch_top_models` 按当日总量倒序取前三，不足三个按实际数量返回。出处：`reader.py:fetch_top_models`。
4. **会话用量全期合计**：`fetch_session_usage` 不按天过滤，返回该会话 (总计,输入,输出,缓存) 四元组；无记录返回全 0。出处：`reader.py:fetch_session_usage`（`tests/test_reader.py::test_fetch_session_usage*` 锁住）。
5. **最近活跃会话**：`fetch_latest_session` 按 `session.time_updated` 倒序取第一；无会话返回 None。出处：`reader.py:fetch_latest_session`（`tests/test_reader.py::test_fetch_latest_session*` 锁住）。
6. **速率取样**：`fetch_last_gen_rows` 只收 `status='completed'` 且 `first_token_at`/`completed_at` 齐全、`output_tokens>0` 的今日行，按 `model_id` 分区各取最近若干条（`theme.RATE_MODEL_CANDIDATES`）后整体按 `completed_at` 倒序；未完成/已取消/缺首字时刻/无输出/昨日行全部排除。返回行数只随当日模型数增长（每模型 ≤ 候选条数），**不随 `model_usage` 行数增长**；多取几条是为让上层在最近一条样本不可信时退到该模型更早的样本。出处：`reader.py:fetch_last_gen_rows`（`tests/test_reader.py::test_fetch_last_gen_rows_*` 四条锁住，含 40 行 vs 4000 行的查询形态回归）。

### 已知待修问题

- **1. `model_id` 存在大小写变体，会拆成两行**：近 7 天实测 9 个不同 `model_id`，其中 `GLM-5.3-Flash`(4524 行) 与 `glm-5.3-flash`(415 行) 是同一个模型的不同写法，`GLM-5.3` 与 `glm-5.3` 同理。`fetch_top_models` 按 `model_id` 分组，故跨天看会把同一模型拆成两行（当天模型少时看不出来）。影响 tab 0 模型 TOP3 与速率行的归并口径；暂定不动（归一化会改动既有总量口径），先记录。

### 反直觉/易误解（踩坑预警）

- **started_at 是毫秒时间戳**：比较基准必须用 `stats.today_start_ms()` 的毫秒值；传秒值会静默查不到数据。
- **computed_total 已含缓存读取**：`input_tokens` 本身包含 cache_read，`computed_total = input + output`，不要把缓存列再加一遍。
- **表里藏着一批没用上的字段**：`status`/`first_token_at`/`completed_at`/`duration_ms`/`time_to_first_token_ms`/`reasoning_tokens` 都是真实数据（生成速率就靠前三个）。`duration_ms` 含首字等待，别拿它当生成时长。

---

## 套餐额度取数（quota.py）

**主代码**：`quota.py`
**模型/数据**：OpenCode Go 用量接口（`GET https://opencode.ai/zen/go/v1/usage`）+ ZCode 供应商配置（`~/.zcode/v2/provider_config.json`，只读）中的 API Key + 本机 `state.json` 的 `quota_api_key`（界面配置，托盘「配置…」写入）
**关联决策**：无

### 一句话定位

回答"OpenCode Go 套餐还剩多少额度"的唯一取数口：key 发现与来源裁决、多出口（环境变量代理 → Windows 系统代理 → 直连）降级请求、响应解析与倒计时格式化、展示用脱敏；纯逻辑无 Qt，供 `main.py` 后台线程调用、`card.py` 与 `config_window.py` 消费结果。

### 用户入口

| 入口 | 能做什么 |
|---|---|
| `resolve_key` / `find_api_key` | 裁决生效 key（界面配置 > 环境变量 > 自动发现）并给出脱敏与来源 |
| `discover_keys` | 列出 ZCode 配置里所有带 key 的供应商（配置窗口的候选列表） |
| `fetch_usage` | 取一次三窗口额度（`rolling`/`weekly`/`monthly` 的 percent 与 resetsAt） |
| `countdown` / `hottest` / `is_stale` / `mask` | 卡片与配置窗口展示用纯函数（倒计时、最热窗口、陈旧判定、脱敏） |

### 行为预期（可验证，已逐条核实代码）

1. **key 裁决顺序**：界面配置（`state.json.quota_api_key`）> 环境变量 `OPENCODE_GO_API_KEY` > ZCode 配置自动发现（`opencode-go-chat`）；三者皆无 = 未配置（空 key，`source="none"`）。界面配置优先是刻意取舍：界面里选过就必须生效，否则"配了没反应"。出处：`quota.py:resolve_key`（`tests/test_quota.py::test_resolve_key_*` 四条锁住）；`find_api_key` 是返回字符串的兼容入口。
2. **只读不写**：只读打开 `~/.zcode/v2/provider_config.json`（路径可用 `ZCODE_PROVIDER_CONFIG` 覆盖），缺失/损坏/无该供应商一律视为未配置，不抛异常；发现与裁决都不改动文件内容与修改时间。出处：`quota.py:discover_keys/_provider_rules`（`tests/test_quota.py::test_discover_keys_is_read_only`、`test_find_api_key_missing_file` 锁住）。
3. **发现列表**：`discover_keys` 列出配置里**所有**带 key 的供应商（顺序即文件顺序，跳过无 key/纯空白/非字符串行）；只负责列表，不判断该 key 是否适用于 OpenCode Go 端点（能否取数只有真请求才知道，由界面如实提示）。出处：`quota.py:discover_keys`（`tests/test_quota.py::test_discover_keys_*` 锁住）。
4. **脱敏定长**：`mask` 只留首 6 尾 4（定长 11 字符），过短一律全掩、原值不出现在结果里；界面上任何位置都不显示完整 key，唯一例外是配置窗口的手动输入框（用户自己粘贴核对用）。出处：`quota.py:mask`（`tests/test_quota.py::test_mask_*` 锁住）。
5. **出口候选顺序**：`OPENCODE_GO_PROXY`（显式指定）→ 环境变量代理 → Windows 系统代理（注册表 WinINET，未开启/读取失败则跳过）→ 直连；首个成功的出口被记住并在后续请求里优先复用，鉴权类 HTTP 401/403 不再换出口重试。出处：`quota.py:default_candidates/Fetcher._ordered/get_json`（`tests/test_quota.py::test_fetcher_*`、`test_default_candidates_order` 锁住；2026-09-24 真机实测：环境变量代理 7897 失效 → 自动旁路到系统代理 17891 成功）。
6. **每候选一份新 Request**：`urllib` 的 `ProxyHandler` 会就地改写 Request（`set_proxy`），复用同一对象会让失效候选污染后续候选（含直连）导致"全失败"；故候选循环内每次新建 Request。出处：`quota.py:Fetcher._request`（`tests/test_quota.py::test_each_candidate_gets_fresh_request` 锁住）。
7. **解析口径**：三窗口固定按 `rolling/weekly/monthly` 顺序输出中文标签「5 小时/本周/本月」；percent 接受数字或数字字符串并钳到 0~100，不可解析为 None；`resetsAt` 非法/缺失为 None；三窗口全无 percent 或整体结构不符才抛 `QuotaError`。出处：`quota.py:parse_usage`（`tests/test_quota.py::test_parse_*`、`test_percent_parsing_and_clamp` 锁住）。
8. **失败降级**：请求失败（超时/连接被拒/HTTP 非 200/解析失败）抛 `QuotaError`，由调用方保留上次数值并标记状态；`Fetcher` 不写任何本地状态。出处：`quota.py:Fetcher.get_json`、`main.py:_QuotaThread.run`。
9. **倒计时格式**：`<1h → "13m"`；`<1d → "2h13m"`；`≥1d → "3d09h"`；已过 → `"已重置"`；无重置时间 → 空串。出处：`quota.py:countdown`（`tests/test_quota.py::test_countdown_*` 锁住）。

### 已知待修问题

- **1. README 宣称的 `OPENCODE_GO_USAGE_URL` 未实现**：README「工作原理」节写明"可用环境变量 `OPENCODE_GO_USAGE_URL` 覆盖地址"，但全仓库 grep 无任何代码读取该变量（`DEFAULT_URL` 在 `fetch_usage` 默认参数里写死）。影响：按文档改环境变量不生效。暂定对策：要么实现该覆盖，要么删掉该说明——待用户定；本轮（加配置窗口）不夹带。

### 反直觉/易误解（踩坑预警）

- **界面配置压过环境变量**：`OPENCODE_GO_API_KEY` 只在"没有界面配置"时生效；环境变量是给人临时兜底的，不是最高优先级。
- **手填非 OpenCode Go 的 key 必然失败**：额度端点只有 OpenCode Go 一路（opencode.ai），kimi/workbuddy 等 key 会 401；这是如实反馈（状态行显示 HTTP 401），不是 bug。
- **环境变量代理可能是坏的**：本机 `HTTPS_PROXY` 指向失效端口 7897，而真正可用的是系统代理 17891；只依赖 env 代理会全盘失败，故必须保留系统代理与直连兜底。
- **接口只给百分比，没有绝对值**：实测响应只有 `{status, percent, resetsAt}`，没有"已用/总额"数字，所以卡片只能显示已用百分比与重置倒计时，别指望换算成美元或 token 数。
- **官方没有公开用量 API**（anomalyco/opencode#31084 已确认），该端点是社区用法，官方若变更需要跟着改。

---

## 配置窗口（config_window.py）

**主代码**：`config_window.py`（入口 `main.py:open_config`，候选来自 `quota.discover_keys`，落盘走 `config.save`）
**模型/数据**：`state.json.quota_api_key`（本机配置）+ ZCode 供应商配置（只读）
**关联决策**：无

### 一句话定位

托盘右键「配置…」打开的独立纸感窗口，回答"套餐页的数据用哪个 key"：三档互斥来源（自动发现 / ZCode 配置里的 key / 手动输入）+ 保存即生效 + 落盘回读校验；独立窗口不占卡片空间，卡片布局与几何零改动。

### 用户入口

| 入口 | 能做什么 |
|---|---|
| 托盘右键「配置…」 | 打开/置前配置窗口（复用同一实例，不开第二个） |
| 窗口内选项行 | 选来源；选中「手动输入」行才启用输入框 |
| 「保存」/「取消」/「×」/ESC | 保存并立即生效；取消、关闭都不改配置 |

### 行为预期（可验证，已逐条核实代码）

1. **不占卡片空间**：本功能不改卡片 296×218 布局、tab 宽度与位置、点击/拖动判定（顶行仍两格）；配置窗口是独立顶层窗口（`Qt.Tool`，不进任务栏）。出处：本文件「窗口渲染（card.py）」几何预期（本轮未改）+ `config_window.py` 独立类。
2. **三档互斥来源**：行序固定「自动发现（默认）→ ZCode 配置发现的 key（脱敏显示 + providerId 附注）→ 手动输入（恒为末行）」；"选哪行 = 存哪个值"由纯函数决定：自动发现存空串（回落自动发现）、key 行存该 key、手动行存去空白后的输入。出处：`config_window.py:build_rows/selected_value/row_index_for`（`tests/test_config_window.py::test_rows_order_is_auto_keys_manual`、`test_selected_value_maps_row_to_value`、`test_row_index_backfills_from_configured` 锁住）。
3. **回填**：打开/刷新时按已保存值定位——空 = 自动发现；命中某个已发现的 key = 该行；其余 = 手动输入行并把明文填回输入框（便于核对）。出处：`config_window.py:row_index_for/refresh`（`tests/test_config_window.py::test_refresh_rebackfills_configured` 锁住）。
4. **输入框只在手动行可用**：未选中该行时清空 + 置灰（连背景一起压暗），选中时获得焦点；这是界面上唯一显示完整 key 的位置（用户自己粘贴核对用）。出处：`config_window.py:_sync_selection` + 输入框 QSS（`tests/test_config_window.py::test_field_enabled_only_for_manual_row` 锁住）。
5. **保存闭环**：写 `state.json.quota_api_key` → 回读校验 → 成功后关窗并发 `key_saved`（由 `main._apply_quota_key` 立即换 key 重取）；手动行内容为空、或写盘校验不一致时**不关窗、不发信号**，窗口内红字说明原因。出处：`config_window.py:_save/save_configured`（`tests/test_config_window.py::test_save_*` 四条锁住）。
6. **窗口内自证**：顶部两行显示「当前使用：<脱敏 key>（来源）」与「上次取数：<与套餐页同一口径的文案>」——重开窗口即可确认配置是否真的生效，不必去翻卡片。出处：`config_window.py:_draw_info` + `card.py:quota_fetch_note`。
7. **长列表可滚**：候选行数超过 `KEYWIN_ROWS_MAX`(9) 时窗口不再长高，选项区用滚轮翻看并在栏目标签右侧提示「共 N 项 · 滚轮翻看」；手动输入行滚出视野时输入框隐藏（避免浮在别的行上）。出处：`config_window.py:layout/wheelEvent/_row_y`（`tests/test_config_window.py::test_layout_grows_with_rows_and_caps`、`test_row_at_hit_test_and_scroll` 锁住）。
8. **视觉与卡片同语言**：暖白纸底 + 细灰线 + 同套投影/圆角/色板，字号走与 card.py 同一套 px 取整规则，色值全部取自 `theme.py`；标题「套餐 API Key」，右上「×」关闭，ESC 关闭，空白处可拖动。2026-09-30 截图验收（真实字体、`WA_DontShowOnScreen` 离屏渲染）：`out/shot_config_auto.png` / `_picked.png` / `_manual.png` 三态行文字与附注无重叠、说明文字不截断。出处：`config_window.py:paintEvent/_draw_*`、`tools/shot_config.py`。

### 反直觉/易误解（踩坑预警）

- **"自动发现"是一档显式选择，不是"未配置"**：它表示"交给 `quota.resolve_key` 按 环境变量 → ZCode 配置 去挑"；所以选它保存会写入空串，之前手填的 key 会被清掉。
- **窗口复用但位置不持久化**：反复打开只刷新内容、不新开窗口，位置在本会话内保持；重启程序后回到鼠标所在屏幕中央。
- **候选列表不做可用性判断**：列的是"ZCode 配置里有 key 的供应商"，不代表这些 key 都能取 OpenCode Go 额度（实测只有 `opencode-go-chat` 那路可用，其余会 401 并在套餐页如实显示）。

---

## 统计聚合（stats.py）

**主代码**：`stats.py`
**模型/数据**：无（纯函数）
**关联决策**：无

### 一句话定位

把原始行变成界面数字的唯一口径：按天/分模型聚合与中文单位换算都在这里，UI 不得自行计算。

### 行为预期（可验证，已逐条核实代码）

1. **中文单位**：≥1亿 → `X.XX亿`；≥1万 → `X.X万`；否则千分位整数；99,999,999 显示 `10000.0万`（与设计稿口径一致，不进位到亿）。出处：`stats.py:cny`（`tests/test_stats.py::test_cny_units` 锁住）。
2. **完整数字**：`full(v)` 输出千分位整数字符串（无单位），供三列小数额跳动可感知显示。出处：`stats.py:full`（`tests/test_stats.py::test_full_units` 锁住）。
3. **聚合字段**：count/input/output/cache/total 五项，空输入返回全零。出处：`stats.py:aggregate`。
4. **占比**：`shares` 按当日总量归一，总量为 0 时全 0。出处：`stats.py:shares`。
5. **生成速率口径**：`speed_of` = `output_tokens ÷ ((completed_at − first_token_at)/1000)`，**分母排除首字等待**——真机样本整轮 13.765s 里 7.9s 在等首字，用 `duration_ms` 会把速度低估一半以上；且只算 output（与含缓存的"今日总量"是两个口径）。字段缺失、生成窗口 < `RATE_MIN_WINDOW_MS`(100ms)、速度 > `RATE_MAX_TOK_S`(2000) 一律返回 None（判为上游写入异常）。出处：`stats.py:speed_of`（`tests/test_stats.py::test_speed_of_*` 锁住）。
6. **取速率**：`gen_rates` 单次遍历倒序候选行，**每个模型各取自己最近一次可信样本**（多模型可并行生成，不是"最近一条通吃"；最近一条不可信则退到该模型更早的候选），返回三项 =（顶行当前速率, 各模型最后速率, 正在生成的模型集合）。两个口径分开：**顶行速率**只在新鲜期（`RATE_FRESH_MS`=60s）内取，超期返回 None（界面显「空闲」）；**各模型速率**取"最后一次"的读数、**不限新鲜期**——空闲时仍可回顾刚才各模型多快，是否还在跑由活跃集合标记（样本仍在新鲜期内）。出处：`stats.py:gen_rates`（`tests/test_stats.py::test_gen_rates_*` 四条锁住，含"过期仍给最后读数但 active 为空"与新鲜期边界）。
7. **速率显示**：`fmt_rate` 无样本 → `空闲`；取整；超过 `RATE_MAX_SHOWN`(999) 钳成 `999+`；单位由调用方给（顶行带 `t/s`，模型行不带）。出处：`stats.py:fmt_rate`（`tests/test_stats.py::test_fmt_rate_idle_clamp_and_unit` 锁住）。
8. **轮次显示**：`fmt_count` 4 位及以内 `5124次`（无空格），达万 `1万次`（**不带小数**）。槽位实测 39px，故 `5124 次`(41px)、`99999次`(41px)、`1.0万次`(40px) 三种写法都放不下、已否决。出处：`stats.py:fmt_count`（`tests/test_stats.py::test_fmt_count_units`、`tests/test_card_rate.py::test_cap_count_rejects_decimal_wan_form` 锁住）。

### 已知待修问题

- （暂无）

---

## 当前会话解析（current.py）

**主代码**：`current.py`
**模型/数据**：`%APPDATA%/ZCode/session/Local Storage/leveldb`（ZCode 桌面端 localStorage，只读）+ `session` 表活跃时间
**关联决策**：无

### 一句话定位

回答"用户当前查看的是哪个对话"：扫描桌面端 localStorage 的 `zcode-v4-last-session:v1:<工作区>` 键拿会话候选，配合 `SessionResolver` 以数据库最近活跃会话为主信号裁决。

### 行为预期（可验证，已逐条核实代码）

1. **扫描只读且容错**：目录缺失/文件读失败返回空候选，不抛错。出处：`current.py:scan_candidates`（`tests/test_current.py::test_scan_missing_dir` 等锁住）。
2. **键值编码自由组合**：键与值各自可能是 ASCII 或 UTF-16LE（Chromium 独立选编码），四种组合都能提取出 `sess_<uuid>`。出处：`current.py:_SESS/_SESS_U16`（`tests/test_current.py::test_scan_utf16_key_with_ascii_value` 锁住）。
3. **首轮不覆盖**：`SessionResolver` 首次轮询只建档，无论候选是什么都返回库内最近活跃会话。出处：`current.py:SessionResolver.resolve`（`tests/test_current.py::test_resolve_first_poll_no_override` 锁住）。
4. **切换动作可覆盖**：候选里首次出现的新会话 ID（≠最近活跃会话）视为一次切换，立即跟随该会话；主会话在其后又有新活动、或覆盖目标自己成为最近活跃时覆盖解除。出处：`current.py:SessionResolver`（`tests/test_current.py::test_resolve_fresh_candidate_overrides` 等 5 条锁住）。

### 已知待修问题

- **1. localStorage 键族随 ZCode 版本演进**：曾观察到 `zcode-v4-last-session` 记录随文件轮转/窗口关闭消失、活跃工作区记录缺失的现象。届时扫描退化为空候选，卡片显示"最近活跃会话"（主信号兜底，不会答错到陈旧会话）。若 ZCode 改键名导致整层失效，同样只失去切换跟随能力，不产生错误显示。

### 反直觉/易误解（踩坑预警）

- **纯翻看切换靠覆盖信号**：翻看旧对话不产生数据库活动，靠"新会话 ID 首次出现在候选"捕获；若切到的是最近已见过的会话 ID，则不会触发覆盖（保守取舍，宁可显示主信号也不错跟）。
- **不解析 leveldb 内部结构**：启发式字节扫描，ZCode 大版本更新可能改变键族；失效模式是"失去切换跟随"，不是"显示错误会话"。

---

## 增量摊放调度（drip.py）

**主代码**：`drip.py`
**模型/数据**：无（内存池 + 注入时钟的纯逻辑状态机）
**关联决策**：无

### 一句话定位

把每段到账的用量增量按其产生间隔（与上一次到账的时间差）在后续时间里按 1~3s 节拍分步释放，让悬浮窗数字常跳而显示落后有界；card 数值显示的唯一节拍源。

### 行为预期（可验证，已逐条核实代码）

1. **按时长摊放**：单段摊放时长 = 该段产生间隔（首段无参照按一个节拍 4s），封顶 `SMOOTH_MAX_DURATION_MS`（10 分钟）；段内按剩余时长均分多跳，过期一次清空。出处：`drip.py:add/release`（`tests/test_stream.py::test_duration_matches_arrival_gap`、`test_max_duration_cap` 锁住）。
2. **守恒与并行**：各段独立成池、独立期限，同跳合并释放、先到期先放完；任意时刻 已释放+在池 = 已入池。出处：`drip.py:release`（`test_conservation_parallel_batches` 锁住）。
3. **落后有界**：显示不超真实；到账停止后 max(末段时长， 节拍) 内追平。出处：`drip.py` 期限机制（`test_display_lag_bounded_and_catches_up` 锁住）。
4. **段内等比**：单段多字段同跳共用抖动因子、按剩余量等比释放；多段合计不保证全局等比。出处：`drip.py:_plan`（`test_fields_released_proportionally` 锁住）。
5. **相邻跳必异**：每跳释放量 = 均分 × 抖动(0.7~1.3)，total 与上一跳取整撞值时换抖动重抽(至多 3 次)；末跳/过期不抖动、一次清空；`reset()` 清全部池(跨天时由 card 触发)。出处：`drip.py:release/_plan/reset`（`test_adjacent_releases_differ`、`test_reset_drops_all_pending` 锁住）。

### 反直觉/易误解（踩坑预警）

- **零增量不入池也不推进到账时刻**：间隔跨过无新增的轮询继续累计，直到真正有记录的那次。
- **释放量随期限逼近变大**：节拍固定但每次释放量按剩余时长折算，不是恒定等分。
- **末跳与过期跳不抖动**：抖动只作用于还有后续跳的池，"期限到即清空"语义不受抖动影响。

---

## 窗口渲染（card.py）

**主代码**：`card.py`
**模型/数据**：消费 stats 聚合结果
**关联决策**：无

### 一句话定位

324×246 窗体（296×218 内容 + 四周投影边距）纸感浅色无边框置顶横卡的全部视觉呈现：QPainter 自绘布局、数值摊放补间、增量飘字、占比条与呼吸灯动画、底部当前对话行、拖动交互。顶行右侧两格 tab 分两页：tab 0 = 用量（默认页，含今日总量/三列/模型 TOP3/当前对话），tab 1 = 套餐（OpenCode Go 三窗口额度）。另有三处例外：底部当前对话行、生成速率（顶行当前速率 + 模型行各自速率）都整值直显不进池；模型行速率取该模型最后一次读数，仍在新鲜期内（正在生成）的转红、历史读数保持灰。

### 行为预期（可验证，已逐条核实代码）

1. **皮肤为纸感浅色**（选型稿 `design/皮肤总览.html` 01 号）：暖白纸底 `#fdfcf9`、细灰线描边、橙色强调、四周落地柔影；窗口比卡片大一圈（四周 14px 透明边距画投影），色值一律取自 `theme.py`，布局坐标常量集中在 `card.py` 顶部。出处：`card.py:_draw_card/_draw_shadow`、`theme.py`。
2. **窗体 296×218**（含投影边距 324×246）：默认落位主屏右下角（任务栏上方，右边距 20、底边距 14），用户拖动后位置写入 `state.json` 并按原位恢复。出处：`main.py:_restore_pos`。
3. **增量摊放**：每轮轮询到账的增量进 `drip` 池，按其产生间隔、1~3s 一跳分步释放为显示值（单段封顶 10 分钟）；显示全程 ≤ 真实值，到账停止后追平；首帧直接显示真实值不摊放；当日累计回退（跨零点/上游修正）时清池并立即对齐新一天真实值，旧量不再放出。出处：`card.py:set_data/_drip`、`drip.py`（`tests/test_stream.py` 锁住）。
4. **增量飘字**：摊放调度每释放一跳，大数字右侧与三列右侧各自冒出「+释放量」上浮淡出；首帧与零释放时不飘。出处：`card.py:_drip/_draw_rise`。
5. **三列完整数字**：输入/输出/缓存显示千分位完整数字（左对齐、无中文单位），缓存行占比小字紧跟数字右侧（`FS_PCT`）；标签列贴近竖分隔线（x=148），数值左对齐区 176~278（亿级 11 位数+占比不溢出）。出处：`card.py:_draw_main`、`stats.py:full`。
6. **占比条**：宽度按当日总量归一平滑过渡，绘制时最小 3px；条区 `M_TRACK_X ~ +M_TRACK_W`（132~181），右端让位给「速率 + 单空格 + 累计」列，互不重叠；不足三个模型时多余行不渲染。出处：`card.py:_bar_targets/_draw_models`（几何锁 `tests/test_card_rate.py::test_model_rate_column_never_overlaps_bar` 锁住——条宽定为 49px 就是按"最坏速率组 96px 仍留 5px 净空"推出来的）。
7. **拖动**：左键拖动移动窗口，松开后位置写入 `state.json`。出处：`card.py:mouse*Event`。
8. **异常态独立配色**：数据源异常时呼吸灯与状态文字变红橙 `C_ERROR`，与第三模型蓝色区分；异常期间摊放池与显示保持不动。出处：`card.py:_draw_top/set_error`。
9. **顶行日期与时钟**：标签为「M月D日 周X + 24 小时制 HH:MM」，每帧按当前时间生成——跨零点自动换日、时钟每秒刷新。出处：`card.py:_draw_top`。
10. **底部当前对话行**（y=180 分隔线 + 行中心 198）：左侧会话标题（省略号截断,吃行首剩余宽度），右侧「N（P%）」——N 为该会话全部总计走 `stats.cny`（只出现万/亿与千分位整数），P = 缓存÷总计取整百分比，total 为 0 时 P 显示 0；不显示冒号或"总"等标签字；字号 `FS_CUR`(11px)；【反向约束】这行数字不走 drip 池、无飘字/补间，`set_data` 每轮整值直显真实汇总（`cur` 不在 `TWEEN_KEYS`）；无会话数据时整行不画。出处：`card.py:_draw_cur/set_data`（`tests/test_card_cur.py` 锁住，含"不进池"反向测试与"当日数字照常进池"正向对照）。
11. **tab 控件与切换**：顶行两格「用量 / 套餐」（`TAB_Y/W/H`，x 由 `tab_x()` 动态算出——取"左侧日期时钟文本结束位置"与"右侧次数起点"的中点，二者间距相等；右侧按 `TAB_RIGHT_REF`（4 位数参照）计算，故次数位数变化时 tab 不抖动）；激活格橙字 + 橙淡填充（`C_ACCENT` alpha 0.14），未激活灰字；默认 `tab = 0`。出处：`card.py:header_text/tab_x/_draw_tabs/tab_at`（`tests/test_card_tab.py::test_tab_centered_between_head_and_count`、`test_tab_x_tracks_head_text_width`、`test_tab_at_hit_test`、`test_default_tab_is_usage` 锁住）。
12. **点击与拖动区分**：按下→释放位移 ≤ `CLICK_MAX_MOVE`(4px) 且落在 tab 控件内才切页；位移超过阈值按拖动处理（移动窗口并保存位置），纯点击不再写 `state.json`。出处：`card.py:is_click/mouseReleaseEvent`（`tests/test_card_tab.py::test_click_on_tab_switches_and_click_does_not_save_pos`、`test_drag_keeps_tab_and_saves_pos` 锁住）。
13. **tab 0 内容零改动**：切到套餐页再切回，tab 0 的补间目标、drip 摊放池、真实值累积都照常（切页不重绘 tab 0 内容、也不动其状态）。出处：`card.py:paintEvent` 分派（`tests/test_card_tab.py::test_tab0_numbers_and_pool_untouched_by_tab_switch` 锁住）。
14. **套餐页排版**（`_draw_quota`）：大数字 = 已用百分比最高的窗口（`quota.hottest`，达 `QUOTA_WARN_PCT`(90) 转 `C_ERROR`），cap 文案「{窗口名}额度已用」；三行固定 `5 小时/本周/本月`（行中心 `Q_ROW_CY`，复用 tab 0 的色点/行高几何）+ 进度条（左端 `Q_BAR_X` 贴近窗口名、右端让位百分比列）+ 已用百分比（数字与百分号分两段绘制、中间留 `Q_PCT_GAP` 间距，右端 `Q_PCT_RIGHT`）+ 重置倒计时（右端 `Q_CD_RIGHT`，字号与百分比同档 `FS_Q_CD = FS_Q_PCT`，`quota.countdown`）；底部一行状态（`_quota_status`）：正常「套餐额度 · 更新于 HH:MM」灰字、陈旧「数据陈旧 · 最后更新 HH:MM」警示色、失败「<原因> · 显示 HH:MM 数据」警示色、未配置灰字。**状态行仅在"界面里显式配过 key"时**在正常态插一句脱敏 key（「套餐额度 · sk-ab12…cdef · 更新于 HH:MM」，实测 203px < 可用 266px）；默认自动发现/环境变量时不插（文案与改版前逐字一致），陈旧/失败/未配置三态也不插（那三种先行文案已很长，让位给原因本身）。出处：`card.py:_draw_quota/_quota_status/set_quota_key_label`（`tests/test_card_tab.py::test_quota_page_renders_every_state`、`test_quota_status_shows_key_only_when_configured`、`test_quota_status_key_not_shown_on_abnormal_states` 锁住）。
15. **呼吸灯随当前页**：tab 0 看用量数据源异常，tab 1 看额度状态（未配置不算故障、不转红；失败或陈旧转 `C_ERROR`）。出处：`card.py:_top_problem`（`tests/test_card_tab.py::test_light_follows_current_tab` 锁住）。
16. **额度数值不进 drip 池**：`set_quota` 首帧落位、其后走 `TWEEN_MS` 补间，不产生飘字、不入池。出处：`card.py:set_quota`（`tests/test_card_tab.py::test_quota_values_never_enter_drip_pool`、`test_quota_first_set_snaps_then_tweens` 锁住）。
17. **顶行当前速率**：占用原「次数」的位置（右对齐 `TOP_RIGHT`），显示 `S.fmt_rate(rate, RATE_UNIT)`（如 `159 t/s`；空闲显 `空闲`）。`TAB_RIGHT_REF` 由 `0000 次`(41px) 换成 `000 t/s`(42px)，实测差 1px，**故 tab 位置不变（仍为 164）**；文案另按"不压到 tab 右侧格标签墨迹"的可用宽度（`TOP_RIGHT −(tab_x + TAB_LABEL_OFFSET)`≈58px）截断兜底。出处：`card.py:top_right_text/_draw_top`（`tests/test_card_rate.py::test_tab_position_unchanged_by_reference_swap`、`test_top_right_text_fits_beside_tab` 锁住）。
18. **cap 行轮次**：`今日 TOKENS` 右侧、右对齐至 `CAP_COUNT_RIGHT`(140)，文案走 `S.fmt_count`（`5124次` / 万级 `1万次`），字号沿用 `FS_REQ`。槽位实测 39px。出处：`card.py:_draw_main`（`tests/test_card_rate.py::test_cap_count_slot_fits` 锁住）。
19. **模型行各自速率**：每行在累计值左侧显示该模型自己的速率——右对齐、与累计之间隔**单空格** `RATE_GAP`(7px)、**不带单位**、字号 `FS_MI_V`(12.5px) 加粗；取该模型**最后一次**可信样本的读数（**不限新鲜期**，今日无可信样本才显 `空闲`）。配色由 `model_rate_color(active)` 决定：样本仍在 `RATE_FRESH_MS`(60s) 内（该模型正在生成）→ 红 `C_RATE_ACTIVE`，否则灰 `C_TEXT_LABEL`（历史读数）——空闲时仍能看到各模型刚才多快，靠颜色区分"还在跑"与"已停下"。与累计一样整值直显：**不进 drip 池、无飘字、不补间**（`TWEEN_KEYS` 不含 `rate`/`model_rates`/`active_models`）。出处：`card.py:_draw_models/set_data/model_rate_color`（`tests/test_card_rate.py::test_rate_never_enters_drip_pool` 反向锁住、`test_model_rate_color_active_red_else_grey` 锁配色、`test_active_models_follows_each_set_data` 锁整值替换）。
20. **异常态顶行**：`set_error` 时顶行右端显示固定短句 `ERROR_TOP_TEXT`（「数据源异常」，与改版前一致），**不显示异常类名**——实测 `OperationalError` 97px、`sqlite3.OperationalError` 145px，都会越过 tab；轮次与各速率按既有容错约定保留上次值（与"今日总量在异常期间同样是上次值"同理），状态由呼吸灯转红 + 短句标记。出处：`card.py:top_right_text/set_error/_draw_top`（`tests/test_card_rate.py::test_error_keeps_cap_count_and_moves_warning_to_top_row` 锁住）。
21. **配置窗口的两个读取口**：`set_quota_key_label(label)` 只存一个字符串（空 = 不显示），卡片不碰 `state.json`；`quota_fetch_note()` 返回「上次取数」文案与是否故障，**复用 `_quota_status` 同一份口径与配色来源**（配置窗口与套餐页状态行不会各说各话）。出处：`card.py:set_quota_key_label/quota_fetch_note`（文案一致性由 `tests/test_card_tab.py::test_quota_status_*` 两条间接锁定）。

### 已知待修问题

- （暂无）

### 反直觉/易误解（踩坑预警）

- **窗口 hide 后 grab() 仍可渲染**：截图验收无需 show，避免打扰用户桌面（`tools/shot.py` 即此做法）。

---

## 入口装配（main.py）

**主代码**：`main.py`
**模型/数据**：组装 reader/stats/card/config
**关联决策**：无

### 一句话定位

程序生命周期管理：单实例唤醒、托盘常驻、1.5s 轮询、当前会话解析装配、窗口位置恢复与屏幕范围校验。

### 行为预期（可验证，已逐条核实代码）

1. **单实例**：重复启动时向已有实例发 `show` 后自身退出，不开第二个窗口。出处：`main.py:notify_running_instance`。
2. **容错**：读库异常时保留上次显示并标记"数据源异常"（呼吸灯变红橙），下次轮询自动重连。出处：`main.py:_poll`。
3. **位置校验**：恢复位置时窗口须与任一屏幕相交，否则落回主屏右下默认位。出处：`main.py:_restore_pos`。
4. **轮询装配当前会话**：每轮轮询固定 **6 条查询**（当日行、模型 TOP3、近期生成行、最近活跃会话、会话标题、会话用量）+ 一次 leveldb 扫描，查询条数固定、不随 `model_usage` 行数线性增长；装配结果经 `current.SessionResolver` 裁决后交给 `card.set_data` 的 `cur` 字段。出处：`main.py:_poll/_current_session`（`tests/test_current.py` 裁决行为锁住）。
7. **生成速率装配**：`_poll` 里 `fetch_last_gen_rows` 取每模型固定候选条数（`RATE_MODEL_CANDIDATES`=3）后交 `S.gen_rates(rows, now_ms, RATE_FRESH_MS)`，结果写入 `d["rate"]`（顶行当前速率）、`d["model_rates"]`（各模型最后速率）与 `d["active_models"]`（正在生成的模型集合，驱动模型行速率转红）一并 `set_data`；速率只算 output，与含缓存的"今日总量"口径不同，故单独取数、不并入 `aggregate`。出处：`main.py:_poll`。
5. **托盘菜单五项**：跟随显示、开机自启动、配置…、显示/隐藏、退出；自启动勾选状态初始化自注册表现状（先设状态后连信号，初始化不产生注册表写），勾选变化即写/删 Run 键，失败回弹勾选并托盘气泡提示。出处：`main.py` 托盘装配、`_toggle_autostart`。
6. **额度轮询独立线程**：`_QuotaThread` 启动即拉一次、此后每 `QUOTA_POLL_MS`(60s) 一次（QThread 内 sleep，不占 UI 线程）；结果经信号回主线程 `card.set_quota`，失败只上报错误文案（卡片保留上次数值并标陈旧）；退出时 `stop()` + `wait(2000)` 收线程（分片睡眠，最坏 0.2s 退出）。本条失败不影响 1.5s 的本地库轮询与 tab 0 显示。出处：`main.py:_QuotaThread/_on_quota/_cleanup`。
7. **key 来源与"未配置"边界**：启动时 key 取自 `state.json.quota_api_key` → 交 `quota.resolve_key` 裁决（界面配置 > 环境变量 > 自动发现）；裁决结果为空则**不起线程**，直接置"未配置 OpenCode Go（需 API Key）"灰字提示（`kind="config"`，不当作故障、呼吸灯不转红）。出处：`main.py:App.__init__/_apply_quota_key`。
8. **配置窗口与换 key 即时生效**：`open_config` 每次打开都重扫 ZCode 配置并按当前配置刷新内容（复用同一实例、已开着只置前，不开第二个；首次落在鼠标所在屏幕中央）；窗口 `key_saved` 直接连到 `_apply_quota_key`——先断开旧线程信号（防上一条 key 的结果回灌界面）、`stop()`+`wait(2000)`、`setParent(None)`+`deleteLater()`，再按新 key 起新线程（线程启动即取一次，故不等下一个 60s 周期）；状态行的 key 标签只在 `source=="config"`（界面配置）时设置，环境变量/自动发现不显示。出处：`main.py:open_config/_center_config/_apply_quota_key`（真机端到端 2026-09-30 已验证：选中 opencode-go-chat 行保存 → `state.json` 写入且回读一致 → 线程重建 → 立即取回三窗口 6%/2%/1%；验证后 `state.json` 已还原，未留副作用）。

### 已知待修问题

- （暂无）

---

## 配置持久化（config.py）

**主代码**：`config.py`
**模型/数据**：`state.json`（源码模式：仓库根；打包模式：`%APPDATA%/ZCodeTokensCard/state.json`）
**关联决策**：无

### 一句话定位

窗口几何等运行状态的唯一读写口；读失败返回空、写失败静默（配置非关键路径）。

### 行为预期（可验证，已逐条核实代码）

1. **路径按形态分流**：源码模式 = 仓库根 `state.json`；打包（`sys.frozen`）模式 = `%APPDATA%/ZCodeTokensCard/state.json`（父目录自动创建，APPDATA 缺失退回 `~/`）。出处：`config.py:config_path`（`tests/test_config.py` 锁住）。
2. **读写容错**：`load` 对缺失/损坏 JSON 返回 `{}`；`save` 增量合并不覆盖既有键、写失败静默不抛。出处：`config.py:load/save`（`tests/test_config.py` 锁住）。
3. **本文件是唯一落盘点**：窗口位置（`pos_x`/`pos_y`）与套餐页的界面配置 key（`quota_api_key`，空串 = 自动发现）都只写这里；`state.json` 已在 `.gitignore` 内，**密钥不入开源仓库**。出处：`.gitignore`、`config_window.py:save_configured`（`tests/test_config_window.py::test_save_persists_and_emits` 等锁住）。
4. **写失败不谎报**：`config.save` 对写失败静默（既有约定，配置非关键路径），故配置窗口在 `save` 后**回读校验**，不一致时窗口内红字提示且不关闭、不发保存信号（`save_configured` 返回 False）。出处：`config_window.py:save_configured`（`tests/test_config_window.py::test_save_failure_is_reported_not_faked` 锁住）。

### 反直觉/易误解（踩坑预警）

- **打包模式的程序目录不可靠**：onefile exe 每次运行解压到临时目录，状态必须放 APPDATA，否则窗口位置重启即丢。

---

## 开机自启动（autostart.py）

**主代码**：`autostart.py`（托盘入口在 `main.py:_toggle_autostart`）
**模型/数据**：注册表 `HKCU\...\CurrentVersion\Run` 的 `ZCodeTokensCard` 条目（仅当前用户，无需管理员）
**关联决策**：无

### 一句话定位

托盘"开机自启动"勾选项的注册表读写；只操作本程序专属条目，不碰其他程序的 Run 记录。

### 行为预期（可验证，已逐条核实代码）

1. **勾选即写、取消即删**：enable 覆盖写入 `REG_SZ` 启动命令（源码模式 `pythonw.exe main.py`，打包模式 exe 自身，路径均带引号）；disable 删除条目，未开启时幂等通过。出处：`autostart.py`（`tests/test_autostart.py` 锁住；真实注册表写入/回读/删除已于 2026-09-15 人工验证）。
2. **状态如实**：`is_enabled` = Run 键里存在 `ZCodeTokensCard` 条目；读取失败按未开启处理。出处：`autostart.py:is_enabled`。
3. **失败回弹**：注册表写/删抛 `OSError` 时，`main.py:_toggle_autostart` 回弹勾选并托盘气泡提示，不崩溃、不假成功。出处：`main.py:_toggle_autostart`。
4. **只动自己**：其他程序的 Run 条目不受任何影响。出处：固定值名 `_VALUE_NAME`（`tests/test_autostart.py::test_only_own_entry_touched` 锁住）。
5. **路径漂移自愈**：每次启动 `main.py` 调 `autostart.sync`——条目存在但指向与当前命令不一致时自动覆盖为新命令；条目不存在（用户未开启）或读取失败时保守不动，绝不擅自开启；修复失败静默不影响启动。出处：`autostart.py:sync`（`tests/test_autostart.py::test_sync_*` 锁住；真实注册表"伪造旧路径→sync→改回"已于 2026-09-15 实测）。

### 反直觉/易误解（踩坑预警）

- **移动 exe 无需手动处理**：Run 条目存的是静态路径，但程序启动时会自愈修正，"勾选显示开着却没自启"的窗口期只存在于 exe 挪位后到下一次启动之间。
- **手工改过 Run 命令会被覆盖**：自愈以"与程序生成的标准命令精确一致"为最新标准，若手动给 Run 条目加过自定义参数，下次启动会被覆盖回标准命令。

---

## 打包分发（PyInstaller）

**主代码**：`ZCodeTokensCard.spec`、`tools/make_icon.py`
**模型/数据**：无
**关联决策**：`docs/打包分发说明.md`（构建命令与对使用者说明）

### 一句话定位

把程序打成单文件 exe 供他人免安装使用；打包模式与源码模式共用业务代码，仅状态文件路径与自启动命令按 `sys.frozen` 分流。

### 行为预期（可验证，已逐条核实代码）

1. **单文件产物**：`python -m PyInstaller ZCodeTokensCard.spec --noconfirm --distpath dist --workpath build` 产出 `dist/ZCodeTokensCard.exe`（无控制台、带 Z 图标）；`build/`、`dist/` 不入库。出处：spec 文件、`.gitignore`。
2. **冻结态可启动**：exe 启动能完成 PySide6 全部导入（QtCore/QtGui/QtNetwork/QtWidgets）并执行单实例逻辑。2026-09-15 实测：已有实例运行时启动 exe，唤醒对方后自身退出码 0。

### 已知待修问题

- （暂无）

---

> 落地顺序建议：按真实模块逐条建立条目，优先建"改 A 易误伤 B"的核心模块（数据源读取、统计聚合口径、窗口渲染、配置持久化）。
