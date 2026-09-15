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
| `fetch_session_usage` | 单会话全部用量合计（当前对话行） |
| `fetch_latest_session` / `fetch_session_title` | 库内最近活跃会话与标题（当前对话主信号） |

### 行为预期（可验证，已逐条核实代码）

1. **连接只读**：`open_ro` 用 URI `?mode=ro` 打开，任何写入抛 OperationalError。出处：`reader.py:open_ro`（`tests/test_reader.py::test_open_ro_blocks_writes` 锁住）。
2. **今日口径**：查询按 `started_at >= 今日0点(本地毫秒)` 过滤，昨日数据不进入统计。出处：`reader.py:fetch_*`（`tests/test_reader.py::test_fetch_day_rows_excludes_yesterday` 锁住）。
3. **模型 TOP3**：`fetch_top_models` 按当日总量倒序取前三，不足三个按实际数量返回。出处：`reader.py:fetch_top_models`。
4. **会话用量全期合计**：`fetch_session_usage` 不按天过滤，返回该会话 (总计,输入,输出,缓存) 四元组；无记录返回全 0。出处：`reader.py:fetch_session_usage`（`tests/test_reader.py::test_fetch_session_usage*` 锁住）。
5. **最近活跃会话**：`fetch_latest_session` 按 `session.time_updated` 倒序取第一；无会话返回 None。出处：`reader.py:fetch_latest_session`（`tests/test_reader.py::test_fetch_latest_session*` 锁住）。

### 反直觉/易误解（踩坑预警）

- **started_at 是毫秒时间戳**：比较基准必须用 `stats.today_start_ms()` 的毫秒值；传秒值会静默查不到数据。
- **computed_total 已含缓存读取**：`input_tokens` 本身包含 cache_read，`computed_total = input + output`，不要把缓存列再加一遍。

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

324×246 窗体（296×218 内容 + 四周投影边距）纸感浅色无边框置顶横卡的全部视觉呈现：QPainter 自绘布局、数值摊放补间、增量飘字、占比条与呼吸灯动画、底部当前对话行、拖动交互。

### 行为预期（可验证，已逐条核实代码）

1. **皮肤为纸感浅色**（选型稿 `design/皮肤总览.html` 01 号）：暖白纸底 `#fdfcf9`、细灰线描边、橙色强调、四周落地柔影；窗口比卡片大一圈（四周 14px 透明边距画投影），色值一律取自 `theme.py`，布局坐标常量集中在 `card.py` 顶部。出处：`card.py:_draw_card/_draw_shadow`、`theme.py`。
2. **窗体 296×218**（含投影边距 324×246）：默认落位主屏右下角（任务栏上方，右边距 20、底边距 14），用户拖动后位置写入 `state.json` 并按原位恢复。出处：`main.py:_restore_pos`。
3. **增量摊放**：每轮轮询到账的增量进 `drip` 池，按其产生间隔、1~3s 一跳分步释放为显示值（单段封顶 10 分钟）；显示全程 ≤ 真实值，到账停止后追平；首帧直接显示真实值不摊放；当日累计回退（跨零点/上游修正）时清池并立即对齐新一天真实值，旧量不再放出。出处：`card.py:set_data/_drip`、`drip.py`（`tests/test_stream.py` 锁住）。
4. **增量飘字**：摊放调度每释放一跳，大数字右侧与三列右侧各自冒出「+释放量」上浮淡出；首帧与零释放时不飘。出处：`card.py:_drip/_draw_rise`。
5. **三列完整数字**：输入/输出/缓存显示千分位完整数字（左对齐、无中文单位），缓存行占比小字紧跟数字右侧（`FS_PCT`）；标签列贴近竖分隔线（x=148），数值左对齐区 176~278（亿级 11 位数+占比不溢出）。出处：`card.py:_draw_main`、`stats.py:full`。
6. **占比条**：宽度按当日总量归一平滑过渡，最小 2%；条区 132~210，模型数值右对齐至 282，互不重叠；不足三个模型时多余行不渲染。出处：`card.py:_bar_targets/_draw_models`。
7. **拖动**：左键拖动移动窗口，松开后位置写入 `state.json`。出处：`card.py:mouse*Event`。
8. **异常态独立配色**：数据源异常时呼吸灯与状态文字变红橙 `C_ERROR`，与第三模型蓝色区分；异常期间摊放池与显示保持不动。出处：`card.py:_draw_top/set_error`。
9. **顶行日期与时钟**：标签为「M月D日 周X + 24 小时制 HH:MM」，每帧按当前时间生成——跨零点自动换日、时钟每秒刷新。出处：`card.py:_draw_top`。
10. **底部当前对话行**（y=180 分隔线 + 行中心 198）：左侧会话标题（省略号截断,吃行首剩余宽度），右侧「N（P%）」——N 为该会话全部总计走 `stats.cny`（只出现万/亿与千分位整数），P = 缓存÷总计取整百分比，total 为 0 时 P 显示 0；不显示冒号或"总"等标签字；字号 `FS_CUR`(11px)；【反向约束】这行数字不走 drip 池、无飘字/补间，`set_data` 每轮整值直显真实汇总（`cur` 不在 `TWEEN_KEYS`）；无会话数据时整行不画。出处：`card.py:_draw_cur/set_data`（`tests/test_card_cur.py` 锁住，含"不进池"反向测试与"当日数字照常进池"正向对照）。

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
4. **轮询装配当前会话**：每轮轮询追加固定 3 条查询（最近活跃会话、会话标题、会话用量）+ 一次 leveldb 扫描，查询条数不随 `model_usage` 行数增长；装配结果经 `current.SessionResolver` 裁决后交给 `card.set_data` 的 `cur` 字段。出处：`main.py:_current_session`（`tests/test_current.py` 裁决行为锁住）。
5. **托盘菜单四项**：跟随显示、开机自启动、显示/隐藏、退出；自启动勾选状态初始化自注册表现状（先设状态后连信号，初始化不产生注册表写），勾选变化即写/删 Run 键，失败回弹勾选并托盘气泡提示。出处：`main.py` 托盘装配、`_toggle_autostart`。

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

### 反直觉/易误解（踩坑预警）

- **移动 exe 后需重新勾一次**：条目存在即视为"已开启"，exe 挪位置后旧命令失效，重新勾选一次即修复（enable 是覆盖写）。

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
