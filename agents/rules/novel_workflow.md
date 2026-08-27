# novel_workflow.md - 4 阶段全自动自愈创作流水线 SOP 与工具级联动规范

本文件规定了 Universal Novel Studio 在单章推进与版本迭代中的**标准数据流转、自愈重试闭环、工具链精确调用与多状态机自同步规约**。

> 🎯 **人机分工与全自动自愈准则 (Autonomous Self-Healing Standard)**：
> - **人类职责 (Human Role)**：仅负责开书时的核心方向设定，以及每章最终定稿 `finalized/ch_xxx.md` 的终审放行；
> - **Agent 职责 (Agent Pipeline)**：Stage 2 (细纲) $\to$ Stage 3 (起草+精修+质检) $\to$ Stage 4 (状态自同步+台账核验+快照) 全自动化执行；
> - **🔄 遇阻自愈机制 (Auto-Repair on Failure)**：流水线任意环节若触发门禁报错 (Exit Code != 0)、读者卡点 (CRITICAL Confusion) 或台账不平，**必须在 Agent 内部自动打回重做、微创修复并再次质检，直至 100% 达标（0 Errors / 0 Warnings），方可向人类交付终审**。

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

## 阶段二：单章细纲自主推演与决断 (Autonomous Beats & Pacing)
- **输入**：上一章定稿、当前实时状态机与待推进剧情目标。
- **全自动执行流**：
  1. 运行语境打包器一键聚合创作全量语境（耗时 0.1 秒 · 0 Token）：
     ```powershell
     python studio.py pack ch_xxx --json [--budget 8000]
     ```
     （自动注入梗概脊柱、BM25 召回旧段落、跨章查重预警与题材导演提示；系统自动运行 `python studio.py schedule ch_xxx` 主动排期待引爆/回唤伏笔）；
  2. 调用 `novel-beats-builder`，运用 16 大变奏形态工具箱与 10 大核心看点矩阵推演单章细纲；
  3. 自主决断最优张力走向分支并写入：`novel_workspace/03_outlines/vol_xx/beats/ch_xxx_beats.md`；
  4. 自动校验 Beats 4D 积木与前置因果无误后，**无缝直接触发 Stage 3**，无需等待人类确认。
- **输出资产**：`ch_xxx_beats.md`（包含分场景节拍、在场人物、伏笔激活与心智跃迁点）。

---

## 阶段三：正文起草与自愈审校门禁 (Drafting & Self-Healing Polish Loop)
- **步骤 1【初稿起草】**：
  - 调用 `novel-chapter-drafter`，分场景起草正文（标准 2500~5000 字自适应），严格恪守限制视角与 8 大心流指令；
  - 保存至 `novel_workspace/05_manuscript/vol_xx/raw_drafts/ch_xxx_v1.md`；
- **步骤 2【独立审校与去戏腔重铸】**：
  - 派发专职 `novel_editor` Sub-Agent 执行【对齐 4 大通用爆款支柱、去古早戏腔、节奏脱水与顺手全能纠错】；
  - 输出初版定稿至 `novel_workspace/05_manuscript/vol_xx/finalized/ch_xxx.md`；
  - 物理销毁 Sub-Agent；
- **步骤 3【全维质检与自愈重做闭环 (Self-Healing Loop)】**：
  - 自动化运行多维门禁：
    ```powershell
    python studio.py lint ch_xxx --voice
    python studio.py confusion ch_xxx
    ```
  - 🔄 **自愈重试判断机制**：
    - 若 `lint` 出现错误（字数 < 2500、引号不匹配、内部标记泄露、严重 OOC 声纹偏离）或 `confusion` 出现 `CRITICAL` 级阅读卡点：
      1. 自动提取错误上下文与 `python studio.py rx ch_xxx` 手术处方单；
      2. 针对性执行局部微创重写或文本重铸；
      3. 重新运行 `lint` 与 `confusion`；
      4. **循环自愈直至 Exit Code 0 且 0 CRITICAL 错误全部通过为止**（系统内置最大重试保护上限 3 次）；
- **输出资产**：100% 达标的 `finalized/ch_xxx.md`。

---

## 阶段四：状态确定性自同步、台账核验与快照封存 (State Sync Engine)
- **输入**：达标的 `finalized/ch_xxx.md` 定稿文本；
- **全自动执行流**：
  1. **零 LLM 预填骨架**：运行 `python studio.py draft ch_xxx`，0-Token 扫描定稿预填在场角色、候选资金流水（带证据句）、伤势/协议线索与自动梗概至 `state_inbox/ch_xxx.draft.json`；
  2. **语义级自动复核**：基于定稿正文确认流水方向/金额/资源池，润色梗概，补全时空/境界/局势/伏笔/心智/编年史，另存为正式 `state_inbox/ch_xxx.json`；
  3. **确定性合并与台账审计**：
     ```powershell
     python studio.py sync ch_xxx
     ```
     （`state_apply.py` 幂等合并提案；`verify_double_ledgers.py` 校验双台账；`track_item_continuity.py` 核验道具轨迹；封存 `ch_xxx_done` 版本快照）；
  4. 🔄 **台账自愈重试**：
     - 若 `sync` 报错（如资金借贷不平、GUN 编号冲突、时空不连续）：
       1. 解析报错日志；
       2. 自动修正 `state_inbox/ch_xxx.json` 对应字段；
       3. 重新执行 `sync` 直至通过；
  5. 运行 `python studio.py doctor` 确保全局 0 错误 0 警告；
- **阶段交付与终审呈现**：
  - 调用 `present_file` 在人类工作区直接展开 `finalized/ch_xxx.md`；
  - 输出本章字数、黄金配比、核心高光提要与状态变动简报，提请人类作家完成终审放行。
