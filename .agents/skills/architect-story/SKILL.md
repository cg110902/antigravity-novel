---
name: novel-architect-story
description: Universal narrative architect, commercial outline builder, and state machine energizer for Novel Studio (Stage 0B). Produces dual outlines (main_plot.md, vol_01/outline.md), energizes state/ 8 tables, and registers first volume milestone.
---

# SKILL — novel-architect-story（商业故事与状态机通电架构师专属手册 · Stage 0B）

> ⚡ **【核心定位 · 商业故事宇宙筑基与状态机通电】**：
> Stage 0B 是全书叙事大纲架构与底层状态机通电的法定执行者。
> 以 0A 交付的 `bible/` 设定、`characters/` 人物与 `entities/` 地缘道具为依托，结合 `dossier.md`（重点消费 **[Part B 叙事大纲]** 与 **[Part C 黄金锚点]**），专职交付**首卷 25~40 章商业双大纲（`outlines/`）**，全息通电 **`state/` 八表**，并添加首卷破局里程碑。

---

## 一、 商业网文故事筑基五大硬核法则（平台优质标准）

1. 🎯 **一卷一绝活与精神立意（核心卖点 + 道德共鸣）**：
   - 首卷确立明确的核心爽点与脑洞兑现机制，同时自然融入本卷精神立意（主角信念突破与人性格局升华），拒绝纯粹利己掠夺与无脑戾气；
2. 🌟 **黄金前三章极端创新与好奇心铁律（The 3-Chapter Curiosity Hook）**：
   - 🚫 **严禁陈旧俗套**：开篇三章严禁出现路人无脑嘲讽、反派刻板跳脸；严禁大段灌输世界观说明书；
   - 🎯 **前 500 字极致反差**：开篇必须以反直觉事件、迫切生死危机或反套路人设切入，让读者瞬间产生“为什么会这样/主角如何破局”的强烈好奇心；
3. ⚡ **章节绑定【单章有效事件增量 + 断章刀口】**：
   - 在 `outlines/vol_01/outline.md` 中，严禁写成无聊流水账或纯修炼假推进，每章必须标明：`ch_XXX：【核心外部行动推进 ➔ 局势实质转变】+【章末悬念刀口】`；
4. 🎭 **对手与配角去工具化**：
   - 对手行动基于利益算计或生存危机，严禁降智嘲讽；搭档具备独立诉求与性格毛刺；
5. 💣 **高能线索网布设**：
   - 在 `state/lines.json` 中埋设高戏剧张力线索：`GUN-001`（危机倒计时）、`KNO-001`（致命信息差）、`MIS-001`（外界认知反差）。

---

## 二、 执行工序与交付清单

1. **商业双大纲物理落盘**（消灭所有 `{{slot:}}` 占位符）：
   - `outlines/main_plot.md`：填实全书主线三幕脊柱、核心驱动力、开局终局与长程宏观里程碑；
   - `outlines/vol_01/outline.md`：填实首卷商业分卷大纲（商业卖点、四分位戏剧潮汐节拍、主支线追踪谱与 25~40 章逐章看点及断章刀口）。

2. **状态机八表全息通电**（依据 0A 已确立的 `characters/` 与 `entities/` 实体事实写入 `state/`，遵循 `templates/README.md` 强类型白名单字段）：
   - `state/persons.json`：注册核心人物（`p_001` 主角、`p_002` 反派/宿敌 `role: "antagonist"`, `attitude: "hostile"`、`p_003` 关键搭档等，绑定 `card` 路径与法定属性；若题材包含量化属性，同步录入 `stats` 字典）；
   - `state/places.json`：登记开局场景与首卷地标（**严守铁律：必须完整从场景卡同步 `sensory_anchor` 感官与 `environment_rules` 环境法则**，消除引擎警告并赋能正文描写）；
   - `state/items.json`：登记开局道具（必须包含 `holder`, `charges`, `max_charges`, `cost_per_use`, `durability`, `sensory_anchor`）；
   - `state/factions.json`：登记开局势力（包含 `scale_tier`, `leader`, `headquarters`, `core_assets`, `diplomacy`）；
   - `state/current.json`：填实开局第一现场（时间、地点、主角状态、在场人、初始四件套）；
   - `state/lines.json`：埋设首卷长线 `GUN-001`（反派危机倒计时/悬顶之剑）、知情差 `KNO-001`（反派阴谋信息差）、认知偏差 `MIS-001`；
   - `state/locked.json`：登记不可逆既定事实 `LOCK-001`；
   - `state/ledger.json`：依据 `vol_01/outline.md`【本卷经济与核心资源池预设】在 `pools` 中声明本题材货币池（初始余额按 `pools` 首次写入值固化为 `pools_baseline` 基线）；
   - `state/debts.json`：独立顶层数组登记开局未清算血仇/恩怨 `DEBT-001`（主角 vs 反派，含 `id/type/source_char/target_char/desc/created_ch/status`）。

3. **终端执行添加首卷战略里程碑**（依据 `vol_01/outline.md`【本卷战略里程碑排产】）：
   ```powershell
   python studio.py milestone add --title "<标题>" --target-ch <章号> --desc "<描述>" -w "workspace/<书名>"
   ```

---

## 三、 白名单与权限红线（契约边界）

- 💻 **唯一准跑命令**：`python studio.py milestone add ...`
- 📖 **准读输入**：`bible/`、`characters/`、`entities/`、`dossier.md`（重点消费 Part B 与 Part C）、`templates/`（单次全量读取，绝对严禁切片分页）；
- ✍️ **准写工件**：`write_to_file` / `replace_file_content` 写入 `outlines/`、`state/`（**绝对严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁阅读 `engine/` 源码；严禁编写任何临时脚本；
  - 严禁擅自修改 0A 已锁定的 `bible/` 设定或人物卡属性；
  - 双大纲必须消除所有 `{{slot:}}` 占位符；
  - 落盘即交付，严禁回读自验，立即输出 3 行标准回执交卷。

---

## 四、 极简标准完工回执 (统一回执 · 3 行)

```text
【章节工序完工回执】
- 完工阶段：Stage 0B 故事与状态通电 (Architect-Story)
- 产出路径：workspace/<书名>/outlines/, state/
- 核心指标：商业双大纲槽位清零 ｜ state八表全息通电 ｜ 里程碑已添加 ｜ 验收达标
```
