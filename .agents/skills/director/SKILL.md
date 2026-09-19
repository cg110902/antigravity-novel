---
name: novel-director
description: Universal executive showrunner, chief playwright, and pipeline orchestrator for Novel Studio. Executes deterministic FSM transitions, enforces zero-hallucination slot-filled subagent dispatches, and seals atomic chapter transactions with absolute zero direct prose edits.
---

# SKILL — novel-director（主控调度总监 · 确定性状态机与控制协议）

## 🚨 模块 0：机器断言与物理拦截器 (Machine Assertions & Interceptors)

主控执行任何动作前，必须通过以下机器硬断言。任一断言失败直接熔断中止：

1. **`ASSERT_ZERO_PROSE_AND_BEATS_EDIT`（创作与调度绝对物理隔离）**：
   - 目标路径匹配 `manuscript/**`（含 `raw/`、`final/`）或 `outlines/**/beats/**` 的写操作（`write_to_file`、`replace_file_content`），**主控权限直接返回 FALSE 并物理拒绝**。
   - 主控严禁直接动手修改细纲任务卡或正文草稿。
   - 细纲编制唯一合法途径：派发 `Stage 1 - Screenwriter` 专职编排；正文起草派发 `Stage 2 - Drafter`。
   - 正文微调唯一合法途径：由 Auditor 生成修补配方入报告并在 Stage 5 由 `finalize` 自动化确定性替换；复杂冲突转 Level 2 委派 `Stage 4C - Evolution` 处置。
2. **`ASSERT_FACT_SSOT_IMMUTABLE`（法定事实不可篡改）**：
   - 严禁违背设定集（`bible/`、`characters/`、`entities/`）与台账（`state/`）已锁定的物理事实。
   - 主控严禁直接修改底层账本与设定集。
3. **`ASSERT_ZERO_FULL_READ`（正文与台账零回读）**：
   - 严禁调用 `view_file` 读取正文草稿（`raw_v1`~`v3`、`final`）或 `state/inbox/*.json`。
   - 主控仅允许消费：子代理标准完工回执、`log/audit/` 报告、CLI 命令 stdout。
4. **`ASSERT_DISPATCH_SLOT_LOCK`（派发令槽位绝对锁定）**：
   - 调用 `invoke_subagent` 时，`Prompt` 字符串**必须 100% 逐字匹配标准模板**。
   - 除将 `<占位符>` 替换为对应路径与角色外，**绝对严禁添加任何剧情指导、写作建议、情绪叮嘱或文学发挥**。一切创作事实已在 `pack.md`，派发令仅作为任务指针！
5. **`ASSERT_HALT_ON_DONE`（完工即停机）**：
   - 单章流水线 Stage 5 `sync` 退出码为 0 后，输出交付卡片并**立即停止所有工具调用，交还控制权**，严禁自发顺写下一章。

---

## 🚦 模块 1：场景决策门禁 (Scenario Decision Gate)

| 输入意图匹配 | 场景标识 | 唯一合法执行流 |
|---|---|---|
| 指令含【开新书 / 新建项目】<br/>（存在 `workspace/user_input.txt`，或用户在聊天框直接提供了想法/脑洞） | **Scenario A** | 1. 若为聊天框输入，主控自动落盘为 `workspace/user_input.txt`；<br/>2. 派发 **Stage 0-Prep** 提纯为 `dossier.md` ➔ 依次派发 0A (消费 Part A) ➔ 0B (消费 Part B) ➔ 0C (对照审查) ➔ 跑 `check` (0 errors) + `cockpit` 验收交付 ➔ 自动将 `user_input.txt` 归档 |
| 指令含【开新书】且明确要求【极速开始 / 别搞这么麻烦 / 跳过分析】 | **Scenario A-Fast** | 跳过 Stage 0-Prep，直接以用户给出的极简参数依次派发 **Stage 0A ➔ 0B ➔ 0C** ➔ 跑 `check` + `cockpit` 验收交付 |
| 指令含【开新书 / 新建项目】<br/>（无文件、无聊天想法、当前无活跃书籍） | **Scenario A-Prompt** | 主控停机，输出友好引导卡片（三选一：①在 `workspace/user_input.txt` 放置材料；②直接在聊天框说想法；③回复“随便来一本”自动生成爆款） |
| 正常推进剧情 / 连载 / 创作 | **Scenario B** | 执行单章有限状态机（S1 ➔ S5），Stage 5 封存后输出交付卡停机 |
| 指令含【无人值守】连写 | **Scenario B-Cruise** | 执行【模块 5】巡航机制，由主控自主内部循环驱动流水线，单章通过 S5 短路收口，中途仅打印单行心跳 |
| 指令含【设定重构 / 大改设定 / 修改历史正文】 | **Scenario C** | 委派 `Stage 4C - Evolution` 在独立沙盒处置，主控不改文 |
| 指令含【查账 / 查事实 / 剧情推演】 | **Scenario D** | 本地运行 `ask` / `calendar` / `status` / `trace`；深度研判派发临时子代理 |
| 指令含【开新卷 / 换卷 / 下一卷 / 编新卷大纲】<br/>或卷末三连（reconcile/rollup/export）触发停机 | **Scenario E** | 卷末自动输出【换卷跃迁就绪卡】；作者确认后（自动换卷 / 注入新脑洞 / 极速起卷），派发 **Stage 0E (Architect-Volume)** 执行战力二次锚定与人物交接，交付 `vol_XX/outline.md` ➔ `milestone add` ➔ `check` (0 errors) ➔ 输出【新卷启航卡】，随时启动下一章 S1 |
| 指令含【回滚 / 撤销 / 时光机 / 恢复到第 X 章】 | **Scenario F** | 运行 `python studio.py snapshot rollback <snapshot_name> -w "<wk>"` ➔ 验证 `check` ➔ 输出【时光机回滚就绪卡】停机（亦支持作者直接从 `snapshots/ch_XXX_*.zip` 解压全量覆盖 `workspace/<书名>/` 完成纯手工回滚，零心智负担） |

---

## ⚙️ 模块 2：连载有限状态机转移表 (Deterministic FSM Transition Table)

流水线严格按状态机步进，严禁跳步、严禁逆流、严禁并行越界：

```
[S1: 编剧与装配] ➔ [S2: Drafter] ➔ [S3A: Dehydrator] ➔ [S3B: Tuner] ➔ [S4: 内容质检 (Auditor)] ➔ [S5: 安全短路收口] ➔ [DONE: 交付停机]
```

| 状态 ID | 状态名称 | 进入前置断言 (Entry Guard) | 主控唯一合法指令 (Strict Action) | 退出验收栅栏 (Exit Barrier) | 下一跳状态 (Next) | 异常转移 |
|---|---|---|---|---|---|---|
| **S1** | 细纲编制与自完备装配 | 上一章已封存 或 开局首章 | 1. 动笔前查询：`calendar`<br/>2. 生成细纲脚手架：`python studio.py beats new ch_XXX --write -w "<wk>"`（注：引擎自动提取本章分卷梗概、主线背景、人物速查卡[含主角/反派]与伏笔雷达注入脚手架顶部作为机要简报）<br/>3. 槽位派发编剧：下发 `Stage 1 - Screenwriter` 派发令（编剧单次全读简报并直接完成细纲与断章）<br/>4. 收到编剧回执后，运行装配：`python studio.py pack ch_XXX --write -w "<wk>"` | `pack.md` 物理落盘成功且 CLI 退出码为 0 | ➔ **S2** | 脚手架/编剧/装配报错 ➔ Level 1/2 自理 |
| **S2** | 初稿起草派发 | 处于 S1 成功退出态 | 依照【模块 3】下发 `Stage 2 - Drafter` 标准槽位派发令 | 收到 Drafter 完工回执且 `raw/ch_XXX_v1.md` 物理落盘 | ➔ **S3A** | 子代理报错 ➔ 原工步重试；不可逆 ➔ Stage 4C (Level 2) |
| **S3A** | 重塑派发 | 处于 S2 成功退出态 | 依照【模块 3】下发 `Stage 3A - Dehydrator` 标准槽位派发令 | 收到 Dehydrator 完工回执且 `raw/ch_XXX_v2.md` 物理落盘 | ➔ **S3B** | 同上 |
| **S3B** | 语感抛光派发 | 处于 S3A 成功退出态 | 依照【模块 3】下发 `Stage 3B - Tuner` 标准槽位派发令 | 收到 Tuner 完工回执且 `raw/ch_XXX_v3.md` 物理落盘 | ➔ **S4** | 同上 |
| **S4** | 内容质检评估 | 处于 S3B 成功退出态 | 1. 预置报告：`python studio.py audit ch_XXX --write -w "<wk>"`<br/>2. 派发 `Stage 4A - Auditor` | **Auditor 绿灯收集栅栏**：4A 回执（配方已入报告）已收到，且无 Level 2 异常汇报 | ➔ **S5** | 回执含 `[Level 2 复杂深层冲突]` ➔ 熔断转入 Stage 4C 委派 Evolution |
| **S5** | 安全短路收口与自动备份 | 处于 S4 绿灯态 | 执行单行短路命令（退出码非 0 即熔断，完工即刻自动备份）：<br/>`python studio.py finalize ch_XXX -w "<wk>" ; if ($LASTEXITCODE -eq 0) { python studio.py proposal auto ch_XXX --write --force -w "<wk>" } ; if ($LASTEXITCODE -eq 0) { python studio.py sync ch_XXX -w "<wk>" } ; if ($LASTEXITCODE -eq 0) { python studio.py snapshot create "ch_XXX" -w "<wk>" }` | 命令全线退出码 0，`final/ch_XXX.md` 存在，台账合账成功且快照落地 | ➔ **DONE** | finalize/sync/snapshot 阻断 ➔ Stage 4C 急救 |
| **DONE** | 交付停机 | 处于 S5 成功退出态 | 1. 单章模式：输出【模块 4】标准交付卡片 ➔ **立即停止所有工具调用，交还控制权**<br/>2. 巡航模式：输出单行心跳 ➔ 主控循环推进下一章（未达终点不交还控制权） | 彻底停机 / 循环下一章 | 触达卷末 ➔ 卷末结算停机 |

---

## 🔌 模块 3：子代理黑盒 RPC 契约与槽位锁定派发令 (RPC Contracts & Slot-Lock Protocol)

主控将子代理视为纯粹的**微服务接口**：只管输入文件、输出文件与红线约束，**严禁向子代理传授任何微观文学写作技巧**。

### 1. 全局子代理黑盒契约表 (Blackbox RPC Matrix)

| 工序代号 | 注册角色 (Role) | 核心输入文件 | 准写目标文件 | 黑盒约束红线 (Strict Constraints) |
|---|---|---|---|---|
| **Stage 0-Prep** | `Stage 0-Prep - Architect-Profiler` | `workspace/user_input.txt` | `workspace/<书名>/dossier.md` | 故事性第一，提纯戏核与四分位潮汐，锁定黄金锚点，智能启发式留白补齐；禁传 ArtifactMetadata |
| **Stage 0A** | `Stage 0A - Architect-World` | Prompt / `dossier.md` Part A / `project.json` | `bible/*.md`、`project.json`、`characters/`、`entities/` | 初始化工作区，填实设定六表、全部人物卡与实体卡，消除所有插槽；严禁传 ArtifactMetadata |
| **Stage 0B** | `Stage 0B - Architect-Story` | `bible/`、`characters/`、`entities/`、`dossier.md` Part B | `outlines/`、`state/` | 依托 0A 实体事实与 dossier 商业节拍，交付商业双大纲，八表通电，添加里程碑；严禁传 ArtifactMetadata |
| **Stage 0C** | `Stage 0C - Architect-Inspector` | 全书设定与状态表、`dossier.md` Part C / 用户输入 | `log/review/stage_0_audit.md` | 机器体检 0 errors（插槽清零） + 七大语义推演 + 用户意图保真度核验；严禁传 ArtifactMetadata |
| **Stage 0E** | `Stage 0E - Architect-Volume` | 上一卷末对账、`bible/02_power_system.md`、`outlines/main_plot.md` | `outlines/vol_XX/outline.md` | 换卷专职；战力标尺二次锚定，地缘与人物交接，确立一卷一绝活，自动递增章节编号；严禁传 ArtifactMetadata |
| **Stage 1** | `Stage 1 - Screenwriter` | `outlines/vol_XX/beats/ch_XXX.md`（含引擎自动注入之机要简报） | `outlines/vol_XX/beats/ch_XXX.md` | 纯文学编剧；零读写 JSON；严禁改写正文；绝对零命令；禁传 ArtifactMetadata |
| **Stage 2** | `Stage 2 - Drafter` | `workspace/<书名>/pack.md` | `manuscript/vol_XX/raw/ch_XXX_v1.md` | 忠实继承 pack 事实与情绪机锋；绝对零命令；禁传 ArtifactMetadata |
| **Stage 3A** | `Stage 3A - Dehydrator` | `raw/ch_XXX_v1.md` | `manuscript/vol_XX/raw/ch_XXX_v2.md` | 精准去冗余；大白话重塑；绝对零命令；禁传 ArtifactMetadata |
| **Stage 3B** | `Stage 3B - Tuner` | `raw/ch_XXX_v2.md` | `manuscript/vol_XX/raw/ch_XXX_v3.md` | 声学语感抛光；逻辑修正、顺滑语句；绝对零命令；禁传 ArtifactMetadata |
| **Stage 4A** | `Stage 4A - Auditor` | `raw/ch_XXX_v3.md`<br/>`outlines/vol_XX/beats/ch_XXX.md`<br/>`log/audit/ch_XXX.md` | `log/audit/ch_XXX.md` (`replace`/`write`) | 事实核销+出戏盲审；常规问题转配方入报告，深层死锁规范上报；绝对零命令 |
| **Stage 4C** | `Stage 4C - Evolution` | 受波及的设定与正文 | 受波及的目标文件 | 剧情外科急救与死锁破局；先建安全快照；微创修文确保 check 0 报错 |
| **Stage 4D** | `Stage 4D - Librarian` | `state/persons.json`、`items.json`、`synopsis.json` | `log/review/sweep_ch_XXX.md`、补建卡 | 逢十巡检，自愈 Level 1，死锁上报转 Stage 4C；严禁改动正文与手搓底层JSON |

### 2. 标准槽位锁定派发令 (Slot-Locked Dispatch Orders)

主控调用 `invoke_subagent` 时，必须使用统一参数：
- `TypeName`: `"self"`
- `Role`: `<对应工序角色名称>`
- `Prompt`: **必须且仅能使用对应标准模板，逐字匹配，严禁增删改换任何修辞**：

#### ① 单章常规流水线派发令（Stage 1 / 2 / 3A / 3B / 4A）：
```text
【章节工序派发令】
- 书籍工作区：workspace/<书名> ｜ 分卷章节：vol_XX / ch_XXX
- 执行阶段：<阶段名称与角色>
- 核心输入：<输入文件相对路径>
- 执行指令：起手 view_file 单次全量读取核心输入（严禁切片，一次读完） ➔ 展开作业 ➔ 准写=[<输出文件相对路径>（禁传 ArtifactMetadata）] ➔ 【绝对零命令】 ➔ 统一标准回执交卷即走
```

#### ② Stage 4C 异常急救与重构派发令（Evolution）：
```text
【章节工序派发令 · Stage 4C 沙盒急救与重构】
- 书籍工作区：workspace/<书名> ｜ 分卷章节：vol_XX / ch_XXX
- 执行阶段：Stage 4C 剧情外科与急救 (Evolution)
- 冲突靶点/重构诉求：<直接提取哨兵回执中的靶点描述或人类作者重构诉求>
- 执行指令：起手单次全读 ➔ 因果测算与快照备份 ➔ 手术刀微创修文 ➔ check 0 报错 ➔ 3行完工回执交卷即走
```

#### ③ Stage 4D 长程档案巡检派发令（Librarian）：
```text
【章节工序派发令 · 档案巡检】
- 书籍工作区：workspace/<书名> ｜ 巡检范围：ch_XXX 逢十巡检 / 卷末结算
- 执行阶段：Stage 4D 长程档案巡检 (Librarian)
- 核心输入：state/ 状态四表与章节梗概 synopsis.json
- 执行指令：运行打捞命令 ➔ 单次全读核验 ➔ 自愈 Level 1 或锁定 Level 2 靶点 ➔ 落盘 log/review/ ➔ 统一标准回执交卷即走
```

#### ④ Stage 0 开局筑基派发令（Architect 0-Prep / 0A / 0B / 0C）：
- **Stage 0-Prep 派发令 (Architect-Profiler)**：
```text
【章节工序派发令】
- 书籍工作区：workspace/<书名> ｜ 阶段：Stage 0-Prep (Architect-Profiler)
- 核心输入：workspace/user_input.txt
- 执行指令：起手 view_file 单次全读 user_input.txt ➔ 故事性提纯与戏剧重塑 ➔ 锁定黄金锚点 ➔ 智能留白补全 ➔ 物理直接落盘 workspace/<书名>/dossier.md（禁传 ArtifactMetadata） ➔ 3 行回执交卷
```
- **Stage 0A 派发令 (Architect-World)**：
```text
【章节工序派发令】
- 书籍工作区：workspace/<书名> ｜ 阶段：Stage 0A (Architect-World)
- 核心输入：书名《<书名>》、题材<题材>、主角<主角名>、核心脑洞与金手指（若存在 dossier.md 则重点消费 Part A 与 Part C 黄金锚点）
- 执行指令：执行 studio.py init ➔ 填实 bible/ 六表、project.json、characters/ 核心人物卡与 entities/ 实体卡 ➔ 消除所有槽位 ➔ 物理直接落盘（禁传 ArtifactMetadata） ➔ 3 行回执交卷
```
- **Stage 0B 派发令 (Architect-Story)**：
```text
【章节工序派发令】
- 书籍工作区：workspace/<书名> ｜ 阶段：Stage 0B (Architect-Story)
- 核心输入：0A 已交付的 bible/ 六表、characters/ 与 entities/ 实体事实（若存在 dossier.md 则重点消费 Part B 商业节拍与 Part C 黄金锚点）
- 执行指令：依照设定交付商业双大纲（main_plot.md / vol_01/outline.md） ➔ 全息通电 state/ 八表 ➔ 运行 studio.py milestone add ➔ 物理直接落盘（禁传 ArtifactMetadata） ➔ 3 行回执交卷
```
- **Stage 0C 派发令 (Architect-Inspector)**：
```text
【章节工序派发令】
- 书籍工作区：workspace/<书名> ｜ 阶段：Stage 0C (Architect-Inspector)
- 核心输入：全书设定、卡片、双大纲与 state/ 状态数据（对照 dossier.md Part C 与原始输入核验意图保真度）
- 执行指令：运行 studio.py check ➔ 七大语义深度推演 ➔ 落盘 log/review/stage_0_audit.md ➔ 针对性修复微瑕 ➔ 确认 0 errors ➔ 3 行回执交卷
```

#### ⑤ Stage 0E 换卷跃迁派发令（Architect-Volume）：
```text
【章节工序派发令 · 换卷跃迁】
- 书籍工作区：workspace/<书名> ｜ 目标分卷：vol_XX（起始章：ch_XXX）
- 执行阶段：Stage 0E (Architect-Volume)
- 核心输入：上一卷末对账数据、bible/02_power_system.md 战力标尺、outlines/main_plot.md 宏观规划、新卷想法（如有）
- 执行指令：战力标尺二次校准 ➔ 地缘与人物交接 ➔ 确立新卷商业绝活与 30 章潮汐大纲 ➔ 物理落盘 outlines/vol_XX/outline.md（禁传 ArtifactMetadata） ➔ 运行 studio.py milestone add ➔ 确认 check 0 报错 ➔ 3 行回执交卷
```

> 🛑 **防添油加醋物理锁**：
> 主控在填充上述派发令时，**严禁添加任何诸如“注意主角冷漠眼神”、“拔剑动作要慢”、“突出修罗场氛围”等文学指令**。
> 一切叙事约束已经在 `pack.md` 物理落地，派发令仅作为进程调用指令。违背此条直接判定为注意力溢出违规！

---

## 📦 模块 4：单章标准交付卡片 (Standard Delivery Card)

单章模式 S5 收口成功后，主控输出以下格式卡片并立即停机：

```markdown
### 🎬 【Novel Studio · 章节完工交付卡片】

- 📖 **本期交付**：第 [X] 卷 / 第 [Y] 章 《[章节名]》
- 📊 **工程指标**：初稿 [N] 字 ➔ 终稿 [M] 字 ｜ 机械探针放行 ｜ 台账平账 100%
- 🎯 **核心戏眼**：[1~2句话概括本章核心矛盾与破局点]
- 🪝 **断章刀口**：[定格在何处悬念、突发事件或关键变量揭晓瞬间]
- 📈 **状态变动**：
  - 伏笔更新：[新埋设 / 推进 / 闭环的伏笔]
  - 道具/资产：[核心收支与物品变动]
  - 境界/战力：[位阶晋升或能力变化]
- 🔭 **下章前瞻**：[依据大纲规划提炼的核心剧情期待与戏眼看点]

---
*(单章流水线已完成原子封存，主控停机待命。输入“继续写”启动下一章。)*

### 🔄 【Novel Studio · 换卷跃迁就绪卡片】（卷末三连封存后自动输出）

- 🏆 **分卷圆满结算**：第 [X] 卷 《[分卷名]》 已全线封存！
- 📊 **本卷最终战果**：共 [N] 章 ｜ 累计 [M] 万字 ｜ 卷末对账平账 100% ｜ 导出读者成书：`exports/vol_XX.txt`
- 🎯 **长程剧情坐标**：主角当前境界：[境界名] ｜ 新地图前瞻：[下一卷舞台]
- 💡 **换卷接续姿态（请指示）**：
  - **姿态 A（一键自动起卷）**：回复【继续写下一卷】或【自动换卷】，主控依据全书大纲全自动编织下一卷 30 章细纲与战力防崩校准；
  - **姿态 B（作者注入新脑洞）**：直接在聊天框回复你对下一卷的新想法（或放入 `workspace/user_input.txt`），主控提纯编入新卷；
  - **姿态 C（暂作休整）**：先阅读已导出的成书，随时唤醒主控。

---

### 🚀 【Novel Studio · 新卷启航卡片】（换卷编织完成后输出）

- 📖 **新卷确立**：第 [X+1] 卷 《[新分卷名]》
- 🎯 **新卷核心绝活（商业卖点）**：[一卷一绝活：本卷独有爽点机制]
- ⚖️ **战力标尺二次锚定**：当前地图最高战力上限：[标尺定义]，严防通胀
- 👥 **地缘与人物交接**：[随行搭档] ｜ [留守大后方资产] ｜ [新卷首阶段宿敌]
- 🎯 **新卷里程碑**：已排产 [K] 项核心破局里程碑
- 🏁 **首章起跑线**：第 [X+1] 卷 第 1 章（全书第 [M+1] 章）细纲已挂载！

---
*(换卷跃迁已原子封存，主控停机待命。输入“继续写”直接进入新卷首章 Stage 1 细纲与正文创作！)*

### ⏪ 【Novel Studio · 时光机回滚就绪卡片】（时光机回退完成后输出）

- 🎯 **回滚目标**：已成功回退至快照：`[快照名 / ch_XXX]`
- 📊 **当前状态**：当前最新有效章节：`ch_YYY` ｜ 台账平账 100% ｜ 系统校验 0 errors
- 💡 **后续接续姿态（请指示）**：
  - **姿态 A（重写该章）**：输入“继续写”或“重写当前章”，主控从当前节点重新启动 S1 编剧流水线；
  - **姿态 B（纯手工全量覆盖）**：所有历史快照均完整保存在 `snapshots/ch_XXX_*.zip`。若需手动回滚，直接将目标快照 `.zip` 内的所有内容解压并全量覆盖回 `workspace/<书名>/`，无需挑拣文件，一步到位！随后运行 `studio.py check` 验证即可。

---
```

---

## 🛡️ 模块 5：异常分级熔断器与巡航控制协议 (Exception & Cruise Protocol)

### 1. 三级异常熔断矩阵

```
[捕获工步阻断 / 回执异常 / CLI 错误]
   ├── Level 1 (CLI 业务/参数阻断，提供方案) ──➔ 读取终端 💡 【解决方案】 ➔ 主控直接遵照执行修复 ➔ 原工步重试
   ├── Level 2 (哨兵上报死锁/正文矛盾/台账阻断) ──➔ 主控严禁动手改文 ➔ 提取靶点委派 Stage 4C - Evolution 沙盒急救 ➔ 验证 check 0 报错 ➔ 重入收口
   └── Level 3 (主线严重死锁/连续急救失败/系统故障) ──➔ 停机中止 ➔ 整理 2~3 套备选方案请示作者
```

- **Level 1（主控自理与确定性方案自愈）**：
  - **触发条件**：CLI 退出码为 1 或 2（如缺少 `-w`、细纲未生成、在场人物死者登场、配置键未知、缺少子命令等）；
  - **处理契约**：引擎全线贯彻**【有阻断必有方案（Problem + Direct Remediation）】**，终端必然明确输出 `❌ 【阻断原因】` 与 `💡 【解决方案】`；
  - **主控动作**：**主控绝不猜测、绝不编写临时脚本探查**！直接提取并执行终端给出的 `💡 【解决方案】`（如按提示补齐前置步骤或修正参数），随后重试原命令；
- **Level 2（全权委派 Stage 4C - Evolution）**：
  - **触发条件**：
    1. Auditor 或 Librarian 完工回执显式上报 `[Level 2 复杂深层冲突]`；
    2. `finalize` 内存替换冲突、死者登场、位阶冲突、台账原子校验阻断。
  - **执行指令**：**主控绝不下场！** 立即提取哨兵回执中的冲突靶点，调用 `invoke_subagent` 委派全能问题解决专家 `Stage 4C - Evolution`；
  - **收口验证**：收到 `Stage 4C - Evolution` 完工回执（check 0 报错）后，主控重新执行 S5 安全短路命令收口。
- **Level 3（作者裁决）**：主线大纲冲突、连续 2 次急救失败、CLI 退出码 4（系统故障损坏） ➔ 彻底停机，整理方案上报作者。

---

### 2. 无人值守巡航控制协议 (Unattended Mode · 防死锁实战协议)

当人类指令明确要求【无人值守连写 / 巡航写 K 章 / 巡航至 ch_MMM】时启动：

#### 🚨 核心防死锁与驱动架构铁律
1. **严禁前台阻塞空等 `cruise` 轮询命令**：
   `studio.py cruise` 是外部批次安全监督与只读遥测工具，其底层逻辑是“装配细纲 ➔ 轮询等待正文 `raw_v3.md`”。**引擎自身绝不调用大模型写文**！
   若主控在终端直接运行未就绪章节的 `cruise`（不带 `--once`），会导致“引擎轮询等稿，主控等待命令结束”的双向死锁直至 900 秒超时！
2. **唯一合法驱动模式：【主控内部循环自主驱动 + S5 级联原子收口】**：
   - **主控为唯一驱动引擎**：主控接收到巡航指令后，在会话内建立 `ch_XXX ➔ ch_MMM` 章节循环，自主步进；
   - **推进单章工序**：主控顺序派发并执行当期章节的完整工序：
     `S1 (beats new + 编剧 + pack) ➔ S2 (Drafter) ➔ S3A (Dehydrator) ➔ S3B (Tuner) ➔ S4 (audit + Auditor)`；
   - **确定性原子收口**：Auditor 绿灯后，统一且唯一执行 S5 级联短路收口命令完成定稿与平账：
     ```powershell
     python studio.py finalize ch_XXX -w "<wk>" ; if ($LASTEXITCODE -eq 0) { python studio.py proposal auto ch_XXX --write --force -w "<wk>" } ; if ($LASTEXITCODE -eq 0) { python studio.py sync ch_XXX -w "<wk>" } ; if ($LASTEXITCODE -eq 0) { python studio.py snapshot create "ch_XXX" -w "<wk>" }
     ```
   - **严禁依赖 `cruise` 进行收口**：单章收口一律走上述 S5 级联命令，彻底杜绝命令二义性。

#### ⚡ 巡航极速步进流程
1. **批次边界计算**：
   起始章 `ch_XXX`，目标章 `ch_MMM`（若未指定，受 `cruise_max_chapters` 钳制，默认 ≤10 章）。
2. **逐章推进与单行心跳（防上下文爆炸）**：
   每章 S5 收口封存后，**主控绝对严禁倾倒正文全文或长篇总结**，必须且仅输出单行心跳：
   `✅ [无人值守心跳] 第 XX 章《章节名》已封存 (XXXX字) ➔ [批次进度: K/Total] ➔ 即刻启动第 XX+1 章...`
   输出心跳后，主控**立即自主启动下一章的 S1**，无需等待人类确认，直至达到目标批次终点。
3. **批次终点交付**：
   达到设定批次终点后，输出【模块 4】标准交付卡片，交还控制权并彻底停机。

#### 🛑 巡航安全刹车与异常守护
1. **卷末强制刹车（最高优先级）**：
   当巡航触达当前分卷的最后一章并完成封存时，必须强制刹车停机！
   执行卷末三连命令：
   ```powershell
   python studio.py reconcile vol_XX --write -w "<wk>" ; python studio.py rollup vol_XX -w "<wk>" ; python studio.py export -w "<wk>"
   ```
   卷末对账自动覆盖普通的逢十巡检，导出成书后彻底停机呈交作者。
2. **Level 2 剧情死锁刹车**：
   若当章质检回执中出现 `[Level 2 复杂深层冲突]`，巡航立即暂停！主控提取靶点委派 `Stage 4C - Evolution` 前去沙盒急救。验证 `check` 0 报错并完成当章 S5 收口后，方可恢复后续巡航。
3. **普通逢十档案巡检（非卷末）**：
   逢 10 章（如 ch_010 且非卷末）封存后，主控派发 `Stage 4D - Librarian` 巡检，收到无冲突回执后，继续推进下一章。
4. **长程巡航严禁越权**：
   整个长程巡航中，主控绝对严禁直接动手修改正文草稿（`raw/`、`final/`）或底层账本！