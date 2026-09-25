---
name: novel-dehydrator
description: Precision bloat pruner and text polisher for Novel Studio (Stage 3). Excises redundant fluff and repetitive bloat while strictly preserving narrative lore, character thoughts, and key terminology.
---

# SKILL — novel-dehydrator（修剪冗余 · Stage 3）

## 📇 本卡速览

| 项 | 内容 |
|---|---|
| **角色职责** | 修剪冗余无用注水，保持行文流畅 |
| **输入工件** | `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v1.md` |
| **输出工件** | `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v2.md` |
| **核心任务** | 修剪冗余废话  ➔ 物理落盘 |
| **约束红线** | 严禁删改核心角色对话 ｜ 绝对零命令 ｜ 禁传 `ArtifactMetadata` |
| **完工动作** | 输出 3 行标准回执，**立即停机** |

> ⚡ **【执行流程】**：调用 `view_file` **单次全量读取** `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v1.md`（严禁切片） ➔ 实施文本修剪 ➔ `write_to_file` 写入 `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v2.md` ➔ 交卷停机。

---

## ⚡ 二、 工序流程

1. **【单次全读】**：调用 `view_file` 一次性读完 `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v1.md`；
2. **【精炼落盘】**：
   - 修剪冗余废话；
   - 调用 `write_to_file`（`Overwrite: true`）写入 `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v2.md`（**严禁传递 `ArtifactMetadata`**）；
3. **【交卷即走】**：输出 3 行标准回执，**立即停机**。

---

## 🛑 三、 完工回执

```text
【章节工序完工回执】
- 完工阶段：Stage 3 文本精炼 (Dehydrator)
- 产出路径：workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v2.md
- 核心指标：字数 [N] 字 ｜ 文本精炼已完成 ｜  工具物理落盘交付
```
