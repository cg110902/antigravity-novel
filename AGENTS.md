# Universal Novel Studio · 全题材通用小说工业化流水线法典 (AGENTS.md)

本文件定义了 **Universal Novel Studio** 的总架构师（Lead Director / Planner）与专业特工（Sub-Agents）之间的协同流水线、任务分派协议、宏观元素配比与通用质量门禁。

> 📌 **跨题材通用母法原则 (Universal Multi-Genre Law)**：
> 本文件及所有 `agents/rules/`、`agents/skills/` 均为**全题材通用的基础母体法典**（适配玄幻仙侠、都市异能、科幻机甲、悬疑推理、历史架空、无限流等任意题材）。
> 严禁在通用指令中硬编码任何具体作品的专有名词、特定人名、地名、特定卷名或特定数值。具体小说的设定、手稿与状态台账严格物理隔离在 `novel_workspace/` 中，开新书时仅变更 `novel_workspace/`。

---

## 0. 上下文卫生与工具调用铁律 (Context Hygiene & Tool Contract)

> 🎯 **核心认知：Python 工具是"被调用的函数"，不是"要阅读的文档"。**
> 所有 Agent（含主控与 Sub-Agent）通过 `run_command` 执行 `python studio.py <命令>`，只消费其**终端输出 / `--json` 结果**，**绝不读取工具源码**。工具代码再大也不占模型上下文——占上下文的只有你主动 view_file 的文件。

**🛑 三条上下文红线（所有 Agent 必须遵守）：**

1. **严禁翻阅 / view_file 任何代码文件**：`tools/*.py`、`studio.py`、`tests/*.py`、`__pycache__/`。需要什么能力就调对应命令，行为以命令输出和本法典为准，不要去源码里"确认实现"。唯一例外是主控 Agent 在开发/维护工具链本身时。
2. **不要整本打开状态台账**：`current_state.md`、`economy_ledger.json`、`chekhov_guns.md` 等长台账，一律通过 `studio.py pack`（已自动裁剪/预算化）或 `studio.py status` 获取摘要；不要手动 view_file 全量读取再塞进上下文。
3. **一章一装载，用完即弃**：每章开工前 `python studio.py pack ch_xxx --json`（上下文紧张加 `--budget 8000`）拿到**本章专用上下文包**；章末定稿后该包即作废，不要跨章累积。`budget_report` 会明确告诉你裁掉了什么。

**上下文分层（什么东西在什么时候占用窗口）：**

| 层 | 内容 | 何时占用 |
|---|---|---|
| 常驻 | 本法典 AGENTS.md + 平台挂载的 `agents/rules/`、`agents/skills/` | 进会话即常驻（规则总量克制，勿往里堆正文/样例） |
| 按需 | 本章 pack 上下文包（状态/伏笔/梗概脊柱/RAG召回/调度建议/预警） | 调 `pack` 时装载，受 `--budget` 封顶 |
| 按需 | 当前章细纲 / 草稿 / 定稿（`03_outlines/`、`05_manuscript/`） | 只在该章 Stage 2/3 读写本章对应文件 |
| 零占用 | `tools/*.py`、`studio.py`（工具源码） | **永不读取**，只调用、只看输出 |

**阶段 ↔ 命令速查（照着调即可，无需理解内部实现）：**

| 阶段 | 命令 | 作用 |
|---|---|---|
| Stage 0 | `python studio.py status` | 进度/字数/资产/活跃伏笔概览 |
| Stage 0 | `python studio.py doctor` | 工作区结构与账本体检（ERROR 必须先修） |
| Stage 0 | `python studio.py genre` | 查看本书题材档案（配比基线/口癖/塌中段窗口/题材导演指导） |
| Stage 1 | `python studio.py init --title "..." --genre "..." --protagonist "..."` | 全题材新书脚手架母版创生与初始化 |
| Stage 2 | `python studio.py pack ch_xxx --json [--budget N]` | 装载本章全量上下文（含记忆引擎与伏笔调度） |
| Stage 2 | `python studio.py schedule ch_xxx` | 伏笔主动排期（该引爆/回唤/唤醒哪些枪） |
| Stage 2 | `python studio.py memory recall "关键词"` | BM25 资料员手动回捞旧伏笔/人物/设定 |
| Stage 2 | `python studio.py memory spine` | 扫描定稿自动补全章节梗概脊柱 |
| Stage 2 | `python studio.py memory repeat` | 跨章重复检测（重复首介/雷同/节拍相似） |
| Stage 3 | `python studio.py lint ch_xxx [--voice]` | 定稿质量门禁（字数/AI腔/读者懵逼，CRITICAL 阻断） |
| Stage 3 | `python studio.py confusion ch_xxx` | 单独运行读者阅读卡点与认知断层检测 |
| Stage 3 | `python studio.py rx ch_xxx` | 生成单章分层靶向微创手术处方建议 |
| Stage 3 | `python studio.py diff ch_xxx` | 初稿 vs 定稿脱水重铸质量与颗粒度对比 |
| Stage 3 | `python studio.py quality ratio -c ch_xxx` | 黄金配比三维量化（WARNING 参考，不阻断） |
| Stage 3 | `python studio.py quality stall` | 连续无状态变更塌中段注水检测 |
| Stage 3 | `python studio.py quality distill [-c ch_xxx]` | 全书文风指纹蒸馏或单章偏离度比对 |
| Stage 4 | `python studio.py facts ch_xxx` | 0-Token 快速预提取单章资金流水、伤势与重点道具 |
| Stage 4 | `python studio.py draft ch_xxx` | 0-LLM 预填提案骨架（角色/候选流水/线索/梗概）→ `.draft.json` |
| Stage 4 | `python studio.py apply` | 确定性合并 `state_inbox` 中待处理的状态变更提案 |
| Stage 4 | LLM 复核草稿另存为 `state_inbox/ch_xxx.json` → `python studio.py sync ch_xxx` | 提交结构化状态变更→引擎合并→校验台账→快照封存 |
| 任意 | `python studio.py radar [--json]` | 全维雷达总控（doctor/账本/DAG/塌中段/配比/重复/懵逼…） |
| 任意 | `python studio.py export [--txt]` | 编译导出全书出版级 Markdown 或 TXT 手稿 |
| 任意 | `python studio.py snapshots` / `snapshot <name>` | 列出历史快照 / 创建指定名称快照 |
| 任意 | `python studio.py rollback <name> [--clean-drafts]` | 回滚状态机至历史快照（可选清理孤立稿件） |
| 任意 | `python studio.py test` | 运行自动化单元测试套件 (76 项测试全绿) |

> 💡 **职责分工铁律**：确定性的事（记账、编号、查重、配比统计、BM25 召回、伏笔排期、快照回滚）**全部由本地 Python 完成，零 Token**；需要语义理解的事（提炼事实突变、写梗概、写正文、判断戏腔与张力）才交给 LLM。LLM 产出**结构化提案/正文**，Python 引擎负责**校验、合并、记账、守门**。

---

## 1. 核心架构与 4 阶段流水线总览

```
 ┌────────────────────────────────────────────────────────┐
 │      Stage 1: 新书开局与全题材世界架构 (Novel Inception)     │
 │   - 人机对话确定核心脑洞、世界法则、民生经济与角色卡片 │
 │   - 无需前期样本：基于 4 大通用心流母则直接冷启动首章   │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │   Stage 2: 单章细纲推演与走向决断 (Autonomous Beats)   │
 │   - 4 维正交积木拼装 (镜头/引擎/折叶/余韵)，自主决断最优走向 │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │    Stage 3: 正文起草与独立审校流水线 (Draft & Polish)    │
 │   1. 初稿起草: 依循宏观黄金配比起草，存至 raw_drafts/     │
 │   2. 独立精修: 派发 novel_editor 执行去戏腔、脱水与纠错   │
 │   3. 即用即焚: 验收定稿后单轮内立即物理销毁 Sub-Agent     │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │   Stage 4: 状态自同步、版本快照与交付 (Sync & Snapshot)│
 │   - 自动回写 current_state, ledgers, guns, arcs, timeline │
 │   - 运行 python studio.py sync ch_xxx 校验台账并封存快照  │
 └────────────────────────────────────────────────────────┘
```

---

## 2. 通用文风与叙事心流 4 大母则 (Universal Flow Pillars)

无论何种题材，全书起草与精修必须严格遵守以下 4 大通用标准，彻底拔除 AI 味、老套包浆与阅读疲劳：

1. ☀️ **【自然通透 · 拒绝逼仄阴暗与冷峻压抑】**：
   - 坚决杜绝通篇沉溺于逼仄、阴暗、压抑、死寂、冷峻或暗黑中二基调；
   - 无论何种题材，常规场景必须保持**明快、干脆、从容、自信、富有烟火气与生活感**，多展现开阔视界、健康生命力与积极向上的力量感。
2. 💬 **【市井人话 · 彻底斩除古早戏腔与虚伪客套】**：
   - 对白必须讲人话、接地气、有动机、有利益算盘与现实微机锋；
   - 坚决斩除“老朽活了大半辈子”、“某某有绝密要务求见”、“渊渟岳峙”、“不怒自威”、“神色肃穆”、“抱拳领命”等古装舞台剧念白与老套成语堆砌；人物对话像活在真实利益世界中的人。
3. ⚙️ **【扎实推进 · 轻量动线与拒绝慢动作描写过载 (Lean Description)】**：
   - **描写严控在 15%~30% 以内**：环境与器物描写必须依附于人物动线一笔带过，严禁停下剧情大段描摹风景与死物；
   - **交锋拒绝子弹时间**：动作交锋追求干脆凌厉、雷霆破局，靠结果反差与利落动作营造爽感，严禁慢动作拆解微观粒子导致叙事拖沓；
   - 核心机制（技能晋升、推演演法、系统结算、装备制造、超频异能）展现清晰的里程碑推进与真实生理/器物损耗代价，拒绝浮夸刷屏。
4. 🎣 **【刀尖断章 · 坚决拔除假大空煽情口号】**：
   - 章节末尾必须直接卡在最紧绷的冲突爆发点、动作临界点或悬念转折点上，逼读者立即翻页；
   - 坚决拔除“大江东去，风云际会。浩瀚大世已在脚下铺展！”等假大空空洞煽情总结。

---

## 3. 全书宏观叙事元素黄金均值配比法则 (Macro Golden Ratio Law)

> 💡 **【单章动态自适应 · 全书追求均值均衡 · 对话驱动灵活赋权】**：
> - **全书宏观基线**：宏观上全书稳定维持在 **对白 30%~40% / 推进与动作 40%~50% / 静态描写 ≤20%~30%**；
> - **对话推动剧情与灵活浮动**：现代读者高度偏好节奏生动的对话交锋。在机锋博弈、市井盘算、谈判对峙、误会揭露或日常互动等场景中，**不设死板上限，完全由主笔特工与审校 Sub-Agent 自主拿主意，对话占比可自然提升至 40%~55%+**，用密集的台词交锋直接拉扯剧情与推进因果；
> - **决战与高潮章**：动作决策与雷霆破局自然占据主导（动作 50%~60%），各取所长，随物赋形。

```
 ┌────────────────────────────────────────────────────────┐
 │           全书宏观叙事黄金配比 (Macro Golden Ratio)      │
 ├────────────────────────────┬───────────────────────────┤
 │ 💬 对白与机锋交锋 (30%~40%+)│ 讲人话、有算盘、对话推剧情│
 │ ⚡ 剧情推进与动作决策 (40%~50%)│ 谁干了什么、当场结果与收获│
 │ 🔍 环境与静态描写 (15%~30%)│ 随动线一笔带过，绝不慢放  │
 └────────────────────────────┴───────────────────────────┘
```

- **将篇幅最大化倾注在剧情推进与人物交锋上**：把字数留给利益拉扯、机智博弈、破局决断与实质战备收获，杜绝用静态风景与无意义慢动作注水。

---

## 4. 分阶段执行细则与核心门禁

### 阶段一：新书开局与全题材世界架构 (Stage 1: Novel Inception)
- **触发**：用户提出一句话灵感或新书策划需求。
- **执行**：
  1. 调用 `novel-director`，与用户对齐核心看点（推荐运用 `/grill-me` 深度访谈）；
  2. 生成 `00_meta/project_bible.md`、`01_world/world_rules.md`、`02_characters/`、`03_outlines/` 与 `04_timeline_and_state/` 初始状态机；init 会按题材自动匹配并落一份**题材档案** `00_meta/genre_profile.json`（内置玄幻/都市/科幻/悬疑/历史/规则怪谈/通用，可人工微调，最高优先）；
     - 🎭 **题材档案决定本书的"好书店线"**：章节字数区间、黄金配比基线、塌中段窗口（悬疑/规则怪谈更紧=2 章）、对白地板/描写天花板、题材专属雷词口癖、伏笔提醒窗口，以及注入 pack 的 **director_notes 题材导演指导**（如悬疑要求线索公平、科幻要求设定自洽、都市鼓励对白到 55%）；
     - 质检工具（`quality stall/ratio/distill`）与伏笔调度器（`schedule`）自动读取该档案，无需手改代码；改题材只需编辑这份 JSON 或 init 时换 `-g`；查看用 `python studio.py genre`；
  3. 🌌 **长线叙事大格局规划**：构筑跨卷、跨阶段的深层伏笔网络（Chekhov's Guns）、多方阵营动态博弈、人物多阶心智弧光（Character Growth Arcs）与世界底层因果演进；
  4. 🚀 **新书冷启动第一性原理 (Cold-Start First-Principles Engine)**：
     - **新书在完全没有前序章节或参考切片的情况下，无需焦虑！**
     - 起草与审校特工直接以本法典确立的 **4 大通用心流母则与黄金配比** 作为第一性原理基准；
     - 结合新书设定的世界观与人设，直通起草第 1 章（CH1）；
     - CH1 定稿后，自然成为全书后续所有章节（CH2+）的最高正向风格真值样板，实现全自动平稳巡航，杜绝反复试错。

---

### 阶段二：单章细纲推演与走向决断 (Stage 2: Autonomous Beats & Pacing)
- **执行**：
  1. 运行 `python studio.py pack ch_xxx --json` 一键装载全量语境、状态机与预警；上下文窗口紧张时加 `--budget 6000`，引擎会按「本章细纲 > 硬预警 > 当前状态 > 全书梗概脊柱 > 上章余温 > 伏笔/误会 > 心智台账/RAG召回 > 人物卡」的优先级裁剪，并在 `budget_report` 中明确报告**裁掉了哪些区块、各多少 token**；
  2. **P1 记忆引擎会自动注入三类防重复/防遗忘语境（纯本地、零 Token）**：
     - 📚 **全书梗概脊柱**（`chapter_synopsis.json`）：每章一句话梗概，避免重复已写过的场景/桥段；定稿后由 state-syncer 在提案里带 `synopsis` 字段登记精炼梗概（`studio.py memory spine` 可为漏登记章节补自动梗概占位）；
     - 🔎 **RAG 资料员 BM25 召回**：按本章细纲/上章结尾召回最相关的旧伏笔、人物、设定段落（`studio.py memory recall "关键词"` 可手动查询；无 jieba 时自动降级为字 bi-gram，零依赖可用）；
     - 🔁 **跨章重复预警**：已登场角色被"再次首次介绍"、n-gram 雷同、场景节拍相似（`studio.py memory repeat`），写新章时必须换桥段、勿重新介绍老角色；
  3. 🪶 **P2 伏笔主动调度（pack 自动注入，也可 `studio.py schedule ch_xxx` 单独跑）**：beats-builder 动笔前先看排期建议——本章应**引爆/回收**哪些到期或超期伏笔、应**回唤**哪些临近引爆（3 章窗口内）的伏笔、哪些**沉睡伏笔**（5 章未提及）需要自然唤醒、长线伏笔的保温节奏；beats 必须为"应引爆"伏笔安排兑现节拍；
  4. 调用 `novel-beats-builder` 推演单章分场景细纲，运用 4 维正交积木拼装体系（镜头/引擎/折叶/余韵）；
  5. 🎣 **高级叙事驱动与推拉术**：在核心冲突篇章中运用三层期待感模型（显性目标 + 隐性危机 + 倒计时紧迫感），在日常过渡篇章中张弛有度；
  6. 🛡️ **长线数值与阶梯锁**：严禁单章极速暴涨；机制与金手指必须具备真实波折、代价与未竟之憾；
  7. 🏛️ **社会生态深度**：高位势力拥有体制威严与利益算盘，严禁安排低智反派无脑叫嚣；
  8. 推演 3 个走向选项，由 Lead Director 自主评估选定最优选项，直通起草。

---

### 阶段三：正文起草与独立审校流水线 (Stage 3: Drafting & Auditing Pipeline)
- **执行**：
  1. **初稿起草 (Drafting)**：
     - 调用 `novel-chapter-drafter` 分场景撰写正文（**标准 2500 ~ 5000 字自适应**，情节饱满即自然收尾），保存至 `raw_drafts/ch_xxx_v1.md`；
     - 🚫 **【防工程标记外泄铁律】**：严禁在小说正文中出现 `GUN-xxx`、`MIS-xxx`、`Stage x` 等内部工程标记；
     - ☀️ **【基调自然明朗】**：保持自然通透、干脆明快、富有生活感，严禁逼仄阴暗；
     - 🗡️ **【动线轻量脱水】**：描写严格控制在 30% 以内，动作利落，杜绝子弹时间慢动作。
  2. **独立审校流水线 (Subagent Auditing Pipeline)**：
     - 🚀 **主轨 (Primary · Subagent 物理隔离审校与去戏腔重铸)**：
       主控 Agent 调用 `invoke_subagent` 派发专职独立的 `novel_editor` 审校 Sub-Agent：

       ```json
       {
         "Subagents": [
		    {
             "TypeName": "novel_editor",
             "Role": "novel_editor (金牌网文总编 · 通用网文精修与定稿特工)",
             "Prompt": "【任务类型】: 通用单章网文内容精修、去戏腔去沉闷与全维定稿交付\n
			 【输入文件】: novel_workspace/05_manuscript/vol_xx/raw_drafts/ch_xxx_v1.md\n
			 【输出目标】: novel_workspace/05_manuscript/vol_xx/finalized/ch_xxx.md\n\n
			 
			 【1. 通用网文爆款标准 (Universal Flow Pillars)】:\n
			 - 🎯 专人专事，充分放权！你的核心使命是打磨出自然明快、生动扎实、极具张力的现代网文内容；\n
			 - 🌟 4 大核心风味支柱与宏观黄金配比：\n  
			 ① 自然通透与生活烟火：基调健康明朗，坚决杜绝通篇逼仄、阴暗、压抑、冷峻或暗黑中二；多展现积极从容的生机与真实烟火气；\n  
			 ② 对白讲人话与微机锋 (30%~55%，对白干脆利落、重利益、有温度，鼓励用台词击剑直接推动剧情；彻底斩除‘老朽活了大半辈子’、‘某某有绝密要务求见’、‘抱拳领命’、‘渊渟岳峙’、‘不怒自威’等舞台剧念白与老套成语；\n  
			 ③ 轻量动线与机制推进 (40%~50%)：描写控制在 30% 以内，随动线一笔带过，机制推进展现里程碑厚度与真实代价；\n  
			 ④ 强张力卡点断章：末尾直接切在动作临界、危机爆发或悬念转折点上，坚决拔除‘大江东去’式空洞煽情总结。\n\n
			 ⑤ 靶向精修去AI 味：
			 - 拔除‘笑了笑/似笑非笑/嘴角微勾’等口癖；
			 - 将‘突然/骤然/忽然等’替换为物理声光或环境先兆铺垫（合理的可考虑保留）；
			 - 严禁‘主谋就此伏诛’等上帝视角生硬定论，转化为具象动作或留白；
			 - 将AI高频词汇/句式替换成更为合适的表述；
			 - 人物角色的神态、表情、动作必须多样化，严禁面瘫； \n
			 ⑥  读感顺畅与自然叙事：消灭长难句与拗口表达；追求自然连贯的丝滑流动感；\n 

			 【2. 唯一不可改动的 3 条刚性红线 (Strict Invariants)】:\n
			 - ① 核心因果与胜负绝对不变（谁死谁活、得了什么关键道具情报完全保留）；\n
			 - ② 人设立场与战力阶梯绝对不变（主角沉稳有谋、从容破局，不擅自暴涨境界）；\n
			 - ③ 数值台账分毫不差（金钱、年份、核心数值名必须与初稿及状态机完全一致）。\n
			
			【3. 重点重铸与去油修润清单 (Surgical Overhaul & Cleanup)】:\n
			 - 🪓 斩除戏腔与成语批发，替换为自然生动的现代脱水人话；\n
			 - ⚡ 描写脱水与节奏提速，切除冗长无聊的慢动作环境描摹与过场，直奔核心交锋；\n
			 - 🔍 顺手全能纠错：通读全篇，顺手修复错别字、标点误用与前后动作物理穿帮。\n
			 -✔ 长线防崩兜底：若草稿中出现反派脸谱化弱智叫嚣或无脑秒杀，顺手用更自然的体制机锋与真实交锋物理质感将其拉回合理水平。
			 
			 【4. 严禁违规动作 (Strict Tool Constraints)】:\n
			 - 严禁翻阅 tools/ 源码或运行 Stage 4 全书状态工具；\n
			 - 调用 write_to_file 写入 finalized/ch_xxx.md 时，严禁传入 ArtifactMetadata。\n
			 
			 【5. 标准化 4 步执行流 (Deterministic SOP)】:\n
			 1. 调用 view_file 读取输入文件；\n
			 2. 大胆执行语流重铸与通用风味打磨（确保中文字数 >= 2500）；\n
			 3. 调用 write_to_file 一次性写入输出文件；\n
			 4. 调用 run_command 运行 `python studio.py lint ch_xxx` 确认 Exit Code 0 门禁通过后立即交付退出！"
           }
         ]
       }
       ```

     - 🛡️ **【Sub-Agent 瞬态即焚与生命周期回收铁律】**：
       主控 Agent 在接收到 Sub-Agent 交付的定稿报告并验收完成后，**必须在单轮内无条件调用 `manage_subagents(Action='kill', ConversationIds=[<subagent_id>])` 立即物理销毁子代理**！杜绝会话池积压与内存残留。

     - 🛡️ **容错降级轨 (Fallback · 本地 In-Context 自审校回退)**：
       若因平台环境或网络偶发导致 Sub-Agent 无法调用，主控 Agent 立即无缝自动降级为本地自审校模式，运行 `python studio.py lint ch_xxx` 完成定稿。

  3. 🚨 **【代码级确定性质检门禁 (Deterministic Linter Gate)】**：
     - 单章中文字数 `< 2500 字`，`studio.py lint` 直接返回 **Exit Code 1 强制报错**；
     - 存在未配对中文双引号或工程代号外泄，直接返回 **Exit Code 1 强制报错**；
     - 必须修正通过门禁后，方可触发下一步检查。
  4. 👁️ **【读者阅读卡点与懵逼检测门禁 (Reader Confusion Gate)】**：
     - `studio.py lint` 在通过文学质检后，自动运行 `audit_reader_confusion.py` 执行 8 大读者视角确定性检测（幽灵实体/信息密度过载/代词迷雾区/休眠伏笔无召回/硬切场景/因果虚接/悬空对白/新概念无解释）；
     - 存在 **CRITICAL 级别阅读卡点**（如从未出场的角色突然出现），直接返回 **Exit Code 1 强制报错**；
     - WARNING 级别提示供审校特工参考修正，INFO 级别仅供人工审阅；
     - 必须修正全部 CRITICAL 项通过后，方可触发 Stage 4 状态同步。

  5. 📊 **【P2 高级量化质检雷达（确定性，零 Token，WARNING 不硬阻断）】**：
     - 🪤 **塌中段/注水检测** `python studio.py quality stall`：连续 3 章定稿却无任何状态变更（提案/流水/编年史无痕迹）即判"中段塌陷/注水"（借鉴 Novel-OS stall_detector）；在 `radar` 中作为硬问题上报；
     - ⚖️ **黄金配比量化门** `python studio.py quality ratio [-c ch_xxx]`：逐章统计 对白/推进动作/静态描写 三维占比（引号内为对白，其余按描写/动作信号词投票），对照黄金基线打分并对失衡（通篇风景、零对白、动作停滞）出 WARNING；只提示不阻断，对话章可自然上浮；
     - 🎨 **文风蒸馏** `python studio.py quality distill`（全书建指纹，存 `style_fingerprint.json`）/ `quality distill -c ch_xxx`（单章对比）：以全部定稿为正样本统计句长分布、对白密度、短句占比、段长、口癖词频（笑了笑/似笑非笑/瞳孔骤缩等），单章显著偏离全书指纹或口癖超标即提示，作为去 AI 味/防 OOC 的客观参照。

---

### 阶段四：交付与状态自同步 (Stage 4: Delivery & State Sync)
- **执行（本地先定骨架 → LLM 复核补全 → 确定性引擎合并，AI 不直接手改台账）**：
  1. **零 LLM 预填骨架**：先运行 `python studio.py draft ch_xxx`。工具 0-Token 扫描定稿，把确定性高的字段预填进 `state_inbox/ch_xxx.draft.json`：在场角色（高置信）、候选资金流水（含方向/金额/资源池/证据句）、伤势/协议/伏笔线索句、自动梗概，并附 `_review_checklist`。
  2. 调用 `novel-state-syncer`，**打开该草稿逐项复核**：确认/修正每条 `transactions_draft`（方向、金额、资源池、事由、对手方）后移入 `transactions`；润色 `synopsis`；按正文语义补全本地无法确定的字段（时空/境界/伤势/局势、`guns`/`misunderstandings`/`growth_arcs`/`timeline`）。核对 `_review_checklist` 后，**另存为正式** `state_inbox/ch_xxx.json`（删除 `_draft`/`_instructions`/`_evidence`/`_review_checklist`/`*_draft` 等草稿字段）。
     > ⚠️ 草稿 `.draft.json` 与带 `_draft:true` 的提案**绝不会被合并**（state_apply 双重拦截），只有复核后的正式 `ch_xxx.json` 才会生效。提案字段规范（详见工作区 `04_timeline_and_state/state_inbox/README.md`）：
     - `chapter`（如 `"ch_012"`）；
     - `current_state`：`time / location / present_characters[] / realm / abilities / injury / assets / equipment / situation`（只写有变化的字段）；
     - `guns[]`：`{action: plant|update|resolve, id?, name, target_ch?, plant_ch?, plan?, status?}`，id 省略时引擎自动编号 `GUN-00x`；
     - `misunderstandings[]`：`{action: plant|update|resolve, id?, parties, content, truth?, level?, target_ch?}`，自动编号 `MIS-00x`；
     - `growth_arcs[]`：`{name, action: insert|update, stage, baseline?, inciting_event?, strategy?, ultimate?}`（按角色名 upsert）；
     - `timeline[]`：`{time, event}`（按时间锚点幂等去重）；
     - `transactions[]`：复式记账流水 `{resource, delta(正收负支), type, subject, counterparty?, note?}`，余额由流水重算，**严禁手填余额**；资源池不存在时报错（先在台账登记）；
     - `synopsis`（可选）+ `chapter_title`（可选）：本章 2~3 句精炼梗概，登记进梗概脊柱（source=manual，优先于自动梗概）。
  3. 运行 `python studio.py sync ch_xxx`：流程 `[0/3]` 先由确定性合并器 `tools/state_apply.py` 校验并幂等合并提案（成功归档 `state_inbox/processed/`、失败归档 `state_inbox/failed/` 并报错），随后核验双台账平衡、道具时空轨迹并打下版本快照；
  4. 可随时运行 `python studio.py doctor`（`tools/validate_state.py`）做工作区体检：结构完整性、复式账本平衡、GUN/MIS 编号冲突、正文占位符残留；有 ERROR 时退出码为 1；
  5. 向人类导演交付定稿，并提供下一章剧情引子。

> 📌 **设计原则**：MD/JSON 台账仍是唯一真值源且对人可读；LLM 只产出结构化提案，所有校验、编号、记账、去重由零依赖 Python 引擎确定性完成（不花 Token、可重放、可审计）。合并为幂等操作，重复提交同一提案不会重复记账。