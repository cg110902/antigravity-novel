---
name: novel-state-syncer
description: >-
  小说状态自同步与记忆沉淀技能。在章节定稿后，自动提炼故事 10+ 大维度变动（含开放式自定义），产出一份结构化状态变更提案 JSON（state_inbox/ch_xxx.json），交由确定性引擎 state_apply.py 幂等合并进 current_state/timeline/伏笔池/误会台账/心智台账/复式账本并自动记账、打快照。AI 只提案、不手写台账。适用场景：状态同步、更新状态机、推进时间线、同步伏笔、沉淀记忆、打快照。
---

# 故事状态自同步技能 (Novel State Syncer)

本技能作为小说的状态机与归档器，负责在每一章定稿交付后，将文本中的动态变化提炼沉淀为结构化记忆，并调用校验工具确保双台账与道具轨迹绝对自洽，防止长篇创作后期吃设定。

> 💡 **【开放式状态追踪与全面沉淀原则】**：
> 本技能所列的突变维度与量化资源类别，**均为启发式参考（包含但不限于文中列举的类型）**。同步官 Agent **完全可以且被鼓励根据小说题材特性自由拓展与沉淀其他关键状态维度（如星际战力指数、San值深度、领地发展指数等）**；所提取的事实与策略完全可以是示例之外的例外，确保全书记忆真实严密！

---

## 执行步骤

### 1. 0-Token 事实线索预扫描与 10 大突变提炼 (Pre-Scan & State Mutation Extraction)
1. **预提取高敏线索**：先运行 `python studio.py facts ch_xxx` 获取正文中出现的货币交易句、出场角色、伤势负荷、重点道具与协议；
2. **结合上下文提炼清单**：精准提炼以下事实突变（10 个常用维度 + 1 个开放式自定义，按题材自由增删）：

1. 📍 **[时空位移与环境迁移]**：更新故事发生时间点、具体物理地点、周遭环境阻力与地貌特征；
2. ⚔️ **[能力 / 战力 / 状态变化]**：新突破或能力升级、技能/装备获取、出手后的身心负荷、暗伤、装备或弹药/能源消耗（按题材：修炼境界、异能评级、义体损耗、舰战损伤等）；
3. 🧮 **[资产 / 货币 / 资源流水]**：本书货币与资源的实际收支、点数/配额/积分增减、投资收益与债务应收账目；
4. 🗝️ **[道具 / 凭证 / 契约权属]**：新获关键道具、协议/合同签订、信物或证据交付流转、抵押/封存状态变更；
5. 🤝 **[人际关系与阵营洗牌]**：敌友阵营转换、利益捆绑盟友确立、主从关系或嫌隙产生；
6. 👁️ **[情报暗战与认知差]**：谁掌握了核心秘密、谁产生了重大信息误判（MIS）、谁的马甲被怀疑；
7. 🧠 **[心智阶段与成长跃迁]**：角色的心理防线、信任边界、行事底线与心智阶段（Stage 0/1/2...）跃迁；
8. 🕸️ **[伏笔网络与因果涟漪]**：新埋下的中长线暗流（Planted）、推进激化（Reminded）与引爆闭环（Resolved）；
9. 🏛️ **[格局与规则变迁]**：势力/组织关系重组、官方管制/通缉/法令变动、地下或幕后力量洗牌；
10. 🔮 **[核心机制与长线设定沉淀]**：主角外挂/系统/特殊能力的进度结算、关键资源/词条更新、已掌握情报与待解悬念的记忆沉淀；
11. 🌟 **[开放式自定义维度]**：根据题材自由提取特殊状态（如星际舰队战损、污染值/San值、赛博义体磨损、阵营声望等）。

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
  - 💡 **LLM 只提流水，不碰余额**：正文中的货币、属性点、技能点、灵力值、San值、信用点等量化收支，由 State Syncer 语义提炼为 `transactions[]` 流水（只写 `delta` 正收负支 + 事由）；
  - **余额由确定性引擎从流水重算**，LLM 严禁手填 `balance_after`/`current`；引用未登记的资源池会被引擎报错（须先在台账登记）。Python 引擎负责复式平衡稽核，杜绝算术算错或凭空暴富。

### 3. 产出一份结构化变更提案（AI 提议 → 引擎合并，不手写台账）
**不要**直接 `write_to_file` 改 6 大状态文件。改为把上面提炼的全部突变写成**一份** JSON 提案，保存到：
`novel_workspace/04_timeline_and_state/state_inbox/ch_xxx.json`

提案 schema（`novel-studio.state-mutation/v1`），只填有变化的字段：
```json
{
  "schema": "novel-studio.state-mutation/v1",
  "chapter": "ch_012",
  "current_state": {"time": "第三日·夜", "location": "黑市废仓库", "present_characters": ["陈昂", "老周"], "realm": "...", "injury": "...", "assets": "...", "situation": "..."},
  "guns": [
    {"action": "plant", "name": "铁壁公司内部账本", "target_ch": 18, "plan": "用账目诱敌自曝"},
    {"action": "update", "id": "GUN-001", "status": "Reminded"},
    {"action": "resolve", "id": "GUN-002"}
  ],
  "misunderstandings": [
    {"action": "plant", "parties": "陈昂/老周", "content": "老周以为陈昂不知芯片价值", "truth": "陈昂已解码", "level": "2 级", "target_ch": 15}
  ],
  "growth_arcs": [
    {"name": "陈昂", "action": "update", "stage": "Stage 1【信息做庄】", "inciting_event": "首次主动布局反制"}
  ],
  "timeline": [{"time": "第三日·夜", "event": "黑市交易破裂，陈昂反将一军"}],
  "transactions": [
    {"resource": "standard_currency", "delta": -30, "type": "expense", "subject": "购入情报", "counterparty": "黑市掮客老周"}
  ],
  "synopsis": "本章 2~3 句精炼梗概（可选，登记进梗概脊柱防场景重复）",
  "chapter_title": "黑市交锋（可选）"
}
```
> 规则：`guns/misunderstandings` 的 `id` 可省略，引擎自动编号 `GUN-00x`/`MIS-00x`；`resolve` 自动置为已回收/已澄清；`timeline` 幂等去重；重复提交同一提案不会重复记账。

### 4. 一键合并、校验与快照存档 (Deterministic Engine Gatekeeper)
运行单条命令，引擎会**自动完成**合并提案 → 复式记账 → 台账校验 → 打快照：
```bash
python studio.py sync ch_xxx
```
- sync 的 `[0/3]` 先由 `state_apply.py` 合并提案：成功移入 `state_inbox/processed/`，校验失败移入 `state_inbox/failed/` 并打印原因（按原因修提案后重跑即可）；
- 随后自动核验双台账平衡、道具时空轨迹，封存 `ch_xxx_done` 快照。
- 如需单独体检工作区（结构/账本/编号/占位符），运行 `python studio.py doctor`（有 ERROR 退出码为 1）。
- 注：State Syncer **不要**自己翻阅 `tools/*.py` 源码，也不要手动改台账文件；一切以命令输出为准。

### 5. 状态交付备忘
向用户交付【事实突变声明与记忆更新摘要】（基于 sync 输出的合并结果）以及【下一章情节引子】。
