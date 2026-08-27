# Universal Novel Studio (全题材自适应长篇网文 AI 协同创作工作站)

> 🚀 **专为 Google Antigravity 原生环境与 Gemini 模型深度定制的 Agent-First 全题材网文工程架构**  
> 🌟 **核心设计哲学**：**5条通用铁律 · 17种题材自适应 · 长线大格局叙事 · Antigravity 原生特工流 · 确定性质检门禁 · 状态双台账绝对自洽**

> ⚠️ **v2 全题材自适应**：本工作站支持 17 种内置题材（玄幻/武侠/都市/科幻/悬疑/恐怖/历史/规则怪谈/无限流/言情/游戏/体育/军事/轻小说/现实主义/治愈系/通用）。文风/基调/配比/字数/词表全部由 `genre_profile.json`（题材档案）动态控制，不再一刀切。真正的通用铁律仅5条（限制视角/信息差/动机真实/因果一致/无工程标记）。

---

## 🗺️ 一、 五层原生工程架构地图 (Architecture SSOT)

本系统将文学创作解构为**确定性工程流水线**，充分发挥 **Gemini 百万级上下文理解** 与 **Antigravity 高性能并发特工调度** 优势：

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. 顶级总控层: AGENTS.md (最高战略指挥法典)                                              │
│    - 4 阶段闭环 SOP、Sub-Agent 物理隔离审校门禁、瞬态即焚生命周期管理、防工程标记外泄铁律│
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 2. 外部总览与调度层: README.md & novel_config.yaml & studio.py (统一总控与 CLI)         │
│    - README.md: 全景架构地图、Antigravity × Gemini 实战作战手册 (本文档)                │
│    - novel_config.yaml: 全局声明式配置中心 (工程配置，题材参数由 genre_profile 控制)     │
│    - studio.py: 极简统一调度器 (pack / lint / sync / radar / rollback / export / test) │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 3. 中台文学通用法典: agents/rules/ (5 大全题材底层规范 · 知识库)                       │
│    - novel_style.md: v2 自适应文风规范 (5条通用铁律 + 题材档案覆盖，废除一刀切基调禁令)  │
│    - novel_long_arc_and_pacing.md: 宏观三级节奏、能力阶梯锁(全题材12种对应表)、经济防通胀│
│    - novel_brainhole_and_pacing.md: 全题材12大看点维度、爽点公式、16种题材爽点侧重表    │
│    - novel_anti_ooc.md: 角色一致性、心智阶段演进、能力一致性(8种题材对应)、信息差闭环    │
│    - novel_workflow.md: 4 阶段 SOP 工具级联动、状态机可插拔、自动快照封存机制           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 4. 前线专职特工技能: agents/skills/ (5 大专业化行动 Runbooks)                          │
│    - novel-director: 总策划 (8 维人机对齐访谈、世界观创生、题材档案匹配)               │
│    - novel-beats-builder: 编剧 (语境打包、4 维积木拼装、13大看点维度、张力走向自主决断) │
│    - novel-chapter-drafter: 主笔 (影视级分场景起草、基调自适应4模式、真实物理代价)       │
│    - novel-continuity-guard: 审校官 (题材档案文风规范、念白感检测而非单词禁用、全能纠错) │
│    - novel-state-syncer: 同步官 (10+大事实突变提炼、power_level通用字段、状态组件可插拔) │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 5. 底层数据与工具基座: novel_workspace/ & templates/ & tools/ (真值源+母版+工具箱)      │
│    - novel_workspace/: 唯一事实真值源 (SSOT: 设定/大纲/状态机/手稿/快照)               │
│    - templates/: 全题材 6 大官方标准母版中心 (圣经/世界/人物/大纲/细纲/状态机)          │
│    - tools/: 33 个 Python 经典算法纯函数工具箱 (复式记账/图论/时空追踪/声韵分析/读者懵逼)│
│    - tools/genre_profiles/: 17 种题材档案 JSON (基调/配比/词表/聚类/导演指导)          │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ 二、 统一 CLI 命令行调度手册 (`studio.py`)

系统提供极简统一的 CLI 命令集，由主控 Agent 直接通过 `run_command` 高速调度：

```powershell
# 0. 【项目状态】查看全书进度大盘、资产存量、已完成章节与活跃伏笔池
python studio.py status

# 1. 【工作区自检】运行健康自检 (结构完整性/台账平衡/占位符残留/快照完整性)
python studio.py doctor

# 2. 【题材档案】查看或微调当前题材配置档案 (基调策略/配比基线/状态组件/词表/聚类/导演指导)
python studio.py genre
python studio.py genre --list           # 列出全部17种内置题材
python studio.py genre --genre "科幻末世" --json  # 预览某题材匹配结果

# 3. 【语境打包】一键装载指定章节的创作全量语境 (支持 --json 格式与 --budget 预算裁剪，Agent 首选)
python studio.py pack ch_011 --json --budget 8000

# 4. 【伏笔主动调度】为指定章节 Beats 细纲主动排期待引爆/回唤/沉睡伏笔
python studio.py schedule ch_011

# 5. 【记忆引擎】梗概脊柱补全 / BM25 资料员召回 / 跨章雷同与重复检测
python studio.py memory spine                     # 扫描定稿自动补全章节梗概脊柱
python studio.py memory recall "黑市 芯片 伏笔"   # BM25 资料员相关旧段落召回
python studio.py memory repeat                    # 跨章重复检测

# 6. 【全维质检门禁】对指定章节运行读感·体验·造句·标记外泄门禁 + 读者懵逼检测
#    字数阈值由 genre_profile.word_count.min 控制 (通用兜底1800，各题材不同)
python studio.py lint ch_011 [--voice]

# 7. 【读者懵逼检测】单独运行读者阅读卡点与认知断层检测 (8 大确定性算法)
python studio.py confusion ch_011

# 8. 【微创诊断】即时输出该章分层靶向微创手术处方与切片建议 (0 落盘)
python studio.py rx ch_011

# 9. 【脱水对比】初稿 (raw_drafts) vs 定稿 (finalized) 质量提升与颗粒度分析
python studio.py diff ch_011

# 10. 【高级质检雷达】塌中段注水检测 / 黄金配比量化门 / 文风蒸馏指纹
#     配比基线由 genre_profile.ratio_baseline 控制
python studio.py quality stall                   # 连续无状态变更塌中段注水检测
python studio.py quality ratio -c ch_011         # 对白/推进/描写三维配比量化
python studio.py quality distill                 # 全书文风指纹蒸馏或单章偏离度比对

# 11. 【事实预提取】0-Token 快速预提取单章资金流水、伤势、重点道具与出场角色
python studio.py facts ch_011

# 12. 【零 LLM 提案骨架】扫描定稿章节预填在场角色/候选流水/线索句/梗概至 .draft.json
python studio.py draft ch_011

# 13. 【确定性状态合并】将 state_inbox 中的结构化变更提案幂等合并进状态真值文件
python studio.py apply [--dry-run]

# 14. 【状态自同步】一键合并提案、校验双台账平衡(如有经济体系)、核验道具轨迹并自动打下版本快照
python studio.py sync ch_011

# 15. 【全维雷达巡检】一键运行全书 14 项工程雷达总控巡检
python studio.py radar

# 16. 【全书手稿导出】一键合并全书定稿章节为出版级 Markdown 或 TXT 手稿
python studio.py export [--txt]

# 17. 【版本快照与回滚】管理多分支与历史状态快照
python studio.py snapshots                       # 列出所有历史版本快照
python studio.py snapshot my_milestone           # 手动创建指定名称快照
python studio.py rollback ch_010_done --clean-drafts # 一键回滚状态机并可选清理孤立手稿

# 18. 【开新书初始化】一键为任意题材小说生成标准化全套脚手架母版 (自动匹配题材档案)
python studio.py init --title "书名" --genre "题材" --protagonist "主角名"

# 19. 【工程自检套件】运行自动化单元测试套件
python studio.py test
```

---

## 🤖 三、 Antigravity × Gemini 协同加速作战指南 (Agent Execution SOP)

本工作流为 **Gemini 原生认知特性** 与 **Antigravity 平台能力** 进行了深度适配，AI 在执行各阶段时遵循以下标准动作：

```
 ┌────────────────────────────────────────────────────────┐
 │       Stage 1: 新书架构与世界观创生 (Novel Inception)   │
 │   - Antigravity 交互: 调用 novel-director，与人类导演对齐│
 │   - 题材匹配: init 自动匹配 genre_profile (17种内置题材) │
 │   - 输出基座: 生成 project_bible, world_rules, 人物卡   │
 └──────────────────────────┬─────────────────────────────┘
                            │ (开启单章推进)
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │   Stage 2: 细纲推演与最优张力走向自主决断 (Autonomous)  │
 │   - Gemini 优势: 1次 pack 装载全量语境(含题材档案)，算力全留给剧情 │
 │   - 4 维积木拼装: 镜头入口 + 推进引擎 + 意外折叶 + 余韵│
 │   - 13大看点维度: 认知破局/价值兑现/利益交锋/情感共鸣/日常治愈等 │
 │   - 自主决断: 推演 3 个走向分支，选定张力与反差最强选项│
 └──────────────────────────┬─────────────────────────────┘
                            │ (写入 beats/ 细纲，直通起草)
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │   Stage 3: 正文起草与 Sub-Agent 靶向精修 (Draft & Audit)│
 │   1. 初稿起草: 分场景起草 (字数由 genre_profile 控制)   │
 │      - 基调自适应: dark_preferred题材(悬疑/恐怖)严禁强行明快化 │
 │      - 5条通用铁律: 限制视角/信息差/动机真实/因果一致/无工程标记 │
 │   2. 物理隔离审校: invoke_subagent 派发 novel_editor   │
 │      - 题材档案文风规范 + 念白感检测(非单词禁用) + 全能纠错 │
 │      - 运行 studio.py lint 确认 Exit Code 0 通过门禁   │
 │      - lint 自动追加 读者懵逼检测，CRITICAL → 阻断     │
 │   3. 瞬态即焚: 验收定稿后单轮内调用 manage_subagents 销毁│
 └──────────────────────────┬─────────────────────────────┘
                            │ (通过质检门禁)
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │   Stage 4: 状态自同步、版本快照与终审交付 (Sync & Done) │
 │   1. 骨架预填: 运行 studio.py draft ch_xxx 预填草稿    │
 │   2. 语义复核: novel-state-syncer 复核补全后另存为     │
 │      state_inbox/ch_xxx.json 结构化提案 (AI 不手改台账) │
 │      - power_level 通用字段 (realm→power_level)        │
 │      - 状态组件可插拔 (无经济题材跳过 economy_ledger)   │
 │   3. 确定性合并: 运行 python studio.py sync ch_xxx      │
 │      - state_apply 自动合并提案 (如有经济体系则重算复式账本) │
 │      - 校验双台账平衡、道具流转轨迹并封存版本快照       │
 │   4. 交付备忘: 呈递【章节定稿】与【状态更新备忘】      │
 └────────────────────────────────────────────────────────┘
```

---

## 🛡️ 四、 AI 创作核心铁律与防翻车门禁 (Deterministic Safeguards)

### 5 条通用铁律 (所有题材不可违反)
1. **限制视角不越界**：严格锁定 POV 角色的物理视野与认知边界，严禁上帝视角。
2. **信息差自洽**：谁知道什么前后一致，角色不能基于未获知信息做决策。
3. **角色动机真实**：每个角色行为有合乎性格/立场/利益的动机，严禁工具人化。
4. **前后因果一致**：设定/规则/时间线/道具权属前后一致，严禁吃设定。
5. **无工程标记外泄**：正文不出现 GUN-001/MIS-001/Stage 1/占位符等内部标记。

### 题材自适应门禁 (由 genre_profile 控制)
1. 🚨 **字数硬伤门禁**：
   - 单章正文中文字数必须达到 `genre_profile.word_count.min`（通用兜底 1800 字，玄幻默认 2500，治愈系可低至 1500）；
   - 低于阈值，`studio.py lint` 直接返回 **Exit Code 1 强制报错阻断**。
2. 🗡️ **能力阶梯锁与真实物理动线**（v2: 战力→能力，全题材通用）：
   - 单卷严格限制大层级跨越（玄幻=境界/武侠=武功/科幻=异能/都市=资源权位/悬疑=认知/言情=情感深度等）；
   - 严禁无脑秒杀；每次出手必有真实的生理损耗、器物磨损、体能代偿与环境互动阻力。
3. 💰 **复式记账与货币防通胀**（有经济体系的题材适用，由 `genre_profile.economy_required` 控制）：
   - 严格遵循民生购买力锚定表；
   - 正文中涉及的具体数额必须与 `economy_ledger.json` 双台账保持分毫不差的算术自洽；
   - 无经济体系的题材（纯悬疑/纯爱/恐怖/治愈系）跳过此项。
4. 🛡️ **Sub-Agent 瞬态即焚与 100% 自动生命周期回收**：
   - 主控在接收到定稿报告并确认通过后，**必须在单轮内立即调用 `manage_subagents(Action='kill')` 物理销毁子代理**。
5. 👁️ **读者阅读卡点与懵逼检测门禁**：
   - `studio.py lint` 在文学质检后自动运行 `audit_reader_confusion.py`，执行 8 大读者视角确定性检测；
   - 存在 CRITICAL 级别阅读卡点 → Exit Code 1 强制阻断。
6. ⚔️ **战斗陈词检测**（仅 `combat_heavy=true` 题材启用）：
   - 玄幻/武侠/科幻/军事/游戏/体育等战斗密集型题材启用战斗脸谱化词汇检测；
   - 言情/治愈/悬疑/恐怖等非战斗题材自动跳过。

---

## 🚀 五、 全题材开新书与即插即用指南 (Zero-Cost Reusability)

本工作站除 `novel_workspace/` 保存当前特定小说作品的数据外，其余所有工具和法典均为**100% 通用基础设施**。开启一本全新题材小说极为简单：

1. **一键初始化新书脚手架**（自动匹配题材档案）：
   ```powershell
   python studio.py init --title "星际深渊：我有一艘反重力打捞船" --genre "科幻末世 / 深空悬疑" --protagonist "陈昂"
   ```
2. **确认题材档案**：运行 `python studio.py genre` 查看当前匹配的题材档案，如需微调可编辑 `novel_workspace/00_meta/genre_profile.json`；
3. **声明式配置**：在 `novel_config.yaml` 中配置工程参数（字数/配比/基调由题材档案控制，不需在此配置）；
4. **开启创作**：调用 `novel-director` 进行设定推演与世界观生成，无缝开启全新百万字长篇创作！

### 17 种内置题材速查
运行 `python studio.py genre --list` 查看完整列表：

| 类别 | 题材 |
|------|------|
| 东方玄幻 | xuanhuan(玄幻/仙侠/系统)、wuxia(武侠/江湖)、history(历史/架空/种田权谋) |
| 现代都市 | urban(都市/异能/职场商战)、realism(现实主义/年代/知青) |
| 科幻未来 | scifi(科幻/机甲/星际/赛博朋克/末世)、lightnovel(轻小说/异世界转生) |
| 悬疑恐怖 | mystery(悬疑/推理/惊悚犯罪)、horror(恐怖/克苏鲁/灵异/心理恐怖) |
| 规则生存 | rulebound(规则怪谈/SCP/异常)、infinite(无限流/轮回/任务世界) |
| 情感日常 | romance(言情/纯爱/甜宠/婚恋)、iyashikei(治愈系/日常/慢生活/田园美食) |
| 竞技军事 | gaming(游戏/电竞/网游/直播)、sports(体育/竞技)、military(军事/战争/军旅/谍战) |
| 通用兜底 | generic(全题材通用自适应) |
