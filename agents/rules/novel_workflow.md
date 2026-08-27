# novel_workflow.md - 4 阶段创作流水线 SOP 与工具级联动规范

本文件规定了 Universal Novel Studio 在单章推进与版本迭代中的**标准数据流转、工具链精确调用与多状态机自同步规约**。

---

## 阶段一：灵感发散与世界架构 (Inception & World-Building)
- **输入**：用户的一句话创意、核心脑洞或粗纲。
- **执行**：
  1. 调用 `novel-director`，执行 8 维人机对齐访谈（推荐使用 `/grill-me` 深度交互）；
  2. 运行脚手架初始化命令：
     ```powershell
     python studio.py init --title "书名" --genre "题材" --protagonist "主角名"
     ```
     （工具将按题材自动匹配并安装题材档案 `00_meta/genre_profile.json`，可用 `python studio.py genre` 查看或微调）
- **输出资产**：
  - `00_meta/project_bible.md`（项目圣经，确立核心法则，无需前期样本即可由 4 大通用心流母则直接冷启动首章）
  - `00_meta/genre_profile.json`（题材档案，锁定字数/配比/调度窗口/导演指导）
  - `01_world/`（力量/法则/科技规则库与购买力防通胀锚定表）
  - `02_characters/`（角色索引表与独立人物卡）
  - `03_outlines/`（全局主线与分卷大纲）
  - `04_timeline_and_state/`（初始状态机、双台账、伏笔池与编年史）

---

## 阶段二：单章细纲推演与走向决断 (Autonomous Beats & Pacing)
- **输入**：上一章定稿、当前实时状态机与待推进剧情目标。
- **执行**：
  1. 运行语境打包器一键聚合创作全量语境（耗时 0.1 秒 · 0 Token）：
     ```powershell
     python studio.py pack ch_xxx --json [--budget 8000]
     ```
     （自动注入梗概脊柱、BM25 召回旧段落、跨章查重预警与题材导演提示；可用 `python studio.py schedule ch_xxx` 主动排期伏笔）；
  2. 调用 `novel-beats-builder`，运用 16 大变奏形态工具箱与 10 大核心看点矩阵推演单章细纲；
  3. 推演 3 个不同风味的走向分支（ABC 方案），Lead Director 自主选定最优项并写入：
     `novel_workspace/03_outlines/vol_xx/beats/ch_xxx_beats.md`。
- **输出资产**：`ch_xxx_beats.md`（包含分场景节拍、在场人物、伏笔激活与心智跃迁点）。

---

## 阶段三：正文起草与双轨独立审校流水线 (Drafting & Targeted Polishing)
- **步骤 1【初稿起草】**：
  - 调用 `novel-chapter-drafter`，分场景起草正文（标准 2500~5000 字自适应），严格恪守限制视角与 8 大心流指令；
  - 保存至 `novel_workspace/05_manuscript/vol_xx/raw_drafts/ch_xxx_v1.md`；
- **步骤 2【双轨独立审校门禁】**：
  - 🚀 **主轨 (Subagent 物理隔离审校与网文内容重铸)**：
    - 调用 `invoke_subagent` 派发专职 `novel_editor` Sub-Agent，执行【对齐 4 大通用爆款支柱、去古早戏腔、节奏脱水与顺手全能纠错】；
    - 运行 `python studio.py lint ch_xxx` 确认无硬伤（字数 >= 2500、排版正常、无标记外泄）；
    - `lint` 自动追加运行 `audit_reader_confusion.py` 执行读者视角 8 大确定性检测，CRITICAL 级别阅读卡点 → Exit Code 1 阻断；
    - 定稿写入 `novel_workspace/05_manuscript/vol_xx/finalized/ch_xxx.md`；
    - 主控验收后，单轮内立即调用 `manage_subagents(Action='kill')` 物理销毁子代理；
  - 🛡️ **降级轨 (In-Context 自审校回退)**：若 Sub-Agent 调用异常，主控自动执行本地自审校。

---

## 阶段四：交付与状态自同步 (Delivery & State Sync Engine)
- **输入**：`finalized/ch_xxx.md` 定稿文本；
- **执行**（本地先定骨架 → LLM 复核补全 → 确定性引擎合并，AI 不直接手改台账）：
  1. **零 LLM 预填骨架**：运行 `python studio.py draft ch_xxx`，0-Token 扫描定稿预填在场角色、候选资金流水（带证据句）、伤势/协议线索与自动梗概至 `state_inbox/ch_xxx.draft.json`；
  2. **LLM 语义复核**：调用 `novel-state-syncer` 打开草稿逐项复核（确认流水方向/金额/资源池，润色梗概，补全时空/境界/局势/伏笔/心智/编年史），另存为正式 `state_inbox/ch_xxx.json`；
  3. **确定性合并与快照封存**：运行一键状态自同步：
     ```powershell
     python studio.py sync ch_xxx
     ```
     （流程 `[0/3]` 由 `state_apply.py` 校验并合并提案、重算复式账本余额；`[1/3]` 由 `verify_double_ledgers.py` 校验双台账；`[2/3]` 由 `track_item_continuity.py` 核验道具轨迹；`[3/3]` 封存 `ch_xxx_done` 版本快照）；
- **输出资产**：合并后的 6 大状态真值文件、版本快照归档与最终交付章节定稿。
