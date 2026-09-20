# Novel Studio v4.4.0 引擎静态审计报告 · CLI / Cruise / Pack / Cockpit / Exporter

- 审计对象：`engine/cli.py`、`engine/cruise.py`、`engine/pack.py`、`engine/cockpit.py`、`engine/exporter.py`
- 审计方式：五模块全文通读（read 工具全覆盖，无切片）+ 跨模块契约核对（ops/state/config/parser/check/ledger/errors/studio.py）+ 动态探针验证（TEMP 沙盒工作区，未触碰真实工作区、未修改任何引擎代码）
- 行数说明：任务描述给出的行数（719/267/516/204/197）与当前 checkout 实际行数不符。实际全文行数：**cli.py 810 / cruise.py 303 / pack.py 595 / cockpit.py 240 / exporter.py 231**。本报告按实际文件行号标注。
- 动态验证结论汇总：**1 项 L1、3 项 L2 已实锤复现**；其余标注 [需动态验证] 的为代码路径推导结论。

## 缺陷候选总览

| # | 级别 | 位置 | 一句话 |
|---|------|------|--------|
| 1 | **L1** | pack.py:191 | 标量形态 `present_characters: p_001` 被逐字符遍历，产出幻影人物档案（已复现） |
| 2 | L2 | pack.py:352/424 | `state_deltas: null` → AttributeError 逃逸成 exit 4（已复现） |
| 3 | L2 | cockpit.py:184/190（+pack.py:304） | relations 表字符串型数值 → TypeError 大盘崩溃 exit 4（已复现） |
| 4 | L2 | cruise.py:225-228 | `--poll 0`（或负值）→ 等待循环死飞，超时安全网失效（已复现） |
| 5 | L2 | cli.py:162-163 | 全局 `-w`/`--json` 置于子命令前被子解析器默认值静默覆盖 → 可对错误工作区执行写命令（已复现） |
| 6 | L3 | cli.py:555-557 | `status --json` 被接受但完全忽略，输出人读大盘且 exit 0（已复现） |
| 7 | L3 | cli.py:177 | `check chXX` 垃圾章号走业务阻断 exit 1，应为参数错误 exit 2（已复现 exit 1） |
| 8 | L3 | cli.py:399/422 | 未建档工作区下"缺子命令"先撞 exit 1 工作区阻断，契约上应为 exit 2 |
| 9 | L3 | cli.py:103 | `_resolve_workspace` 兜底回落 cwd → 可在代码仓库根误定位/误 init |
| 10 | L3 | cli.py 全域 | KeyboardInterrupt（Ctrl-C）无兜底 → 裸 traceback + exit 1 逃逸 |
| 11 | L3 | cli.py:551 | 巡航报告 JSON 截断 1500 字符，stdout 不可机读 |
| 12 | L3 | cli.py:1 | 文件头版本 v4.2.2、"30 命令"与 `__version__=4.4.0`、help 实列 32 条漂移 |
| 13 | L3 | cruise.py:252-256 | human_gate 计数按"章号距离"而非"本批实巡章数"，start_ch 跳跃时误触发且条数播报错误 |
| 14 | L3 | cruise.py:144 | 心跳"累计 N 章"用章号而非章节计数，多卷连续编号工作区失真 |
| 15 | L3 | cruise.py:61-65/115-118 | 卷末章标题含未填槽位即被剔除；全槽位卷纲报"未找到 ### ch_XXX 标题行"属误导（已复现误导文案） |
| 16 | L3 | cruise.py:284-289 | 卷已封存完毕后再次 cruise 会重跑 rollup/reconcile/export 刹车链（报告被重写） |
| 17 | L3 | cruise.py:163-167 | GuardError 重入账路径每章自动建快照 zip，无人值守下快照堆积 |
| 18 | L3 | pack.py:191-201 | present_characters 中数字/嵌套条目被静默丢弃；flow-list 数字解析为字符串 ID → 幻影 id "123" |
| 19 | L3 | pack.py:134/410 | `cfg.get("protagonist")` 永远取不到值（load_config 不含该键），持有人匹配退化为字面 "主角"/"p_001" 子串，存在误命中 |
| 20 | L3 | pack.py:483/cli.py:491 | token_cap 双次 load_config；手改 project.json 非法 token_cap → ValueError  exit 1（标"参数校验"而非系统故障 4） |
| 21 | L3 | cockpit.py:28-30 | `_s()` 空串击败默认值 → 新书大盘"时空/地点"渲染为空白而非兜底文案（已复现） |
| 22 | L3 | cockpit.py:225-228 | milestones.json 非 list（dict/字符串条目）→ TypeError exit 4 [需动态验证] |
| 23 | L3 | cockpit.py:216 | transactions[].delta 为字符串 → f-string `:+` 格式化 ValueError exit 4 [需动态验证] |
| 24 | L3 | exporter.py:150-157 | `--vol` 单卷导出永远拿不到前情提要（_prior 在已过滤的 vol_dirs 上首项即 break） |

---

## 详细候选缺陷

### [SEVERITY: L1] pack.py:191 — 标量形态 present_characters 被逐字符遍历，静默污染自完备装配包

- **文件:行号**：`engine/pack.py:191`（`for _c in (frontmatter.get("present_characters") or []):`）
- **问题描述**：v4.2.2 缺陷#20 的修复只覆盖了"列表内的字符串条目"这一种紧凑形态。当作者按自然 YAML 写法把**整个字段写成标量**（`present_characters: p_001`，不带方括号）时，`parse_mini_yaml` → `_parse_scalar` 原样返回字符串 `"p_001"`（parser.py:118-158），pack 的 `for _c in <str>` 遂按**单字符**迭代。对比：`engine/ops.py:1517`（evidence candidates）用 `[raw_pc] if isinstance(raw_pc, (str, dict)) else ...` 正确包裹了标量整值，pack 漏掉了这层归一化。
- **触发场景**：任何只有一个在场人物的章节（独戏章极常见）写成 `present_characters: p_001`。**已动态实锤**：沙盒工作区以此形态跑 `pack ch_001 --write`，exit 0、状态 🟢 预算健康，但 pack.md 生成 5 条幻影档案 `#### [p] p (supporting)`、`#### [_] _`、`#### [0] 0`、`#### [0] 0`、`#### [1] 1`，真正的主角全息档案（Want/Fear/人物卡/称谓矩阵）全部丢失；下游恩怨/关系/历史交集匹配的 `in_scene_names` 也退化为 `{'p','_','0','1'}`。Drafter 的"唯一事实源"被静默污染且全程 exit 0，无任何旗标。
- **建议修法**：与 ops.py:1517 对齐——迭代前先归一化整值：`_raw_pc = frontmatter.get("present_characters") or []; _pc_list = [_raw_pc] if isinstance(_raw_pc, (str, dict)) else (_raw_pc if isinstance(_raw_pc, list) else [])`，再对列表逐项做现有的 str/dict 归一；数字/嵌套/non-str-non-dict 条目跳过时记入 pack 返回值的 `warnings`，至少让 CLI 回执可见。

### [SEVERITY: L2] pack.py:352/424 — `state_deltas: null` 触发 AttributeError，逃逸成退出码 4

- **文件:行号**：`engine/pack.py:352` 与 `engine/pack.py:424`（`frontmatter.get("state_deltas", {}).get("items")`）
- **问题描述**：`.get("state_deltas", {})` 的默认值只在**键缺失**时生效；键存在且值为 `null`（YAML `state_deltas: null` → `_parse_scalar` 返回 None，parser.py:130-131）时返回 None，`.get("items")` 抛 AttributeError。同函数内 `epistemology`（pack.py:442）用的是 `frontmatter.get("epistemology") or {}`，写法正确且不一致。
- **触发场景**：作者在细纲 frontmatter 写 `state_deltas:` 后接 null，或 delete 掉整个 state_deltas 块后留 `state_deltas: null`。**已动态实锤**：exit 4「💥 未预期异常 AttributeError: 'NoneType' object has no attribute 'get'」。这是可恢复的作者数据问题，却按"系统级故障"上报，误导调用方去 snapshot rollback。
- **建议修法**：改为 `(frontmatter.get("state_deltas") or {})`，并对非 dict 的 state_deltas 视同空表（或抛 BusinessError 给出细纳闷诊文案，走 exit 1）。

### [SEVERITY: L2] cockpit.py:184/190（+ pack.py:304-305）— relations 表字符串型数值令大盘/装配包双双 TypeError

- **文件:行号**：`engine/cockpit.py:184`（`(r.get("tension") or 0) >= 30`）、`engine/cockpit.py:190-191`（`aff > 0`）；同类路径 `engine/pack.py:304-305`
- **问题描述**：tension/affinity 未做数值归一化。`"55" or 0` → `"55"`，`"55" >= 30` 直接 TypeError。cockpit 的 active_lines 等其他字段都做了 `or 0`/`_s` 防护，唯独关系温标没有。
- **触发场景**：relations.json 由 LLM/手工写入时数值带引号（极常见），或从外部工具导入。**已动态实锤**：`"tension": "55"` → `cockpit` exit 4 TypeError: '>=' not supported between instances of 'str' and 'int'。pack 的 `aff > 0` 同理会把打包路径一起打挂。
- **建议修法**： cockpit/pack 读取处加 `_num(v, default)` 归一化助手（`float(str(v))` 失败回落默认值）；或在 `StateManager.get_relations()` 单一出口做类型清洗，与 schema 契约对齐。

### [SEVERITY: L2] cruise.py:225-228 — `--poll 0`（或负值）令等待循环死飞，超时安全网整体失效

- **文件:行号**：`engine/cruise.py:225-228`（`while draft is None and waited < wait_timeout: time.sleep(poll_seconds); waited += poll_seconds`）
- **问题描述**：`waited` 只按 `poll_seconds` 累加，poll=0 时 waited 恒为 0，等待永不超时；poll<0 时 waited 单调递减同样永不超时。poll=0 还是 CPU 忙等（sleep(0)）。
- **触发场景**：`python studio.py cruise --poll 0 -w <ws>`（用户想"尽快轮询"的自然输入）。**已动态实锤**：配置 `cruise_wait_timeout=3` 后仍挂起 15 秒被强杀，超时从未触发。无人值守巡航的"单章等待超时刹车"这一核心安全带被一个参数静默拆掉，作者夜里跑巡航会永久挂起。
- **建议修法**：入口校验 `--poll` 必须 > 0（argparse type 钩子或 `run_cruise` 内 `max(0.1, float(poll_seconds))`）；`waited` 改为按墙钟计时（`time.monotonic()` 差值），使轮询间隔与超时判定解耦。

### [SEVERITY: L2] cli.py:162-163 — 全局 `-w`/`--json` 置于子命令前时被子解析器默认值静默覆盖

- **文件:行号**：`engine/cli.py:162-163`（顶层 `-w`/`--json` 定义）+ 全部子解析器各自的 `-w`/`--json` 重定义（如 178-179、183 等）
- **问题描述**：argparse 的子解析器动作会把**自己的默认值**写回主 namespace，覆盖主解析器已解析出的同名值。由于每个子命令都重新定义了 `-w`，`python studio.py -w <ws> <cmd>` 的 `-w` 被 `None` 覆盖，工作区定位静默回落到 cwd 推断。`--json` 同理（check/help/status 各有自己的 `--json`）。
- **触发场景**：**已动态实锤两例**：(a) `studio.py -w <沙盒ws> cockpit`（从仓库根执行）→ -w 被吞，撞"多书工作区"exit 2，而 `cockpit -w <ws>` 正常 exit 0；(b) `studio.py --json help` → 输出人读文本，而 `help --json` 输出合法 JSON。**真正危险的是写命令**：作者在书 A 目录内执行 `studio.py -w bookB proposal auto ch_010`，proposal_auto 会**反向回填细纲**（ops.py:1083-1085）——命令静默作用在书 A 上，属跨书数据误写风险；finalize/audit --write/sync --force/init --force 同理。
- **建议修法**：二选一——(1) 删掉顶层重复的 `-w`/`--json`，只在子命令保留（help 契约本就把 `-w` 写在子命令位）；或 (2) 解析后用 `args.workspace or 子命令 workspace` 合并，并在顶层 help 明示位置。同时给多书/未建档场景加"目标工作区"回显，让误定位可见。

### [SEVERITY: L3] cli.py:555-557 — `status --json` 被接受但完全忽略

- **问题描述**：`p_stat.add_argument("--json", ...)` 注册了参数，实现分支直接 `print(render_cockpit(ws))` 人读渲染。调用方按 `--json` 契约解析 stdout 会拿到非 JSON。
- **触发场景**：`python studio.py status --json` → exit 0 + 人读大盘。**已动态实锤**（输出首行是 `====`）。契约缺口在于顶层 `--json` 帮助文案承诺"以 JSON 格式输出"。
- **建议修法**：要么实现 status 的结构化 JSON（可复用 ops.get_cockpit 的 dict），要么移除该子命令的 `--json` 定义交还 argparse 报 exit 2。

### [SEVERITY: L3] cli.py:177 — `check` 位置参数缺章号格式钩子，垃圾章号走 exit 1

- **问题描述**：`check` 的 `chapter_id` 是裸 `nargs="?"`，无 `type=_chapter_num_arg`；`milestone add --target-ch`（cli.py:269）已用该钩子。非法章号被当业务错误。
- **触发场景**：`studio.py check chXX` → exit 1（业务阻断）；按退出码铁律，参数语法错误应为 2。**已动态实锤 exit 1**。
- **建议修法**：给 `check` 位置参数加格式校验钩子（注意要放行空串），或在 check 分支对非法 chapter_id 显式 `parser.error()`。

### [SEVERITY: L3] cli.py:399/422 — 未建档工作区下"缺子命令"报错顺序颠倒

- **问题描述**：`project.json` 存在性检查（399-408，exit 1）排在 PARENT_COMMANDS 缺子命令检查（422-430，exit 2）之前。未建档工作区执行 `studio.py beats` 会先吐"工作区未建档" exit 1，而语法契约上缺子命令应先报 exit 2。
- **建议修法**：把 PARENT_COMMANDS 校验移到工作区解析之前（argparse 语法层先行）。

### [SEVERITY: L3] cli.py:103 — `_resolve_workspace` 兜底回落 cwd，可在代码仓库根误定位

- **问题描述**：`workspace/` 不存在时返回 cwd。在仓库根执行任意命令时 ws=仓库根，随后的"未建档"提示会引导用户在仓库根 init，污染代码仓库。
- **建议修法**：兜底改为返回 `cwd/workspace`（即便不存在），保持"书在 workspace/ 下"的不变式；或显式报"未找到 workspace 目录"。

### [SEVERITY: L3] cli.py 全域 — KeyboardInterrupt 无兜底，裸 traceback + exit 1 逃逸

- **问题描述**：`except (BusinessError, ..., KeyError)` / `except RuntimeError` / `except Exception` 均不捕获 BaseException。巡航等待/长校验中 Ctrl-C → KeyboardInterrupt 穿透 main，打印 traceback、退出码 1（与业务阻断同码）。
- **触发场景**：无人值守巡航中人工 Ctrl-C。应给出"已安全停机"人话盒（可约定 exit 130 或 4）。
- **建议修法**：main 外层（或 studio.py）加 `except KeyboardInterrupt` → 人话提示 + `SystemExit(130)`。

### [SEVERITY: L3] cli.py:551 — 巡航批次报告 JSON 截断 1500 字符

- **问题描述**：`print(json.dumps(report)[:1500])` 截断后的字符串不构成合法 JSON，日志采集方若按 JSON 解析直接失败；且截断可能正好切在 results 中间，丢失 brake/timeout 关键行。
- **建议修法**：`--json` 通道完整输出（或落盘 report JSON 到 log/ 并打印路径）；人读通道保留单行心跳即可。

### [SEVERITY: L3] cli.py:1 — 文件头版本/命令数漂移

- **问题描述**：docstring 标注 v4.2.2、"核心连载闭环命令（30）"；实际 `__version__` 4.4.0、help 契约 32 条命令。
- **建议修法**：版本号改引用 `__version__`，命令计数由 help 表长度派生，杜绝手抄漂移。

### [SEVERITY: L3] cruise.py:252-256 — human_gate 计数按章号距离，start_ch 跳跃时误触发

- **问题描述**：门条件 `(sealed_total - batch_start) % gate_every == 0`，而 `sealed_total` 是**章号**（初值 = `plan["sealed_now"]` = 最后封存章号），batch_start 同源。正常续巡时"章号差=实巡章数"；但 `start_ch` 跳段启动（如已封存至 ch_005、`start_ch=ch_010`、gate_every=5）时，封存第 1 章即 `10-5=5` 触发 gate，且播报"已巡 5 章"（实际 1 章）。
- **建议修法**：维护独立的本批计数器 `batch_count += 1`，门条件用 `batch_count % gate_every == 0`，播报同源。

### [SEVERITY: L3] cruise.py:144 — 心跳"累计 N 章"在多卷连续编号下失真

- **问题描述**：心跳与 `sealed_total` 初值都用章号（vol_02 起章即 21+）。vol_02 仅封存 1 章时心跳即显示"累计 21 章"。而 batch_report 的 `sealed_total` 用的是 `len(sealed_list)`（卷内实计数），同一份报告里两套口径并存。
- **建议修法**：心跳累计改为 `len(_sealed_chapters(...))` 全书口径或卷内计数，全链路统一。

### [SEVERITY: L3] cruise.py:61-65/115-118 — 卷末章槽位剔除过宽 + 误导性报错

- **问题描述**：`_volume_last_chapter` 把含 `{{slot:` 的标题行整行剔除（v4.3 C13 的意图是排除纯占位章）。副作用一：末章标题已填但正文仍有其他槽位时，末章被误剔，卷末钳位提前。副作用二：**新初始化工作区**卷纲全部是 `### ch_001: {{slot:...}}` 形态，cruise 直接报"未找到任何 '### ch_XXX' 标题行"——**已动态实锤**该误导文案（文件里明明有标题行，只是都带槽位）。
- **建议修法**：剔除判据改为"该行去除 slot 后无实质内容"；报错文案区分"大纲不存在"与"大纲章节行均为未填槽位态，请先派 Stage 0E 填实卷纲"。

### [SEVERITY: L3] cruise.py:284-289 — 卷已完结后重复 cruise 会重跑刹车链

- **问题描述**：`reached_end` 判定 `goal >= m_last 且 ch_goal 已封存`。全书已封存后再跑 `cruise`（planned 为空）依然命中 reached_end，重跑 `rollup_volume` + `reconcile --write` + `export_book`，对账报告/rollup JSON/成书文件被无变化重写，时间戳全部刷新。
- **建议修法**：`reached_end` 增加"本批实际新封存了卷末章"条件（或检查 rollup 归档时间戳跳过未变更卷）。

### [SEVERITY: L3] cruise.py:163-167 — GuardError 强制重入账路径每章自动快照，无人值守下堆积

- **问题描述**：正文变化未 --force 时先 `snapshot_create(f"pre_force_sync_{chapter_id}")` 再 force 重入账。巡航中若每章都被修订过，snapshots/ 目录按章增长 zip（workspace/testbook 环境每次同步整包）。
- **建议修法**：批次级快照（每批次一个 `pre_force_sync_batch_<vol>`）或带保留上限的滚动清理，并在心跳里播报快照动作。

### [SEVERITY: L3] pack.py:191-201 — 数字/嵌套 present_characters 条目静默丢弃

- **问题描述**：归一化只认 str/dict；None、数字、嵌套 list 条目被 `elif` 双双落空后无痕跳过。另：flow-list（`[p_001, 123]`）解析时数字不走 `_parse_scalar`（parser.py:156），保留字符串 "123"，进入 persons_db.get("123") → 幻影档案 `[123] 123`。
- **建议修法**：非 str/dict 条目记 warning；flow-list 解析数字条目归一为字符串 ID 前先校验 ID 形态（`^[a-z]+_\d+$`），不合形即警告丢弃。

### [SEVERITY: L3] pack.py:134/410 — protagonist 取自 load_config 属死取值，持有匹配误命中

- **问题描述**：`cfg.get("protagonist", "主角")` —— `load_config` 只合并 DEFAULT_CONFIG 白名单键（config.py:85-87），永不含 project.json 顶层的 protagonist，该取值恒为 "主角"。pack.py:410 的子串匹配 `any(k in h for k in (protagonist, "主角", "p_001"))` 中 "主角" 字面量恒在，导致持有人名含"主角"子串（如绰号"主角光环"式命名）或含 "p_001" 子串的任意字符串都会误判为在场主角装备。
- **建议修法**：protagonist 直接读 `project.json`（与 ops.py:331 一致）；匹配改精确集合命中，去掉宽泛子串。

### [SEVERITY: L3] pack.py:483 / cli.py:491 — token_cap 双源双读；非法值定级错位

- **问题描述**：build_pack 内 `int(load_config(...).get("token_cap", 15000))`，CLI 回执又 load 一次。手改 project.json 使 `engine.token_cap = "abc"` 时 int() ValueError → CLI 按"参数/格式校验阻断"exit 1；属配置文件损坏，应 exit 4（config.py 对 project.json 损坏本身是抛 RuntimeError→4 的，口径不一）。
- **建议修法**：load_config 内对引擎旋钮做类型校验，非法即 RuntimeError（与 _read_project 一致）；pack 与 CLI 复用同一 cfg 对象。

### [SEVERITY: L3] cockpit.py:28-30 — `_s()` 空串击败默认值

- **问题描述**：`_s(v, default)` 仅在 v is None 时回落；init 写入的 `last_timeline/last_location` 是空串（ops.py:234-235），空串 `str()` 后原样输出。**已动态实锤**：新书大盘渲染"⏱️ 当前现场： 时空： ｜ 地点："（空白而非"开局第一现场/初始场景"）。
- **建议修法**：`_s` 改为 `str(v) if v not in (None, "") else default`（或调用侧 `or` 链）。

### [SEVERITY: L3] cockpit.py:225-228 — milestones.json 非 list 时大盘崩溃

- **问题描述**：`ms_list = json.load(f)` 未校验类型；若为 dict（如误写成对象映射），`ms_list[:5]` TypeError；若 list 条目为裸字符串，`m.get` AttributeError。均逃逸成 exit 4。
- **建议修法**：加载后 `if not isinstance(ms_list, list): ms_list = []` 并 warning；条目非 dict 跳过。同类风险见 cockpit.py:216（`tx.get('delta', 0):+` 遇字符串 ValueError）、cockpit.py:210（pools 值非数值时仅展示尚可，但若参与未来计算同样危险）——建议统一数值清洗出口。

### [SEVERITY: L3] exporter.py:150-157 — `--vol` 单卷导出永远没有前情提要

- **问题描述**：`_prior` 在**已被 volume_id 过滤后的 vol_dirs** 上循环，首项即目标卷 → 立即 break → `_prior` 恒空 → `digest` 恒空。与 BUG#41"前情提要回顾前序各卷"的设计意图在单卷导出模式下完全失效（vol_02 存在 vol_01 已封存章节时，`export --vol vol_02` 读者仍拿不到任何前情）。
- **建议修法**：`_prior` 改为对**未过滤**的全部卷目录计算（或在函数入口先算 `all_vol_dirs` 再过滤导出集）。

---

## 经审计确认符合契约的要点（无缺陷）

1. **退出码映射主链路正确**：BusinessError/GuardError→1（cli.py:739-779）；argparse 语法错误→2（`_StudioArgumentParser.error` + 缺子命令 + 多书未指定 -w，均已动态实锤 exit 2）；环境依赖→3（studio.py import 期兜底 SyntaxError/ImportError）；RuntimeError→4；未预期异常→4 且**输出人话盒而非裸 traceback**。无"exit 0 但实际失败"路径（check passed=False→1、cruise brake/timeout→1、export 空 final→1、plan 失败→BusinessError→1 均已实锤）。
2. **pack P0 刚性保护成立**：四级修剪只动 P2（世界观/战力/梗概）与 P1（人物卡切片/历史交集/接戏尾），细纲正文、认知禁令（epistemology）、法定事实（locked facts）零裁剪；四级后仍超限输出 🔴 显式旗标与超出 Token 数（pack.py:564-567），无静默截断。token_cap 来源为 `load_config().get("token_cap", 15000)` 配置中心单一来源。
3. **紧凑 present_characters 列表形态归一化生效**（v4.2.2 缺陷#20 修复经动态验证有效：`[p_001, p_002]` → 两条完整档案）；缺陷仅剩"整值标量"未覆盖（见 L1 #1）。
4. **cruise 刹车链顺序正确**：卷末 rollup → reconcile --write → export（cruise.py:286-288）；check errors>0 立即 brake 不带伤入账；异常章（GuardError/BusinessError）停机而非跳过；等待超时标记 timeout 并由 CLI 映射 exit 1（v4.3 修复有效）；批次上限 `max_chapters` 钳制与 `min(target, 卷末)` 语义正确，且卷末刹车只在**本批真正封存到卷末章**时触发（`_chapter_id(goal) in sealed_list`），不会被批次钳制误触发；哨兵"引擎消费即删"（`gate.unlink(missing_ok=True)`）防同批次二次直通。
5. **exporter 只读保证成立**：只读 `manuscript/*/final` 与 `state/sync_log.json`、`state/synopsis.json`、`project.json`，唯一写目标是 `workspace/export/`；无任何反向写台账代码；未入账 final 裸文件被点名跳过（unsealed_chapters）；空 final 目录 → BusinessError exit 1 带排错方案；字数统一引用 sync_log 入账值（v4.4.0 BUG#35 单真值）；标题规范化不再吞正文首行（BUG#A1）。
6. **cockpit 字数来源合规**：总字数/节奏曲线取自 `state/timeline.json` 的 `word_count`，由 sync 时 `count_prose_words`（剥 front-matter 与 Markdown 标题行后的 Python 实测净字数）写入，非 LLM 口径；除零/空列表/None 主体防护到位（`words else 0`、`relations` 非 dict 跳过、`_s()` None 安全），仅剩数值型/空串/容器型边角（见 L3 各项）。
7. **help --json 契约**：help 表 32 条命令与 argparse 子命令一一对应，无"承诺了但不支持"的参数（style --last 已显式标注失效；cruise 的 --target/--once/--poll/--vol 属未文档化但已支持，反向无害）。

## 动态验证记录（沙盒 TEMP 工作区，未触碰真实工作区）

| 探针 | 命令/构造 | 结果 |
|------|-----------|------|
| L1 #1 | beats `present_characters: p_001` + `pack ch_001 --write` | exit 0，pack.md 5 条幻影档案（[p]/[_]/[0]/[0]/[1]） |
| #6 | `status --json` | exit 0，人读大盘 |
| #7 | `check chXX` | exit 1 |
| #5 | `-w <ws> cockpit` vs `cockpit -w <ws>` | 前者 exit 2（-w 被吞），后者 exit 0 |
| #5 | `--json help` vs `help --json` | 前者人读文本，后者合法 JSON |
| #2 | beats `state_deltas: null` + pack | exit 4 AttributeError |
| #3 | relations.json `"tension": "55"` + cockpit | exit 4 TypeError |
| #4 | `config set cruise_wait_timeout 3` + `cruise --poll 0` | 挂起 15s 被强杀，超时未触发 |
| #15 | 新 init 工作区 + `cruise --once` | exit 1，"未找到任何 ### ch_XXX 标题行"（误导文案） |
| #21 | 新 init 工作区 + cockpit | "时空/地点"空白而非兜底默认值 |
| 正向 | `check --json` + 损坏 project.json | stdout 合法 JSON、exit 1（check 对坏表自包容） |
| 正向 | argplane 未知子命令 / 多书无 -w / --version | exit 2 / exit 2 / exit 0 |
| 正向 | compact list `present_characters: [p_001, p_002]` | 两条完整档案，归一化生效 |
