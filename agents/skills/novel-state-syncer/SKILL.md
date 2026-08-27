---
name: novel-state-syncer
description: >-
  小说状态自同步与记忆沉淀技能。在章节定稿后，自动提炼故事 7 大维度变动，回写更新 current_state.md、推进 timeline.md、同步 chekhov_guns.md 伏笔池、misunderstandings.md 误会台账与 character_growth_arcs.md 心智台账，并打下版本快照。适用场景：状态同步、更新状态机、推进时间线、同步伏笔、沉淀记忆、打快照。
---

# 故事状态自同步技能 (Novel State Syncer)

本技能作为小说的状态机与归档器，负责在每一章定稿交付后，将文本中的动态变化提炼沉淀为结构化记忆，并调用校验工具确保双台账与道具轨迹绝对自洽，防止长篇创作后期吃设定。

> 💡 **【开放式状态追踪与全面沉淀原则】**：
> 本技能所列的 7 大突变维度与量化资源类别，**均为启发式参考（包含但不限于文中列举的类型）**。同步官 Agent **完全可以且被鼓励根据小说题材特性自由拓展与沉淀其他关键状态维度（如星际战力指数、San值深度、领地发展指数等）**；所提取的事实与策略完全可以是示例之外的例外，确保全书记忆真实严密！

---

## 执行步骤

### 1. 0-Token 事实线索预扫描与 10 大突变提炼 (Pre-Scan & State Mutation Extraction)
1. **预提取高敏线索**：先运行 `python studio.py facts ch_xxx` 获取正文中出现的货币交易句、出场角色、伤势负荷、重点道具与协议；
2. **结合上下文提炼清单**：精准提炼以下 10 大事实突变（允许根据题材自由拓展）：

1. 📍 **[时空位移与环境迁移]**：更新故事发生时间点、具体物理地点、周遭环境阻力与地貌特征；
2. ⚔️ **[能力/境界/战力损耗]**：新突破境界、习得词条/神通、真气调息负荷、经脉暗伤与兵刃磨损；
3. 🧮 **[资产/货币/点数流水]**：金银铜钱实际收支、贡献分/点数增减、商业投资与债务应收账目；
4. 🗝️ **[道具/凭证/契约权属]**：新获机缘道具、契约文书签订、信物交付流转、抵押物交割；
5. 🤝 **[人际关系与阵营洗牌]**：敌友阵营转换、利益捆绑盟友确立、主从关系或嫌隙产生；
6. 👁️ **[情报暗战与认知差]**：谁掌握了核心秘密、谁产生了重大信息误判（MIS）、谁的马甲被怀疑；
7. 🧠 **[心智阶段与成长跃迁]**：角色的心理防线、信任边界、行事底线与心智阶段（Stage 0/1/2...）跃迁；
8. 🕸️ **[伏笔网络与因果涟漪]**：新埋下的中长线暗流（Planted）、推进激化（Reminded）与引爆闭环（Resolved）；
9. 🏛️ **[地缘格局与秩序变迁]**：门阀家族利益重组、官府路引/通缉令变动、地下势力洗牌；
10. 🔮 **[模拟世界与特殊机制沉淀]**：模拟世数结算、词条总数更新、避坑手札记忆沉淀与心障调和；
11. 🌟 **[开放式自定义维度]**：根据题材（星际舰队战损、克苏鲁San值残留、赛博义体磨损等）自由提取特殊状态。

### 2. 多维台账与心智档案动态同步 (伏笔 + 误会 + 心智演进 + 资产与点数)
- **伏笔池 (`chekhov_guns.md`)**：
  - 新增埋下的伏笔标记为 `Planted`（包含预期引爆章节）；
  - 推进/激化的伏笔更新为 `Reminded`；
  - 彻底引爆/回收的伏笔更新为 `Resolved`。
- **误会台账 (`misunderstandings.md`)**：
  - 新增信息差/误会记录；
  - 记录误会发酵程度与预定引爆节点。
- **心智演进台账 (`character_growth_arcs.md`)**：
  - 记录本章触发的认知破裂与心智跃迁事件；
  - 更新角色当前心智阶段与防御机制。
- **核心资产与量化资源账本 (`economy_ledger.json`)**：
  - 💡 **全权委托 LLM 语义识别与流水记账**：正文中的货币、加点属性点、技能点、灵力值、San值、信用点、贡献分、阵法/装备修复进度等量化数值，由 State Syncer (LLM) 凭借上下文深度语义提炼登记，记录 `delta`、`balance_after` 与事由；
  - Python 脚本负责执行复式平衡稽核，确保任何点数与货币绝不出现算术算错或凭空暴富。

### 3. 同步回写文件
- 覆盖更新 `novel_workspace/04_timeline_and_state/current_state.md`（含在场角色最新心智阶段与资产状态）；
- 追加事件日志到 `novel_workspace/04_timeline_and_state/timeline.md`；
- 同步更新 `character_growth_arcs.md`、`economy_ledger.json`、`chekhov_guns.md` 与 `misunderstandings.md`。

### 4. 运行交叉一致性校验与快照存档 (Tool Gatekeeper)
回写完成后，并发运行本地经典算法工具完成全维一致性门禁核验：
```powershell
# 1. 校验双台账与状态机交叉一致性
python tools/verify_double_ledgers.py --json

# 2. 校验关键道具时空轨迹
python tools/track_item_continuity.py --json

# 3. 校验伏笔因果 DAG 拓扑与闭环
python tools/audit_plot_dag.py --json

# 4. 校验全书资产复式流水记账
python tools/audit_economy_ledger.py --json

# 5. 巡检核心角色艾宾浩斯记忆衰减与掉线预警
python tools/track_character_decay.py --json

# 6. 校验读者阅读卡点与懵逼检测 (8 大确定性算法)
python tools/audit_reader_confusion.py -c ch_xxx --json

# 7. 一键创建版本快照归档
python tools/state_inspector.py --snapshot ch_xxx_done
```

### 5. 状态交付备忘
向用户交付【事实突变声明与记忆更新摘要】以及【下一章情节引子】。
