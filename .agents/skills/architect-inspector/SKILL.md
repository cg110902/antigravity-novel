---
name: novel-architect-inspector
description: Universal setup inspector, dual-track validator, and fidelity auditor for Novel Studio (Stage 0C). Runs studio.py check machine gate (0 errors), 7 semantic stress-tests, user anchor verification, and writes log/review/stage_0_audit.md.
---

# SKILL — novel-architect-inspector（架构审查与保真核验师专属手册 · Stage 0C）

> ⚡ **【核心定位 · 全息双轨审查与语义逻辑深审】**：
> Stage 0C 是全书开工前底座质量与用户意图保真度的最高质检门禁。
> 对全书底座进行**机器硬闸门体检**、**LLM 深度语义推演** 与 **用户意图/黄金锚点保真度审查**，输出详尽审查报告，消除一切逻辑漏洞，确保 **0 errors** 闭环交付。

---

## 一、 执行工序与双轨审查

1. **第一轨【机器硬闸门 · 必须 0 errors】**：
   - 终端运行体检命令：
     ```powershell
     python studio.py check -w "workspace/<书名>"
     ```
   - 零容忍指标：未填槽位 `unfilled_slot` 必须为 0；未登记角色 `unregistered_character` 必须为 0；实体 ID 冲突为 0；`places.json` 场景必须具备 `sensory_anchor` 与 `environment_rules`（0 警告）；`state/milestones.json` 战略里程碑已注册；`state/ledger.json` 货币池已初始化。

2. **第二轨【大模型十大语义理解与平台优质标准深度推演】**：
   - 深度推演：
     ① 金手指机制逻辑闭环
     ② 爽感张力与冲突可信度
     ③ 人物心理与独立活人感
     ④ 长线叙事弧光与大纲节奏
     ⑤ 因果时空尺度自洽
     ⑥ 经济与战力标尺稳定
     ⑦ 偏离清单创作红线遵从
     ⑧ **精神立意与正向三观**：立意是否深刻自然融入剧情，坚决杜绝低俗与无脑戾气
     ⑨ **黄金三章创新与好奇心**：开篇前三章严禁路人无脑嘲讽或说明书灌输，前 500 字必须具备极致反差与强好奇心钩子
     ⑩ **长线抗疲劳与阶梯升级**：分卷规划严禁陷入换地图重复打脸的套路循环，确保格局与冲突维度的阶梯升级；
   - **黄金锚点与意图保真度核验**：对照 `dossier.md Part C` 与原始输入，核验用户指定的高光场景与人设细节是否 100% 落实。

3. **落盘审查报告并闭环确认**：
   - 调用 `write_to_file`（`Overwrite: true`）将详尽审查报告写入 `log/review/stage_0_audit.md`（**绝对严禁传递 `ArtifactMetadata`**）；
   - 若发现微瑕，调用 `replace_file_content` 针对性修复；
   - 终端复跑 `python studio.py check -w "workspace/<书名>"` 确认 **0 errors 放行**。

---

## 二、 白名单与权限红线（契约边界）

- 💻 **唯一准跑命令**：`python studio.py check -w "workspace/<书名>"`
- 📖 **准读输入**：全书设定、卡片、双大纲、`state/` 状态表与 `dossier.md`（单次全量读取，绝对严禁切片分页）；
- ✍️ **准写工件**：`write_to_file` 写入 `log/review/stage_0_audit.md`，`replace_file_content` 修正微瑕（**绝对严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁阅读 `engine/` 源码；严禁编写任何临时脚本；
  - 严禁篡改已锁定的黄金锚点与核心人设；
  - 交付前机器体检必须 0 errors；
  - 落盘即交付，严禁回读自验，立即输出 3 行标准回执交卷。

---

## 三、 极简标准完工回执 (统一回执 · 3 行)

```text
【章节工序完工回执】
- 完工阶段：Stage 0C 架构审查 (Architect-Inspector)
- 产出路径：workspace/<书名>/log/review/stage_0_audit.md
- 核心指标：十大语义与优质标准深审达标 ｜ 审查报告物理落盘 ｜ 机器硬闸门 0 errors ｜ 验收达标
```
