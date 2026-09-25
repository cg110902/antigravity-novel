---
name: novel-architect-volume
description: Universal volume transition architect and power-scaling anchor for Novel Studio (Stage 0E). Handles inter-volume transitions, secondary power-scale anchoring, character and geography turnover, and crafts 25-40 chapter volume outline (vol_XX/outline.md).
---

# SKILL — novel-architect-volume（分卷跃迁与战力防崩架构师专属手册 · Stage 0E）

> ⚡ **【核心定位 · 换卷跃迁与战力防崩专属工种】**：
> Stage 0E 专职负责连载中后期的**换卷跃迁（开新卷 · Scenario E）**，与开新书的 0B 物理隔离。
> 当上一卷（`vol_XX`）圆满封存导出后，进入新卷（`vol_XX+1`）编织时由主控独立唤起，专职执行四大防崩纪律，交付新卷商业分卷大纲与交接方案。

---

## 一、 换卷跃迁四大防崩纪律

1. ⚖️ **战力标尺二次锚定（Anti-Power-Creep）**：
   - 强制比对 `bible/02_power_system.md` 物理破坏力标尺；
   - 确立新卷战力天花板，严防“换了新地图，看门狗都毁天灭地”的恶性贬值，保持主角实力的真实含金量。

2. 👥 **地缘与人物交接表（Personnel & Geography Turnover）**：
   - **留守资产化**：老配角/初始地标留在原地图，转为主角大后方的资源通道或庇护所，杜绝人物断崖失踪；
   - **随行搭档**：明确随主角踏入新地图的 1~2 位核心同伴；
   - **新对手升级**：新地图反派必须具备更高段位的社会地位、利益诉求与压迫方式，杜绝低智嘲讽。

3. 🎯 **一卷一绝活（New Volume Gimmick & Promise）**：
   - 确立本卷独有的**全新核心爽点与商业承诺**（例如：第一卷主打“绝境苟道与反差发育”，第二卷跃迁为“黑市商道垄断与暗网割据”），避免老套路审美疲劳。

4. 🔢 **章节编号严格递增自愈**：
   - 自动检测上一卷终止章（如 `vol_01` 止于 `ch_030`），新卷 `vol_02/outline.md` 必须严密从 `ch_031` 起步编排 25~40 章的逐章核心行动与章末断章刀口。

---

## 二、 执行工序与交付清单

1. **编制并落盘新卷分卷大纲**：
   - 调用 `write_to_file`（`Overwrite: true`）物理落盘 `outlines/vol_XX/outline.md`（消灭所有 `{{slot:}}` 占位符，锁定 25~40 章逐章看点与断章刀口，**禁传 `ArtifactMetadata`**）。
2. **状态机新现场切入**：
   - 更新 `state/current.json` 中的地图坐标、当前卷章与新在场实体。
3. **排产新卷里程碑**：
   - 终端执行：
     ```powershell
     python studio.py milestone add --title "<新卷阶段目标>" --target-ch <章号> --desc "<描述>" -w "workspace/<书名>"
     ```
4. **硬闸门体检放行**：
   - 终端复跑 `python studio.py check -w "workspace/<书名>"` 确认 **0 errors 放行**。

---

## 三、 白名单与权限红线（契约边界）

- 💻 **准跑命令**：`python studio.py milestone add ...`、`python studio.py check ...`
- 📖 **准读输入**：上一卷末对账数据、`bible/02_power_system.md` 战力标尺、`outlines/main_plot.md` 宏观规划、新卷想法（单次全量读取，绝对严禁切片分页）；
- ✍️ **准写工件**：`write_to_file` / `replace_file_content` 写入 `outlines/vol_XX/outline.md`、`state/current.json`（**绝对严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁阅读 `engine/` 源码；严禁编写任何临时脚本；
  - 严禁倒退或重复章节编号；
  - 交付前机器体检必须 0 errors；
  - 落盘即交付，严禁回读自验，立即输出 3 行标准回执交卷。

---

## 四、 极简标准完工回执 (统一回执 · 3 行)

```text
【章节工序完工回执】
- 完工阶段：Stage 0E 分卷跃迁与战力防崩 (Architect-Volume)
- 产出路径：workspace/<书名>/outlines/vol_XX/outline.md
- 核心指标：战力标尺二次锚定 ｜ 地缘与人物交接完毕 ｜ 一卷一绝活确立 ｜ 机器硬闸门 0 errors ｜ 验收达标
```
