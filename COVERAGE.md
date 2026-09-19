# Novel Studio v4.3.2 — 逻辑覆盖清册

> 第 7 轮第 7 项产出。文档 + 代码全量盘点，作为实战测试的靶向地图。
> 目的：把「引擎宣称会管的每一条逻辑」列全，逐条标注**是否已被实战验证**，
> 未验证项即为测试死角，据此设计新书实战。

---

## 一、命令面覆盖（26 顶层 + 10 组二级动作 = 42 个可执行组合）

| # | 命令 | 二级动作 | 位置参数 | 关键选项 |
|---|---|---|---|---|
| 1 | `init` | — | — | `--force` |
| 2 | `check` | — | `[chapter_id]` | `--json` |
| 3 | `cockpit` | — | — | — |
| 4 | `beats` | `new` | `chapter_id` | `--write` `--force` |
| 5 | `outline` | `get` | `chapter_id` | — |
| 6 | `pack` | — | `chapter_id` | `--write` |
| 7 | `audit` | — | `chapter_id` | `--write` `--force` |
| 8 | `finalize` | — | `chapter_id` | — |
| 9 | `proposal` | `auto` | `chapter_id` | `--write` `--force` |
| 10 | `sync` | — | `chapter_id` | `--force` `--refresh` |
| 11 | `cruise` | — | `start_ch` | `--until` `--target` `--max-chapters` `--vol` `--once` `--poll` |
| 12 | `status` | — | — | `--json` |
| 13 | `calendar` | — | `count` | — |
| 14 | `ask` | — | `query` | — |
| 15 | `milestone` | `add` / `achieve` | `[milestone_id]` | `--title` `--target-ch` `--desc` |
| 16 | `snapshot` | `create` / `list` / `rollback` | `[name]` | — |
| 17 | `reconcile` | — | `volume_id` | `--write` |
| 18 | `state` | `rollup` | `volume_id` | — |
| 19 | `evidence` | `candidates` | `chapter_id` | — |
| 20 | `simulate` | `impact` | — | `--entity` `--action` |
| 21 | `trace` | — | `target_id` | — |
| 22 | `id` | `next` / `list` / `trace` | `category` / `target_id` | — |
| 23 | `export` | — | — | `--vol` `--format` `--no-digest` |
| 24 | `style` | — | — | `--last`（已失效，见 BUG#22） |
| 25 | `config` | `get` / `set` / `guide` | `[key]` `[value]` | — |
| 26 | `help` | — | — | `--json` |

---

## 二、硬阻断点（GuardError → exit 1）共 10 处

| # | 位置 | 阻断条件 | 实战验证 |
|---|---|---|---|
| G1 | `ops.py:111` | `init` 工作区已有 project.json 且无 `--force` | ✅ 已验 |
| G2 | `ops.py:523` | `beats new --write` 细纲已有内容，拒绝覆盖 SSOT | ⬜ 待验 |
| G3 | `ops.py:1066` | `finalize` 细纲仍含 `{{slot:}}` 未填占位符 | ⬜ 待验 |
| G4 | `ops.py:1110` | `finalize` 无任何有效正文（final 空且 raw 均空） | ⬜ 待验 |
| G5 | `ops.py:1171` | `sync --refresh` 但该章从未同步过 | ⬜ 待验 |
| G6 | `ops.py:1185` | `sync` 正文指纹与上次不符（需 `--force`/`--refresh`） | ✅ 已验 |
| G7 | `ops.py:1924` | `milestone add --target-ch` < 1 | ✅ 已验（BUG#25） |
| G8 | `ops.py:1935` | `milestone add --target-ch` ≤ 当前章 | ✅ 已验（BUG#25） |
| G9 | `ops.py:2026` | `snapshot rollback` 压缩包含越级路径 | ⬜ 待验 |
| G10 | `state.py:611` | 合账预检 `_fatal`（死者登场 / 道具充能透支） | ✅ 已验 |

---

## 三、`check` 巡检节（7 节，节号已于第 7 轮修正乱序）

| 节 | 名称 | 级别 | 实战验证 |
|---|---|---|---|
| 2.5 | 状态表完整性（坏 JSON 隔离） | error | ✅ 已验 |
| 3.1 | 道具归属与死者平账 | error | ✅ 已验 |
| 3.2 | 伏笔时钟超期 | warning | ✅ 已验 |
| 3.3 | 地点残缺 | warning | ⬜ 待验 |
| 3.4 | 强类型枚举白名单（BUG#27） | warning | ✅ 已验 |
| 3.5 | 定稿 ⇄ 合账对账（BUG#28） | warning | ✅ 已验 |
| 3.6 | 里程碑时钟超期（BUG#25） | warning | ✅ 已验 |
| 3.7 | 台账内部交叉引用 6 项（BUG#20） | error/warning | ✅ 已验 |

---

## 四、正文探针（`probes.py`，4 类 + 1 遥测）

| 探针 | 职责 | 实战验证 |
|---|---|---|
| `probe_epistemology_leaks` | 认知盲区防透视（角色说出不该知道的秘密） | ⬜ **待验** |
| `probe_address_matrix` | 法定称谓矩阵（互称是否符合 address_matrix） | ⬜ **待验** |
| `probe_grounding` | 伏笔与道具物象落地（声明了却没写进正文） | ⬜ **待验** |
| `probe_unregistered_fatalities` | 未登记死亡与新实体预警 | ✅ 已验（BUG#15） |
| 正文字数遥测 | words_per_chapter 区间参考 | ✅ 已验 |

---

## 五、合账数据流（`state.py` 单章 14 张表写入顺序）

`persons` → `items` → `places` → `lines` → `ledger` → `debts` → `relations`
→ `locked` → `synopsis` → `timeline` → `current` → `co_occurrence`
→ `entity_timeline` → `chapter_snapshot`

- 每张表原子（tmp+fsync+`os.replace`），**整体无事务**，但 sync 幂等兜住重跑（BUG#28 已验）。
- 细纲消费字段：顶层 12 个 + `state_deltas` 5 子块（BUG#21 已验）。

---

## 六、实战测试死角清单（本轮靶向目标）

按上表汇总，**尚未被任何测试触及**的逻辑：

1. **G2** `beats new --write` 对已填写细纲的 SSOT 覆盖防护
2. **G3** `finalize` 未填槽位拦截
3. **G4** `finalize` 空正文拦截
4. **G5** `sync --refresh` 无指纹拦截
5. **G9** `snapshot rollback` 路径穿越防护（安全相关，优先级高）
6. **3.3** 地点残缺巡检
7. **三大正文探针**：认知盲区 / 称谓矩阵 / 物象落地 —— 这是「引擎是否偷懒」的核心，
   必须靠**人工编造违规正文**来验，是本轮重中之重
8. `calendar` / `trace` / `id next|list|trace` / `outline get` / `export --format`
   / `config set` / `snapshot list|rollback` / `cruise --once|--poll` 等低频命令
9. **跨卷**：vol_01 → vol_02 换卷、`state rollup`、`reconcile` 双卷
10. **幂等矩阵**：每个写命令重复执行两次，比对台账是否漂移
