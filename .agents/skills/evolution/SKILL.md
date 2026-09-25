---
name: novel-evolution
description: Universal story evolution, setting refactoring, retcon surgery, emergency pipeline fixer, and state reconciler for Novel Studio (Stage 4C - Evolution). Handles mid-story change requests and urgent manuscript/plot conflict fixes using simulate impact for causal topology risk assessment, automated snapshot defenses, surgical manuscript edits via direct tool calls, and state reconciliation in an isolated sandbox.
---

# SKILL — novel-evolution（剧情外科与死锁急救协议 · Stage 4C）

> ⚡ **【执行流程】**：
> 测算因果影响 ➔ 建立快照备份 ➔ 工具精准修改 ➔ 运行 `check` 确认 0 errors ➔ 输出标准回执停机。

---

## 🎯 一、 核心职责与业务范围

1. **Level 2 复杂深层冲突处置**：跨章生死冲突、因果断裂、位阶冲突、跨卷伏笔死锁；
2. **流水线死锁急救**：细纲与设定硬碰撞导致 `finalize` 或 `sync` 阻断等故障；
3. **设定演进与重构（Scenario C）**：中途改设定、改人设、修改历史章节、添加新体系；
4. **本章灵感审查与落地（Scenario B [3]）**：审查灵感是否冲突大纲、战力与里程碑，执行大纲微调或全息平账。

---

## 📚 二、 查阅文件指引

| 任务场景 | 查阅文件 | 审查目的 |
|---|---|---|
| **灵感审查** | 1. `outlines/vol_XX/outline.md`<br/>2. `outlines/main_plot.md`<br/>3. `state/milestones.json` / `lines.json`<br/>4. `bible/02_power_system.md`<br/>5. `characters/` 与 `entities/` | 核对分卷走向、宏观里程碑、伏笔期限与战力设定 |
| **Level 2 剧情冲突急救** | 1. `log/audit/ch_XXX.md` 或 `log/review/`<br/>2. 涉事正文 `manuscript/**`<br/>3. 涉事设定 `bible/**` 或状态 `state/**` | 定位冲突源与最小创口修复路径 |
| **全书设定演进** | 1. `bible/*.md` 六表<br/>2. `outlines/main_plot.md` 与分卷大纲<br/>3. `project.json` | 评估体系调整波及面 |

---

## 🔍 三、 执行规程

### 1. 灵感审查双轨处置
- **微观微调（不改大纲走向、不破战力、不撞伏笔）**：
  1. 使用 `replace_file_content` 将灵感合入 `outlines/vol_XX/outline.md` 当章梗概；
  2. 运行 `python studio.py check` 确保 0 errors；
  3. 回执主控：微观微调已合入大纲。
- **宏观重构（改主线走向、颠覆里程碑或战力）**：
  1. 建立快照：`python studio.py snapshot create "pre_evolution_<灵感主题>" -w "workspace/<书名>"`；
  2. 因果测算：`python studio.py simulate impact --entity <相关实体> --action retcon -w "workspace/<书名>"`；
  3. 协同修改受波及的大纲、设定或状态文件；
  4. 运行 `python studio.py check` 确保 0 errors；
  5. 回执主控：宏观重构已对齐平账。

---

## ⚡ 四、 工序流程

1. **步骤 1【因果测算】**：
   ```powershell
   python studio.py simulate impact --entity <实体名> --action retcon -w "workspace/<书名>"
   ```
   - 验证正文出处（选跑）：`python studio.py ask "<关键词>"`（最多 3 次）。

2. **步骤 2【建立安全快照】**：
   ```powershell
   python studio.py snapshot create "pre_evolution_<修改主题>" -w "workspace/<书名>"
   ```

3. **步骤 3【修改与体检】**：
   - 调用 `view_file` **单次全量读取**目标文件；
   - 使用 `replace_file_content` 或 `write_to_file` 修改目标文件（**禁传 `ArtifactMetadata`**）；
   - 运行体检：
     ```powershell
     python studio.py check -w "workspace/<书名>"
     ```
     确保 **0 errors**；
   - 输出 3 行完工回执停机。

---

## 🔒 五、 权限与红线

- 💻 **准跑命令**：`simulate impact`、`snapshot create/rollback`、`check`、`ask`（最多 3 次）；
- 📖 **准读文件**：受波及的设定、卡片与正文（单次全量读取，禁切片）；
- ✍️ **准写工件**：`replace_file_content` / `write_to_file` 修改受波及文件（**禁传 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁未建立快照直接修改；
  - 严禁全书大拆大卸（只动受影响局部）；
  - 严禁在对话框发送正文；严禁阅读 `engine/` 源码；严禁编写临时脚本。

---

## 🛑 六、 完工回执

```text
【章节工序完工回执】
- 完工阶段：Stage 4C 剧情外科与急救 (Evolution)
- 产出路径：[受影响的主要文件路径]
- 核心指标：备份快照已建立 ｜ 跨层修改精准落地 ｜ check 0 报错 ｜ 工具直接物理落盘
```
