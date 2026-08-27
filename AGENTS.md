# Universal Novel Studio — 全题材自适应小说工业化流水线法典 (AGENTS.md v2)

> **v2 通用性改造**：本文档原名为「玄幻爽文工业化流水线法典」，v2 版本将所有有题材倾向的文风/基调/配比规则降级为「商业爽文默认值」，由 `genre_profile.json`（题材档案）按题材覆盖。真正的通用铁律仅保留五条（详见 `rules/novel_style.md` 第一节）。本法典聚焦**工程流程与确定性流水线**，文风规范请参阅 `rules/novel_style.md`（v2 自适应版）。

本文件是本仓库的**最高执行法典**。所有 Agent（主 Agent / Sub-Agent / 审校官 / 同步官）在执行任何操作前，必须先读本文件并严格遵守。本文件与 `rules/`、`skills/` 下的文档共同构成完整的创作规范体系。

---

## 第 0 节：运行时绝对禁令 (Runtime Invariants)

以下禁令在**任何情况下**都不可违反：

1. **严禁翻阅 / view_file 任何代码文件**：`tools/*.py`、`studio.py`、`tests/*.py`。所有工具能力通过 `python studio.py <command>` 调用，不要读源码。理由：代码文件体积大、上下文污染严重，且工具行为以 CLI 输出为准。
2. **严禁手写状态机文件**：`current_state.md`、`economy_ledger.json`、`chekhov_guns.md`、`misunderstandings.md`、`character_growth_arcs.md`、`timeline.md`。状态变更必须通过 `state_inbox/ch_xxx.json` 提案 → `python studio.py sync ch_xxx` 引擎合并。AI 只提案、不手写台账。
3. **严禁跳过质量门禁**：定稿必须通过 `python studio.py lint ch_xxx`（Exit Code 0）。CRITICAL 级问题（工程标记外泄、字数不足、读者懵逼检测）必须修复后才能交付。
4. **严禁在正文中出现工程标记**：GUN-003、MIS-001、Stage 1、伏笔道具、当前心智阶段、`[中文占位符]` 等。
5. **严禁直接修改 `finalized/` 下的定稿**：定稿修改必须通过「修改 raw_drafts → 重新审校 → 覆盖 finalized」流程。
6. **严禁删除 `state_inbox/processed/` 和 `snapshots/`**：这些是审计与回滚依据。

---

## 第 1 节：五层架构与目录结构

本项目采用**确定性/语义分离**的五层架构：

| 层级 | 目录/文件 | 职责 | 执行者 |
|------|-----------|------|--------|
| L1 配置层 | `novel_config.yaml`、`00_meta/genre_profile.json` | 全局声明式配置 + 题材档案 | 人类/总策划 |
| L2 设定层 | `00_meta/`、`01_world/`、`02_characters/`、`03_outlines/` | 世界观、人设、大纲、细纲 | 总策划/编剧 Agent |
| L3 状态层 | `04_timeline_and_state/` | 状态机、伏笔池、误会台账、心智台账、复式账本、时间线、提案收件箱 | 确定性引擎（AI 只提案） |
| L4 创作层 | `05_manuscript/` | 正文手稿（raw_drafts + finalized） | 主笔 Agent + 审校官 |
| L5 工具层 | `tools/`、`studio.py` | 33 个确定性工具 + 统一 CLI 调度器 | 程序（不读源码） |

### 目录结构速查
```
novel_workspace/
├── 00_meta/           # 项目圣经 + 题材档案
│   ├── project_bible.md
│   └── genre_profile.json    # ← 题材档案，控制文风/基调/配比/词表自适应
├── 01_world/          # 世界观设定
│   ├── world_rules.md
│   ├── factions.md
│   └── geography.md
├── 02_characters/     # 角色卡
│   ├── character_index.md
│   └── profiles/
├── 03_outlines/       # 大纲与细纲
│   ├── main_plot.md
│   ├── vol_01_outline.md
│   └── beats/
├── 04_timeline_and_state/  # 状态机（AI 不手写）
│   ├── current_state.md
│   ├── economy_ledger.json
│   ├── chekhov_guns.md
│   ├── misunderstandings.md
│   ├── character_growth_arcs.md
│   ├── timeline.md
│   ├── state_inbox/         # 提案收件箱
│   │   ├── ch_xxx.draft.json   # 草稿（不合并）
│   │   ├── ch_xxx.json          # 正式提案（合并）
│   │   ├── processed/           # 已合并
│   │   └── failed/              # 校验失败
│   └── snapshots/           # 状态快照（回滚用）
└── 05_manuscript/       # 正文
    └── vol_01/
        ├── raw_drafts/      # 初稿
        └── finalized/       # 定稿（门禁通过后）
```

---

## 第 2 节：文风规范 (v2 自适应)

> ⚠️ **v2 重大变更**：原「4 大通用心流母则」中的基调/断章/配比规则已降级为「商业爽文默认值」，由题材档案 `genre_profile.json` 按题材覆盖。**真正的通用铁律仅保留五条**，详见 `rules/novel_style.md` 第一节。

### 五条通用铁律（所有题材不可违反）
1. **限制视角不越界**：严格锁定当前 POV 角色的物理视野与认知边界。
2. **信息差自洽**：谁知道什么、谁不知道什么，前后一致。
3. **角色动机真实**：每个角色的行为有合乎其性格/立场/利益的动机。
4. **前后因果一致**：设定/规则/时间线/道具权属/人物关系前后一致，不吃设定。
5. **无工程标记外泄**：正文不出现 GUN-001/MIS-001/Stage 1/占位符等内部标记。

### 文风自适应执行流程
1. **先读题材档案**：执行任何文风判断前，先读取 `00_meta/genre_profile.json`（或运行 `python studio.py genre` 查看）。
2. **按题材策略执行**：基调（`tone_policy`）、配比（`ratio_baseline`）、断章（`ending_style`）、词表（`cliche_patterns`/`cliffhanger_keywords`/`semantic_clusters`/`quantity_whitelist`）均由题材档案控制。
3. **场景心流优先**：即使题材偏好明快，绝境/阴谋/葬礼场景自然可以阴暗；即使题材偏好阴暗，安全区/日常场景也可以明快。
4. **详细规范**：完整文风规范参阅 `rules/novel_style.md`（v2 自适应版）。

### 内置题材覆盖（17 种）
运行 `python studio.py genre --list` 查看全部内置题材档案：
- 通用兜底：generic
- 东方玄幻：xuanhuan（玄幻/仙侠/修仙/系统）、wuxia（武侠/江湖）、history（历史/架空/种田权谋）
- 现代都市：urban（都市/异能/职场商战/娱乐）、realism（现实主义/年代/知青）
- 科幻未来：scifi（科幻/机甲/星际/赛博朋克/末世废土）、lightnovel（轻小说/异世界转生）
- 悬疑恐怖：mystery（悬疑/推理/惊悚犯罪）、horror（恐怖/克苏鲁/灵异/心理恐怖）
- 规则生存：rulebound（规则怪谈/SCP/异常）、infinite（无限流/轮回/任务世界）
- 情感日常：romance（言情/纯爱/甜宠/婚恋）、iyashikei（治愈系/日常/慢生活/田园美食）
- 竞技军事：gaming（游戏/电竞/网游/直播）、sports（体育/竞技）、military（军事/战争/军旅/谍战）

---

## 第 3 节：核心工程铁律 (Engineering Invariants)

以下为**工程层面**的确定性规则，与题材无关，所有题材适用：

### 3.1 能力阶梯锁（通用化，不限于玄幻境界）
- 每卷仅允许主角跨越 **1 个大层级或 2~3 个小阶梯**。
- "能力阶梯"通用化为所有题材的核心竞争力：玄幻是境界，科幻是科技/异能评级，都市是资源/人脉/权位，悬疑是认知与证据链，言情是情感深度与信任边界，游戏/体育是技术等级。
- 严禁单章暴涨、跨级秒杀（除非有充分铺垫与代价）。
- 能力跃迁必须源于漫长专注与生死领悟（或对应题材的等价积累）。

### 3.2 核心竞争力（原"金手指"，通用化）
- 每本书有且仅有一个核心竞争力（系统/模拟器/特殊能力/信息差/技术碾压/规则利用等）。
- 核心竞争力的使用必须有真实代价与限制，不能无脑碾压。
- 核心竞争力的成长曲线与能力阶梯锁对齐。

### 3.3 经济数值防通胀（有经济体系的题材适用）
- 以底层普通人一餐一饭为购买力原点，确定货币换算体系。
- 高阶稀缺资源（灵石/信用点/装备/情报）有真实的流动消耗闭环。
- 拒绝数字无限加零、拒绝凭空暴富。
- 复式账本（`economy_ledger.json`）由确定性引擎从流水重算，AI 只提流水、不碰余额。
- **无经济体系的题材**（纯悬疑/纯爱/恐怖/治愈系）可跳过经济台账，由 `genre_profile.economy_required: false` 控制。

### 3.4 伏笔闭环承诺
- 所有埋下的伏笔（`chekhov_guns.md`）必须 100% 回收或明确标记为长线。
- 伏笔调度由 `foreshadow_scheduler.py` 自动计算：回唤提前量、沉睡容忍、长线周期均由题材档案控制。
- 严禁挖坑不填、严禁伏笔冲突。

### 3.5 状态机幂等性
- 状态变更通过提案（`state_inbox/ch_xxx.json`）→ 引擎合并（`studio.py sync`），幂等去重。
- 重复提交同一提案不会重复记账。
-  sync 失败的提案移入 `failed/`，修正后重跑即可，不会污染状态。

---

## 第 4 节：Stage 0-4 确定性工作流

### Stage 0：新书初始化
1. 运行 `python studio.py init --title "书名" --genre "题材" --protagonist "主角名"`
2. 工具自动：创建目录结构、拷贝模板、匹配题材档案（`genre_profile.json`）、生成初始状态机。
3. 总策划 Agent（`skills/novel-director`）与用户互动对齐：核心看点、世界观、人设、首卷大纲。
4. 生成初始资产：`project_bible.md`、`world_rules.md`、`factions.md`、`geography.md`、`character_index.md` + 主角卡、`main_plot.md`、`vol_01_outline.md`。

### Stage 1：单章细纲推演
1. 运行 `python studio.py pack ch_xxx --json` 装载全量上下文（状态机/伏笔/角色卡/上章余温）。
2. 编剧 Agent（`skills/novel-beats-builder`）推演 3 个 ABC 走向选项，由人类或总策划选定。
3. 细纲写入 `03_outlines/vol_xx/beats/ch_xxx_beats.md`。

### Stage 2：正文起草
1. 主笔 Agent（`skills/novel-chapter-drafter`）按细纲分场景起草。
2. 初稿写入 `05_manuscript/vol_xx/raw_drafts/ch_xxx_v1.md`。
3. 字数目标由题材档案控制（`genre_profile.word_count`），通用兜底 1800~5000 字。

### Stage 3：双轨独立审校
1. **Sub-Agent 审校优先**：调用 `invoke_subagent` 启动审校官（`skills/novel-continuity-guard`），在物理隔离上下文中执行语感重铸+全能纠错。
2. **本地自审校降级**：Sub-Agent 不可用时，主 Agent 自审校。
3. 审校官写入 `05_manuscript/vol_xx/finalized/ch_xxx.md`。
4. 运行 `python studio.py lint ch_xxx` 门禁核验（Exit Code 0 才能交付）。

### Stage 4：状态自同步
1. 运行 `python studio.py draft ch_xxx` 生成提案骨架（0-Token 预扫描，预填在场角色/资金流水/伤势/伏笔线索）。
2. 同步官（`skills/novel-state-syncer`）复核草稿，补全语义字段，另存为正式提案 `state_inbox/ch_xxx.json`。
3. 运行 `python studio.py sync ch_xxx`：引擎合并提案 → 复式记账 → 双台账校验 → 道具轨迹校验 → 打快照。
4. 交付【事实突变声明】+【下一章情节引子】。

---

## 第 5 节：Sub-Agent 协同规范

### 5.1 角色分工
| 角色 | Skill | 职责 | 生命周期 |
|------|-------|------|----------|
| 总策划 | novel-director | 新书策划、世界观、人设、大纲、走向决断 | 常驻 |
| 编剧 | novel-beats-builder | 单章细纲推演、ABC 走向 | 单章 |
| 主笔 | novel-chapter-drafter | 正文起草 | 单章 |
| 审校官 | novel-continuity-guard | 语感重铸、纠错、门禁 | 单章（物理隔离） |
| 同步官 | novel-state-syncer | 状态提案、记忆沉淀 | 单章 |

### 5.2 协同规则
- 审校官必须在**物理隔离上下文**中运行（`invoke_subagent`），不继承主 Agent 的上下文，确保双盲审校。
- Sub-Agent 完成任务后立即销毁（`auto_recycle_subagents: true`），避免上下文污染。
- Sub-Agent 之间不直接通信，通过文件系统（细纲/初稿/定稿/提案）传递信息。
- 所有 Sub-Agent 必须遵守第 0 节运行时禁令。

---

## 第 6 节：CLI 命令速查

运行 `python studio.py --help` 查看完整命令列表。常用命令：

| 命令 | 用途 |
|------|------|
| `studio.py init` | 初始化新书工作区 |
| `studio.py status` | 工作区状态总览 |
| `studio.py pack ch_xxx` | 打包全量上下文（JSON/文本） |
| `studio.py lint ch_xxx` | 质量门禁（含读者懵逼检测） |
| `studio.py draft ch_xxx` | 生成状态提案骨架 |
| `studio.py sync ch_xxx` | 合并状态提案 + 校验 + 快照 |
| `studio.py genre` | 查看/匹配题材档案 |
| `studio.py genre --list` | 列出全部内置题材 |
| `studio.py schedule ch_xxx` | 伏笔调度建议 |
| `studio.py radar` | 全维质量雷达（14 项检测） |
| `studio.py doctor` | 工作区体检（结构/账本/编号/占位符） |
| `studio.py snapshots` | 列出状态快照 |
| `studio.py rollback <snapshot>` | 回滚到指定快照 |
| `studio.py export` | 导出全本（md/txt） |
| `studio.py memory recall "关键词"` | 语义召回旧伏笔/人物/设定 |
| `studio.py memory repeat` | 跨章重复场景检测 |

---

## 第 7 节：质量门禁 (Quality Gates)

### 7.1 硬门禁（CRITICAL，阻断交付）
1. **工程标记外泄**：正文出现 GUN-001/MIS-001/Stage 1/占位符等。
2. **字数不足**：低于 `genre_profile.word_count.min`（通用兜底 1800 字）。
3. **读者懵逼检测 CRITICAL**：幽灵实体/代词迷雾区/因果虚接等严重阅读卡点。
4. **状态机不一致**：sync 后双台账不平衡、道具时空轨迹冲突。

### 7.2 软门禁（WARNING，不阻断但需关注）
1. 配比偏离题材基线（`ratio_baseline`）。
2. 语义冗余聚类命中（同段同义表达堆砌）。
3. 题材特定陈词模式命中（`cliche_patterns`）。
4. 伏笔沉睡超期（超过 `dormant_gap`）。
5. 角色掉线（超过 `stall_window` 章未出场）。

### 7.3 自愈流水线
- `self_healing_pipeline: true` 时，门禁不通过自动打回精修重写。
- `max_auto_retry_attempts: 3` 次上限，耗尽后暂停等待人工审核。
- 每次重试记录原因，避免相同错误无限重犯。

---

## 第 8 节：故障排查

| 现象 | 排查命令 | 解决方案 |
|------|----------|----------|
| lint 报工程标记外泄 | `studio.py lint ch_xxx -v` | 搜索正文删除 GUN-/MIS-/Stage 等标记 |
| sync 失败 | 查看 `state_inbox/failed/` | 按错误信息修正提案后重跑 `sync` |
| 题材档案不匹配 | `studio.py genre --genre "你的题材"` | 检查关键词，或手动编辑 `00_meta/genre_profile.json` |
| 状态不一致 | `studio.py doctor` | 修复 ERROR 项，或 `rollback` 到最近快照 |
| 伏笔沉睡超期 | `studio.py schedule ch_xxx` | 按调度建议回唤或引爆 |
| 配比持续报警 | `studio.py genre` 查看当前配比基线 | 确认题材档案是否正确，或微调 `ratio_baseline` |
| 工具命令不存在 | `studio.py --help` | 确认命令拼写，或查看本法典第 6 节 |

---

## 附录：文档索引

| 文档 | 路径 | 内容 |
|------|------|------|
| 本法典 | `AGENTS.md` | 工程流程、确定性流水线、运行时禁令 |
| 文风规范 | `rules/novel_style.md` | v2 自适应文风规范（5条铁律+题材覆盖） |
| 长线节奏 | `rules/novel_long_arc_and_pacing.md` | 三层期待感、能力阶梯、经济防通胀 |
| 脑洞节奏 | `rules/novel_brainhole_and_pacing.md` | 核心看点、爽点模型、反套路 |
| 防OOC | `rules/novel_anti_ooc.md` | 角色一致性、心智阶段、行为逻辑 |
| 工作流 | `rules/novel_workflow.md` | Stage 0-4 详细执行SOP |
| 总策划 | `skills/novel-director/SKILL.md` | 新书策划、世界观、人设、大纲 |
| 编剧 | `skills/novel-beats-builder/SKILL.md` | 单章细纲、ABC走向 |
| 主笔 | `skills/novel-chapter-drafter/SKILL.md` | 正文起草 |
| 审校官 | `skills/novel-continuity-guard/SKILL.md` | 语感重铸、纠错、门禁 |
| 同步官 | `skills/novel-state-syncer/SKILL.md` | 状态提案、记忆沉淀 |
| 题材档案 | `tools/genre_profiles/*.json` | 17 种题材的文风/基调/配比/词表配置 |

---

*本法典为 v2 全题材自适应版本。文风规范以 `rules/novel_style.md` 为准，本法典聚焦工程流程。如有冲突，以具体场景的题材档案 + 场景心流为最高优先级。*
