---
name: novel-architect
description: Universal worldbuilding architect and setup generator for Novel Studio (Stage 0). Covers all genres. Comprises 4 discrete subagent stages: Stage 0A (Architect-World), Stage 0B (Architect-Story), Stage 0C (Architect-Inspector), and Stage 0E (Architect-Volume for volume transitions).
---

# SKILL — novel-architect（全题材开局与分卷架构师专属手册 · Stage 0 / 0E 指南）

> ⚡ **【主控派发契约 · 接力流水线与情报卷宗分流协议】**：
> Stage 0 是全书物理与数据底座的奠基阶段。开新书统一由前置 **Stage 0-Prep (Architect-Profiler)** 将 `workspace/user_input.txt`（无论内容是杂乱碎片还是规范大纲）提纯重塑为标准化《新书立项情报卷宗》（`dossier.md`）。**主控严格依次唤起专职子智能体接力，严禁跨工序大包大揽！**
> 1. **第一棒 ➔ Stage 0A (Architect-World)**：执行 `init` 初始化，消费 `dossier.md` [Part A 设定与实体] 与 [Part C 黄金锚点]，填实 **`bible/` 设定圣经六表**、`project.json`、**`characters/` 核心人物卡** 与 **`entities/` 实体卡**，消除以上全部槽位；
> 2. **第二棒 ➔ Stage 0B (Architect-Story)**：依据 0A 确立的法定事实，消费 `dossier.md` [Part B 叙事大纲] 与 [Part C 黄金锚点]，负责交付 **首卷 25~40 章商业双大纲（`outlines/`）**，全息通电 **`state/` 八表** 并添加首卷里程碑；
> 3. **第三棒 ➔ Stage 0C (Architect-Inspector)**：独立沙盒运行 `check` 机器硬闸门、七大语义深度推演，并对照 `dossier.md Part C` 与原始输入核验**用户意图与黄金锚点保真度**，确保 **0 errors** 闭环交付；
> 4. **分卷独立工种 ➔ Stage 0E (Architect-Volume)**：连载中后期换卷（Scenario E）专职负责编制新卷商业大纲、战力二次锚定与地缘交接，与开局 0B 物理隔离。
>
> ⚡ **【子代理开工准则】**：规范已在技能中锁定，绝对严禁开工调用 `view_file` 回读倒嚼本手册！起手必须直接调用工具物理落盘（**绝对严禁传递 `ArtifactMetadata`**），交卷即走，绝不滞留！

> 🎨 **【子代理填写须知】**：
模板中的预填信息仅为占位，请根据当前题材与设定灵活填写，可自行补充更多！

---

## 🎯 一、 架构师系列专职子智能体工序与权限细则

### 🛠️ 子智能体 1：Stage 0A【设定公理、人物与实体筑基 (Architect-World)】

- **核心职责**：初始化书籍工作区，依据作者给定的设定或 `dossier.md`（重点消费 [Part A 设定与实体] 与 [Part C 黄金锚点]），填实设定真理底座（`bible/` 六表与 `project.json`），并建立与填实全部核心人物卡（`characters/`）与实体卡（`entities/`），严格贯彻黄金锚点，消灭以上所有 `{{slot:}}` 占位符；
- **执行工序**：
  1. 终端执行初始化命令（已含书籍数据的工作区拒覆盖，确认重置加 `--force`）：
     ```powershell
     python studio.py init -w "workspace/<书名>" -t "<书名>" -g "<题材>" -p "<主角名>"
     ```
  2. 填实 `bible/` 六表与 `project.json`（消灭所有 `{{slot:}}` 占位符，删除模板自带的注释）：
     - `bible/01_world_axioms.md`：核心 Logline、空间三级划分、2~3条不可违背客观公理、金手指/优势机制（原理+代价+上限+成长阶梯）；
     - `bible/02_power_system.md`：Tier 1~5 阶层梯阶与破坏力/表现力实物标尺（严防战力通胀）；
     - `bible/03_factions_geography.md`：首发舞台与进阶地缘、三大核心势力矩阵与利益冲突网；
     - `bible/04_economy_items.md`：货币体系与购买力平价锚点（PPP 对账表）、物资道具五阶分类；
     - `bible/05_special_mechanics.md`：题材专属特异机制、相生相克矩阵、负荷代偿法则；
     - `bible/06_deviations.md`：本书偏离清单与核心创作红线；
     - `project.json`：配置书级参数与题材专属词表。
  3. 填实/建立核心角色卡 `characters/`（消灭所有 `{{slot:}}` 占位符，按需填写，允许存在多个）：
     - `characters/protagonist.md`：填实主角专属卡（基于 `init` 生成模板，确立四维心理、微动作库、恒定称谓矩阵）；
     - `characters/antagonist.md`：填实首卷核心反派/宿敌卡（基于 `init` 生成模板，锁定扭曲心理四维、压迫标尺、走狗矩阵、镜像对立与溃败破局钥匙）；
     - `characters/<核心角色>.md`：按需创建关键搭档/女主卡（基于 `templates/characters/character_card_standard.md`，独立动机、互称矩阵）。
  4. 建立开局实体卡 `entities/`（消灭所有 `{{slot:}}` 占位符，按需填写，允许存在多个）：
     - `entities/factions/<初始宗门/阵营名>.md`：开局初始势力卡（基于 `templates/entities/faction_card.md`，锁定掌权人 `leader`、总部 `headquarters`、核心资产、外交关系）；
     - `entities/locations/<开局地标场景名>.md`：开局新手村/核心地标场景卡（基于 `templates/entities/location_card.md`，锁定空间物象、感知锚点与环境规则）；
     - `entities/items/<道具名>.md`：创建开局核心道具/资产卡（基于 `templates/entities/item_card.md`，锁定 `holder`、品阶、使用消耗、充能上限与耐久）。

- **准跑命令**：`python studio.py init`；
- **准写工件**：`write_to_file` / `replace_file_content` 写入 `bible/*.md`、`project.json`、`characters/`、`entities/`（**严禁传递 `ArtifactMetadata`**）；
- **完工标准**：设定六表、人物卡与实体卡槽位消除率 100%，输出标准完工回执即刻交卷。

---

### 👤 子智能体 2：Stage 0B【商业故事宇宙筑基与状态机通电 (Architect-Story)】

- **核心职责**：以 0A 交付的 `bible/` 设定、`characters/` 人物与 `entities/` 地缘道具为依托，结合 `dossier.md`（重点消费 [Part B 叙事大纲] 与 [Part C 黄金锚点]），专职交付**首卷 25~40 章商业双大纲（`outlines/`）**，全息通电 `state/` 八表，并添加首卷破局里程碑；
- **商业网文故事筑基四大硬核法则**：
  1. 🎯 **一卷一绝活（核心商业卖点）**：首卷确立明确的核心爽点与脑洞兑现机制，前三章必须让读者体验到破局；
  2. ⚡ **章节绑定【本章看点 + 断章刀口】**：在 `outlines/vol_01/outline.md` 中，严禁写成无聊对账流水账，每章必须标明：`ch_XXX：【核心行动推进/看点】+【章末悬念刀口】`；
  3. 🎭 **对手与配角去工具化**：对手行动基于利益算计或自保本能，严禁无脑嘲讽；搭档具备独立诉求与毛刺；
  4. 💣 **高能线索网布设**：`state/lines.json` 中埋设高戏剧张力线索：`GUN-001`（危机倒计时）、`KNO-001`（致命信息差）、`MIS-001`（外界认知反差）。
- **执行工序**：
  1. **商业双大纲物理落盘**（消灭所有 `{{slot:}}` 占位符）：
     - `outlines/main_plot.md`：填实全书主线三幕脊柱、核心驱动力、开局终局与长程宏观里程碑；
     - `outlines/vol_01/outline.md`：填实首卷商业分卷大纲（商业卖点、四分位戏剧潮汐节拍、主支线追踪谱与分章航标）。
  2. **状态机八表全息通电**（依据 0A 已确立的 characters/ 与 entities/ 实体事实，同轮写入 state/，遵循 `templates/README.md` 强类型白名单字段；文件若未建则首次写入合法 JSON）：
     - `state/persons.json`：注册核心人物（`p_001` 主角、`p_002` 反派/宿敌 `role: "antagonist"`, `attitude: "hostile"`、`p_003` 关键搭档等，绑定 `card` 路径与法定属性）；
     - `state/items.json`, `factions.json`, `places.json`：登记对应实体（绑定 `card` 路径与法定属性）；
     - `state/current.json`：填实开局第一现场（时间、地点、主角状态、在场人、初始四件套）；
     - `state/lines.json`：埋设首卷长线 `GUN-001`（反派危机倒计时/悬顶之剑）、知情差 `KNO-001`（反派阴谋信息差）、认知偏差 `MIS-001`；
     - `state/locked.json`：登记不可逆既定事实 `LOCK-001`；
     - `state/ledger.json`：仅在 `pools` 中声明本题材货币池（灵石、银两或积分；初始余额即按 `pools` 首次写入值固化为 `pools_baseline` 基线，引擎按「基线 + 流水重放」自动保真）；
     - `state/debts.json`：独立顶层数组登记开局未清算血仇/恩怨 `DEBT-001`（主角 vs 反派，含 `id/type/source_char/target_char/desc/created_ch/status`；引擎**只认此文件**，写进 ledger.json 会被全景无视）；
     - 终端执行添加首卷破局里程碑：
       ```powershell
       python studio.py milestone add --title "标题" --target-ch 5 --desc "描述" -w "workspace/<书名>"
       ```
- **准跑命令**：`python studio.py milestone add`；
- **准写工件**：`write_to_file` / `replace_file_content` 写入 `outlines/`, `state/`（**严禁传递 `ArtifactMetadata`**）；
- **完工标准**：双大纲落盘且槽位消除率 100%，八表通电完毕，里程碑已添加，输出标准完工回执即刻交卷。

---

### 🩺 子智能体 3：Stage 0C【全息双轨审查与语义逻辑深审 (Architect-Inspector)】

- **核心职责**：对全书底座进行机器硬闸门体检、**LLM 深度语义推演** 与 **用户意图/黄金锚点保真度审查**，输出详尽审查报告，消除一切逻辑漏洞，确保 0 errors 闭环交付；
- **执行工序**：
  1. **第一轨【机器硬闸门 · 必须 0 errors】**：
     - 终端运行体检命令：
       ```powershell
       python studio.py check -w "workspace/<书名>"
       ```
     - 零容忍指标：未填槽位 `unfilled_slot` 必须为 0；未登记角色 `unregistered_character` 必须为 0；实体 ID 冲突为 0；
  2. **第二轨【大模型七大语义理解与叙事逻辑深度推演】**：
     - 深度推演：①金手指机制逻辑闭环 ②爽感张力与冲突可信度 ③人物心理与独立活人感 ④长线叙事弧光与大纲节奏 ⑤因果时空尺度自洽 ⑥经济与战力标尺稳定 ⑦偏离清单创作红线遵从；
     - **黄金锚点与意图保真度核验**：对照 `dossier.md Part C` 与原始输入，核验用户指定的高光场景与人设细节是否 100% 落实；
  3. **落盘审查报告并闭环确认**：
     - 调用 `write_to_file` 将详尽审查报告写入 `log/review/stage_0_audit.md`（**严禁传递 `ArtifactMetadata`**）；
     - 若有微瑕，调用 `replace_file_content` 针对性修复；
     - 终端复跑 `python studio.py check -w "workspace/<书名>"` 确认 **0 errors 放行**。
- **准跑命令**：`python studio.py check`；
- **准写工件**：`write_to_file` 写入 `log/review/stage_0_audit.md`，`replace_file_content` 修正微瑕（**严禁传递 `ArtifactMetadata`**）；
- **完工标准**：报告物理落盘，机器硬闸门 0 errors，输出标准完工回执即刻交卷。

---

### 🌐 子智能体 4：Stage 0E【分卷跃迁与战力防崩架构 (Architect-Volume)】

- **核心定位与职责**：**专职负责连载中后期的换卷跃迁（开新卷 · Scenario E）**，与开新书的 0B 物理隔离。当上一卷（`vol_XX`）圆满封存导出后，进入新卷（`vol_XX+1`）编织时由主控独立唤起，**强制执行四大防崩纪律**：
  1. ⚖️ **战力标尺二次锚定（Anti-Power-Creep）**：
     - 强制比对 `bible/02_power_system.md` 物理破坏力标尺；
     - 确立新卷战力天花板，严防“换了新地图，看门狗都毁天灭地”的恶性贬值，保持主角实力的真实含金量；
  2. 👥 **地缘与人物交接表（Personnel & Geography Turnover）**：
     - **留守资产化**：老配角/初始地标留在原地图，转为主角大后方的资源通道或庇护所，杜绝人物断崖失踪；
     - **随行搭档**：明确随主角踏入新地图的 1~2 位核心同伴；
     - **新对手升级**：新地图反派必须具备更高段位的社会地位、利益诉求与压迫方式，杜绝低智嘲讽；
  3. 🎯 **一卷一绝活（New Volume Gimmick & Promise）**：
     - 确立本卷独有的**全新核心爽点与商业承诺**（例如：第一卷主打“绝境苟道与反差发育”，第二卷跃迁为“黑市商道垄断与暗网割据”），避免老套路审美疲劳；
  4. 🔢 **章节编号严格递增自愈**：
     - 自动检测上一卷终止章（如 `vol_01` 止于 `ch_030`），新卷 `vol_02/outline.md` 必须严密从 `ch_031` 起步编排 25~40 章的逐章核心行动与章末断章刀口；
- **准跑命令**：`python studio.py milestone add`、`python studio.py check`；
- **准写工件**：`write_to_file` 写入 `outlines/vol_XX/outline.md`，更新 `state/current.json` 切入新地图（**严禁传递 `ArtifactMetadata`**）；
- **完工标准**：新卷大纲落盘且槽位消除率 100%，战力与人物交接落地，里程碑已添加，`check` 0 errors，输出标准完工回执即刻交卷。

---

## 🔒 二、 白名单与权限红线（契约边界）

- 💻 **准跑命令**：
  - 0A: `python studio.py init ...`
  - 0B: `python studio.py milestone add ...`
  - 0C: `python studio.py check ...`
  - 0E: `python studio.py milestone add ...`, `python studio.py check ...`
- 📖 **准读输入**：输入 Prompt、`bible/`、`characters/`、`entities/`、`outlines/`、`state/`（单次全读，禁切片）；
- ✍️ **准写工件**：
  - 0A 准写：`bible/*.md`、`project.json`、`characters/`、`entities/`
  - 0B 准写：`outlines/`、`state/`
  - 0C 准写：`log/review/stage_0_audit.md`（及针对性修正各表微瑕）
  - 0E 准写：`outlines/vol_XX/outline.md`、`state/current.json`
  （**绝对严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁阅读 `engine/` 源码；严禁编写任何临时脚本；
  - 严禁单 Agent 越权大包大揽（开新书严格按 0A ➔ 0B ➔ 0C 顺序接力；换卷由 0E 独立承接）；
  - 交付前机器体检必须 0 errors；落盘后严禁留恋滞留。

---

## 🛑 三、 极简标准完工回执 (统一回执 · 3 行)

- **Stage 0A 回执**：
```text
【章节工序完工回执】
- 完工阶段：Stage 0A 设定与实体筑基 (Architect-World)
- 产出路径：workspace/<书名>/bible/, characters/, entities/
- 核心指标：设定六表已落盘 ｜ 人物与实体卡槽位消除率 100% ｜ 验收达标
```

- **Stage 0B 回执**：
```text
【章节工序完工回执】
- 完工阶段：Stage 0B 故事与状态通电 (Architect-Story)
- 产出路径：workspace/<书名>/outlines/, state/
- 核心指标：商业双大纲槽位清零 ｜ state八表全息通电 ｜ 里程碑已添加 ｜ 验收达标
```

- **Stage 0C 回执**：
```text
【章节工序完工回执】
- 完工阶段：Stage 0C 架构审查 (Architect-Inspector)
- 产出路径：workspace/<书名>/log/review/stage_0_audit.md
- 核心指标：七大语义逻辑深审达标 ｜ 审查报告物理落盘 ｜ 机器硬闸门 0 errors ｜ 验收达标
```

- **Stage 0E 回执**：
```text
【章节工序完工回执】
- 完工阶段：Stage 0E 分卷跃迁与战力防崩 (Architect-Volume)
- 产出路径：workspace/<书名>/outlines/vol_XX/outline.md
- 核心指标：战力标尺二次锚定 ｜ 地缘与人物交接完毕 ｜ 一卷一绝活确立 ｜ 机器硬闸门 0 errors ｜ 验收达标
```
