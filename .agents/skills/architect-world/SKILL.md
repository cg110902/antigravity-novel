---
name: novel-architect-world
description: Universal worldbuilding architect, axiom builder, and entity card generator for Novel Studio (Stage 0A). Initializes workspace, fills bible/ axioms, project.json, and characters/entities cards.
---

# SKILL — novel-architect-world（世界观与实体架构师专属手册 · Stage 0A）

> ⚡ **【核心定位 · 世界真理与实体底座奠基者】**：
> Stage 0A 是全书物理法则、世界底色与实体矩阵的法定奠基者。
> 依据作者原始需求或 `dossier.md`（重点消费 **[Part A 设定与实体]** 与 **[Part C 黄金锚点]**），初始化书籍工作区，填实设定真理底座（`bible/` 六表与 `project.json`），并建立与填实全部核心人物卡（`characters/`）与实体卡（`entities/`），严格贯彻黄金锚点，消灭以上所有 `{{slot:}}` 占位符。

---

## 一、 执行工序与交付清单

1. **终端执行初始化命令**（已含书籍数据的工作区拒覆盖，确认重置加 `--force`）：
   ```powershell
   python studio.py init -w "workspace/<书名>" -t "<书名>" -g "<题材>" -p "<主角名>"
   ```

2. **填实 `bible/` 六表与 `project.json`**（消灭所有 `{{slot:}}` 占位符，删除模板自带的注释）：
   - `bible/01_world_axioms.md`：核心 Logline、**全书精神立意与核心主题（Theme & Moral Compass，确立正向三观与人性光芒，杜绝低俗与无脑戾气）**、空间三级划分、2~3条不可违背客观公理、金手指/优势机制（原理+代价+上限+成长阶梯）；
   - `bible/02_power_system.md`：Tier 1~5 阶层梯阶与破坏力/表现力实物标尺（严防战力通胀）；
   - `bible/03_factions_geography.md`：首发舞台与进阶地缘、三大核心势力矩阵与利益冲突网；
   - `bible/04_economy_items.md`：货币体系与购买力平价锚点（PPP 对账表）、物资道具五阶分类；
   - `bible/05_special_mechanics.md`：题材专属特异机制、相生相克矩阵、负荷代偿法则；
   - `bible/06_deviations.md`：本书偏离清单与核心创作红线；
   - `project.json`：配置书级参数与题材专属词表（8个顶层键：`schema`/`title`/`genre`/`protagonist`/`scope`/`engine`/`current_status`/`created_at`）。

3. **填实/建立核心角色卡 `characters/`**（消灭所有 `{{slot:}}` 占位符，按需填写，允许存在多个）：
   - `characters/protagonist.md`：填实主角专属卡（确立四维心理、动作库、恒定称谓矩阵；若为量化/游戏/高武题材，启用 frontmatter 中的 `stats` 量化属性字典）；
   - `characters/antagonist.md`：填实首卷核心反派/宿敌卡（锁定扭曲心理四维、压迫标尺、走狗矩阵、镜像对立与溃败破局钥匙；量化题材按需配置 `stats`）；
   - `characters/<核心角色>.md`：按需创建关键搭档/女主卡（基于 `templates/characters/character_card_standard.md`，独立动机、互称矩阵；量化题材按需配置 `stats`）。

4. **建立开局实体卡 `entities/`**（消灭所有 `{{slot:}}` 占位符，按需填写，允许存在多个）：
   - `entities/factions/<初始宗门/阵营名>.md`：开局初始势力卡（基于 `templates/entities/faction_card.md`，锁定掌权人 `leader`、总部 `headquarters`、核心资产、外交关系）；
   - `entities/locations/<开局地标场景名>.md`：开局新手村/核心地标场景卡（基于 `templates/entities/location_card.md`，**必须填实 `sensory_anchor` 感官与 `environment_rules` 环境法则**）；
   - `entities/items/<道具名>.md`：创建开局核心道具/资产卡（基于 `templates/entities/item_card.md`，锁定 `holder`、品阶、使用消耗、充能上限与 `durability` 初始耐久磨损）。

---

## 二、 白名单与权限红线（契约边界）

- 💻 **唯一准跑命令**：`python studio.py init -w "workspace/<书名>" -t "<书名>" -g "<题材>" -p "<主角名>"`
- 📖 **准读输入**：输入 Prompt、`dossier.md`（重点消费 Part A 与 Part C）、`templates/`（单次全量读取，绝对严禁切片分页）；
- ✍️ **准写工件**：`write_to_file` / `replace_file_content` 写入 `bible/*.md`、`project.json`、`characters/`、`entities/`（**绝对严禁传递 `ArtifactMetadata`**）；
- 🚫 **绝对红线**：
  - 严禁阅读 `engine/` 源码；严禁编写任何临时脚本；
  - 严禁越权修改 `outlines/` 或 `state/`（属于 Stage 0B 专属工序）；
  - 设定六表、人物卡与实体卡必须消除所有 `{{slot:}}` 占位符；
  - 落盘即交付，严禁回读自验，立即输出 3 行标准回执交卷。

---

## 三、 极简标准完工回执 (统一回执 · 3 行)

```text
【章节工序完工回执】
- 完工阶段：Stage 0A 设定与实体筑基 (Architect-World)
- 产出路径：workspace/<书名>/bible/, characters/, entities/, project.json
- 核心指标：设定六表已落盘 ｜ 人物与实体卡槽位消除率 100% ｜ 验收达标
```
