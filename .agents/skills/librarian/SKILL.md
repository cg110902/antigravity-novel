---
name: novel-librarian
description: Universal long-range consistency sweep librarian and retroactive ledger reconciler for Novel Studio (Stage 4D, triggered every 10 chapters, plus volume-end reconcile sweeps). Conducts 10-chapter deep sweeps, recharges items, leverages evidence candidates to salvage missing secondary entities, runs the volume-end reconcile worksheet (reconcile vol_XX --write), and outputs audit reports to log/review/.
---

# SKILL — novel-librarian（长程档案巡检协议 · Stage 4D）

> ⚡ **【执行流程】**：
> 运行打捞或对账命令 ➔ 核验档案 ➔ 自愈 Level 1 微瑕或记录 Level 2 靶点 ➔ `write_to_file` 写入 `workspace/<书名>/log/review/sweep_ch_XXX.md`（**严禁传递 `ArtifactMetadata`**） ➔ 输出标准回执停机。

---

## 🎯 一、 核心职责与红线约束

- 🚫 **绝对红线**：严禁修改任何小说正文（`manuscript/`）。
- 🚫 **绝对红线**：严禁直接手写或改动 `state/*.json` 底层数据库。
- 🚫 **绝对红线**：严禁阅读 `engine/` 源码或编写临时脚本。

---

## 🔍 二、 双轨分级自愈规则

1. **Level 1（轻量问题：自主修复）**：
   - 范围：文字错漏、偶发登场次要人物/道具缺失实体卡、非关键属性缺位；
   - 执行：直接调用 `write_to_file` 在 `characters/` 或 `entities/` 补齐卡片，或调用 `replace_file_content` 修正。

2. **Level 2（深层问题：记录上报）**：
   - 范围：大纲冲突、因果断裂、生死矛盾、位阶冲突、跨章死锁；
   - 执行：在巡检报告中记录标准死锁靶点并上报：
```markdown
- 🚨 **【Level 2 复杂深层冲突 / 重大死锁】**：
  - 冲突靶点：[具体受影响的文件、章节与实体位置]
  - 矛盾事实：[严重因果/设定矛盾事实]
  - 处置建议：提请主控委派 Stage 4C - Evolution 沙盒急救
```

---

## ⚡ 三、 工序流程

1. **步骤 1【执行打捞或对账命令】**：
   - 每 10 章巡检：`python studio.py evidence candidates ch_XXX -w "workspace/<书名>"`
   - 卷末对账：`python studio.py reconcile vol_XX --write -w "workspace/<书名>"`
   - 卷末报告第五节分流处理：
     - **⛔ 硬矛盾（生死自相矛盾）**：按 Level 2 靶点记入报告并上报；
     - **⚠️ 账面瑕疵 / 选填字段缺漏**：记入巡检小结，归入 Level 1，不阻塞流程。

2. **步骤 2【核验档案与遥测】**：
   - 调用 `view_file` **单次全量读取** `state/persons.json`、`state/items.json`、`state/synopsis.json`；
   - 验证正文出处（选跑）：`python studio.py ask "<名字>"`（最多 3 次）；
   - 检查角色生命线（离场 ≥10/15 章点名预警）与伏笔倒计时（≤3 章标记临期）。

3. **步骤 3【落盘报告与交付】**：
   - Level 1 补卡或修瑕；
   - Level 2 记入靶点卡片；
   - `write_to_file`（`Overwrite: true`）写入 `workspace/<书名>/log/review/sweep_ch_XXX.md`（卷末写入 `log/review/reconcile_vol_XX.md`，**禁传 `ArtifactMetadata`**）；
   - 输出回执停机。

---

## 🛑 四、 完工回执

- **无深层问题（正常放行）**：
```text
【章节工序完工回执】
- 完工阶段：Stage 4D 长程档案巡检 (Librarian)
- 产出路径：workspace/<书名>/log/review/sweep_ch_XXX.md
- 核心指标：长程档案已补齐 ｜ 实体状态已核实 ｜ 验收达标无冲突
```

- **发现重大冲突（Level 2 警报）**：
```text
【章节工序完工回执】
- 完工阶段：Stage 4D 长程档案巡检 (Librarian)
- 产出路径：workspace/<书名>/log/review/sweep_ch_XXX.md
- 异常汇报：
  - [Level 2 复杂深层冲突]：<一句话靶点与矛盾描述> ➔ 提请主控委派 Stage 4C - Evolution 沙盒急救
```
