---
name: novel-profiler
description: Universal story profiler, raw input deconstructor, and dramatic dramaturg for Novel Studio (Stage 0-Prep). Extracts high-tension narrative cores, enforces must-preserve golden anchors, fills commercial blanks heuristically, and produces the unified workspace/<book>/dossier.md.
---

# SKILL — novel-profiler（故事立项与前置解构协议 · Stage 0-Prep）

> ⚡ **【执行流程】**：
> `view_file` **单次全量读取** `workspace/user_input.txt`（严禁切片） ➔ 解构故事核心与锁定黄金锚点 ➔ `write_to_file` 写入 `workspace/<书名>/dossier.md`（**严禁传递 `ArtifactMetadata`**） ➔ 输出标准回执停机。

---

## 🎯 一、 核心职责与解构规范

### 1. 核心戏核提纯
- 提炼全书核心卖点、主角驱动力与主要危机；
- 构建全书主线三幕结构（绝境起步 ➔ 规则重构 ➔ 终极破局）。

### 2. 角色与对白提炼
- 提炼主角行为逻辑与性格特征；
- 确立反派利益动机与施压方式；
- 赋予重要配角独立诉求。

### 3. 黄金锚点锁定
- 将用户指定的关键高光场景、人设细节、特异设定标记为 `[ANCHOR: MUST_PRESERVE]`，供后续阶段 100% 贯彻。

### 4. 启发式留白补齐
- 用户未提供的部分按商业网文规范自洽补齐：
  - 金手指补齐负荷代偿与限制；
  - 战力体系补齐阶层标尺；
  - 首卷规划按四分位潮汐补齐 25~40 章看点起伏。

---

## ⚡ 二、 工序流程与交付结构

1. **单次全量读取** `workspace/user_input.txt`；
2. **确定工作区**：`workspace/<书名>`；
3. **写入工件**：调用 `write_to_file`（`Overwrite: true`）写入 `workspace/<书名>/dossier.md`（**严禁传递 `ArtifactMetadata`**）；
4. **输出标准 3 行完工回执**，立即停机。

---

## 📋 三、 `dossier.md` 标准结构模板

```markdown
---
id: dossier-001
book_title: 《[书名]》
genre: [题材标签]
schema_version: novel-studio.dossier/v1
created_by: Stage 0-Prep (Architect-Profiler)
---

# 《[书名]》新书立项情报卷宗 (Dossier)

- **建议书名**：《[书名]》
- **题材标签**：[如：玄幻脑洞 / 网游穿越 / 架空异界]
- **核心主角**：[主角名]（[核心身份与人设标签]）
- **商业主线驱动**：[1~2句话总结全书核心爽点与终极追求]

---

## 📌 Part C：黄金锚点与创作红线 (Anchors & Guardrails)
- [ANCHOR-001] [用户指定的不可动摇设定或细节]
- [ANCHOR-002] [用户指定的高光场景]
- [REDLINE-001] [创作红线]

---

## 🏛️ Part A：设定与实体筑基源 (Strictly for Stage 0A)
1. **世界观公理与禁忌**：
   - [公理1：底层物理法则与世界规律]
   - [公理2：核心异常现象与生存真相]
2. **金手指与战力阶梯**：
   - [核心机制：外挂原理、触发逻辑、成长阶梯]
   - [代价与限制：负荷代偿、冷却或消耗]
   - [战力标尺：Tier 1~Tier 5 破坏力参照]
3. **核心人物矩阵（初始档案）**：
   - [主角：心理四维、核心动机、恒定称谓]
   - [宿敌/反派：利益动机、压迫标尺、爪牙配置]
   - [搭档/导师：性格毛刺、独立诉求、互称矩阵]
4. **开局实体物象**：
   - [初始地标：新手场景、危机地形]
   - [核心道具：初始资产、信物]
   - [初始阵营：敌对势力、中立势力]

---

## 📜 Part B：叙事大纲与戏剧节拍源 (Strictly for Stage 0B)
1. **全书主线三幕**：
   - 第一幕（开局起步）：[新手破局]
   - 第二幕（中盘扩张）：[走入宏大世界]
   - 第三幕（终局决战）：[终极决战]
2. **首卷 25~40 章商业潮汐规划**：
   - 阶段一「求生破局」（第 1~8 章）：[危机铺设与金手指觉醒]
   - 阶段二「悄然发育」（第 9~16 章）：[暗中发育，实力提升]
   - 阶段三「深渊探险」（第 17~24 章）：[直面冲突，展现高光]
   - 阶段四「声名鹊起」（第 25~30+ 章）：[确立地位，踏入新地图]
3. **长线伏笔与信息差雷达草案**：
   - [GUN-001] [危机倒计时]
   - [KNO-001] [致命信息差]
   - [MIS-001] [认知偏差]
```

---

## 🛑 四、 完工回执

```text
【章节工序完工回执】
- 完工阶段：Stage 0-Prep 情报解构与戏剧重塑 (Architect-Profiler)
- 产出路径：workspace/<书名>/dossier.md
- 核心指标：原始输入解构完毕 ｜ 黄金锚点已锁定 ｜ 故事性提纯与留白补齐达标 ｜ 验收放行
```
