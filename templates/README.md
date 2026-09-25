# templates/ — 全题材底层词典与设定规范库（Canonical Lore & Correction Templates）

本目录是 Novel Studio 的**全题材底层世界观、实体知识库与对账规范模板库**。
不仅是一次性脚手架，更是全书在 Stage 0 筑基后沉淀为 10,000+ 字全景物理定律的**底层词典与机械矫正器**。后续全流水线的增删改查对账均以此为基准锚点。


**【Architect 填写注意事项】**：
模板中的预填信息仅为占位，请根据当前题材与设定灵活填写，可自行补充更多！

---

## 目录与模块全景架构

```text
templates/
├── project.json                   # 引擎种子配置（scope 商业标尺 + engine 旋钮；词表类旋钮缺席时回落引擎内置全题材默认值，`config guide` 可查）
├── lexicon.json                   # 固定词表（作者死规则：Stage 5 finalize 确定性替换/删除/轮换/保护，无需 LLM 判断）
├── beats.md                       # 单章细纲任务书模板（含主线航标绑定、在场人物弧阶段、负向禁忌红线、事件推演、交付契约）
├── bible/                         # 全书世界观与运转公理词典模块（Stage 0 深度筑基）
│   ├── 01_world_axioms.md         # 世界底色、底层公理与运转机制（含金手指运转逻辑）
│   ├── 02_power_system.md         # 阶层/实力梯阶与物理/社会实物标尺（防表现力通胀）
│   ├── 03_factions_geography.md   # 地缘区划、各方势力矩阵与利益冲突
│   ├── 04_economy_items.md        # 经济通货、购买力锚点与物资道具品阶
│   ├── 05_special_mechanics.md    # 特殊机制、体质/血脉/职业谱系与代偿惩戒法则
│   └── 06_deviations.md           # 本书偏离清单与核心创作红线（推翻传统套路声明）
├── characters/                    # 角色全息卡模板
│   ├── protagonist.md             # 主角高维专属全息卡（含万古底蕴、心理四维、防冷脸动作、绝对称谓矩阵）
│   ├── antagonist.md              # 核心反派/宿敌全息卡（扭曲心理四维、压迫表现标尺、爪牙走狗网络、称谓矩阵、溃败破局钥匙）
│   └── character_card_standard.md # 标准重要配角/女主/关键搭档全息卡模板
├── entities/                      # 非人物类实体全息卡模板（彻底终结道具势力无卡裸奔顽疾）
│   ├── item_card.md               # 核心资产/装备/道具/载具卡模板（品阶、材质物象、能耗代价、充能流转）
│   ├── faction_card.md            # 核心势力/组织卡模板（权力架构、核心底蕴、敌友网络、变迁轨迹；题材示例见卡内）
│   └── location_card.md           # 关键地标/秘境/场景卡模板（空间氛围、感官细节、环境法则、历史节点）
└── outlines/                      # 全书与分卷剧情大纲模板
    ├── main_plot.md               # 全书主线脊柱与长程宏观架构（开局/终局/动力引擎/里程碑）
    └── volume_outline.md          # 分卷大纲模板（本卷承诺、主支线交织追踪谱、四分位阶段规划、人物弧演进里程碑）
```

---

## 模板实例化与目标路径对照

| 模板源文件 | `studio.py init` 目标路径 | 负责角色 | 核心功能与引擎联动 |
|---|---|---|---|
| `project.json` | `project.json` | 引擎自动 ➔ Stage 0A 填实 | **8 个顶层键**：`schema`/`title`/`genre`/`protagonist`/`scope`/`engine`/`current_status`/`created_at`。`scope` 存商业标尺（target_words/target_volumes/chapters_per_volume/words_per_chapter，作为写手指引而非硬性代码拦截）；`engine` 存引擎旋钮：`token_cap`/`cruise_max_chapters`/`cruise_human_gate`/`cruise_wait_timeout`/`default_pool`（v4.3.2 缺陷#26：原文所列 `style_*` 系 style 命令于 v4.2 退役后的文档残留，引擎中从不存在该旋钮，已删除）。彻底移除一切死板的字数容差、对白比例、排版限制与**引擎内硬编码词表**（注意区分：`lexicon.json` 是**作者维护的外部词表文件**，非引擎内置硬编码，不违反此原则）。全量旋钮清单与当前值：`config guide` |
| `lexicon.json` | `lexicon.json` | 引擎自动播种**空骨架** ➔ 作者手工维护 | **固定词表**（v4.5.0 新增）：作者事先定好的死规则。三段——`lexicon`（**定值替换**，空串＝删除，如「猪肝色→青紫色」）、`rotate`（**轮换**，同一词按出现次序取不同候选以制造多样性）、`protect`（**保护**，固定词组整体豁免，如「安安静静」「年纪轻轻」）。由 Stage 5 `finalize` 在配方之后**确定性执行**，不做语境判断。长词优先、保护词优先、单遍不链式（幂等）；轮换起点由「章号+原词」哈希决定，同章重跑一致、跨章错开。**已存在不覆盖**——作者的词表是手工资产，`init` 绝不抹掉；且**只播种空骨架、不复制基线**（全局基线 `templates/lexicon.json` 自动叠加生效，复制进书会造成"改基线对旧书无效"）。格式损坏硬阻断（exit 1），文件缺失合法（功能未启用）。详见 `engine/README.md`「固定替换词表」节 |
| `bible/01_world_axioms.md` | `bible/01_world_axioms.md` | Stage 0A (Architect-World) | 世界底层物理与逻辑公理，金手指运转机制 |
| `bible/02_power_system.md` | `bible/02_power_system.md` | Stage 0A (Architect-World) | 力量/社会地位实物标尺，默认恒给 `pack` P0 时空胶囊 |
| `bible/03_factions_geography.md` | `bible/03_factions_geography.md` | Stage 0A (Architect-World) | 地缘版图与势力利益冲突，默认恒给 `pack` P0 时空胶囊 |
| `bible/04_economy_items.md` | `bible/04_economy_items.md` | Stage 0A (Architect-World) | 货币购买力平价锚点，道具品阶与损耗充能账本 |
| `bible/05_special_mechanics.md` | `bible/05_special_mechanics.md` | Stage 0A (Architect-World) | 独家机制、体质相生相克与反噬走火入魔代偿法则 |
| `bible/06_deviations.md` | `bible/06_deviations.md` | Stage 0A (Architect-World) | 本书偏离清单（`pack` 强制提取注入 P0 时空胶囊） |
| `characters/protagonist.md` | `characters/protagonist.md` | Stage 0A (Architect-World) | 主角全息卡（含绝对称谓矩阵）；卡是**人读视图**，称谓基准由主控抄进细纲、由 `pack` 从台账侧注入 |
| `characters/antagonist.md` | `characters/<反派名>.md` | Stage 0A (Architect-World) | 核心反派/宿敌全息卡（含压迫标尺、走狗爪牙、称谓矩阵、镜像价值对立与溃败钥匙） |
| `characters/character_card_standard.md` | 按需手工复制到 `characters/<角色名>.md` | Stage 0A (Architect-World) | 标准重要配角/女主/关键盟友全息卡（锁定法定称谓对账表） |
| `entities/item_card.md` | 按需手工复制到 `entities/items/<道具名>.md` | Stage 0A (Architect-World) | 核心道具/装备/神舟卡（追踪充能、持有者流转） |
| `entities/faction_card.md` | 按需手工复制到 `entities/factions/<势力名>.md` | Stage 0A (Architect-World) | 核心势力卡（组织架构与对外关系） |
| `entities/location_card.md` | 按需手工复制到 `entities/locations/<地名>.md` | Stage 0A (Architect-World) | 核心地标与第一案发现场空间格局 |
| `outlines/main_plot.md` | `outlines/main_plot.md` | Stage 0B (Architect-Story) | 全书主线脊柱、核心三幕与长线里程碑 |
| `outlines/volume_outline.md` | `outlines/vol_01/outline.md` | Stage 0B (Architect-Story) | 首卷分卷大纲与四分位剧情航标（含主支线交织追踪谱与人物弧演变里程碑） |
| `beats.md` | `studio.py beats new [章节] --write` 自动装配生成（`beats` 只有 `new` 一个子命令；脚手架从卷纲注入本章在卷位置、主线事件看点与**活跃伏笔雷达**，并预填主角名） | 主控 (Director) | 单章细纲任务书（含 narrative_spine 航标、arc_phase 人物弧阶段、负向禁忌红线与量化台账）。  |

---

## 填写、增删改查与生命周期规范

1. **Stage 0 深度筑基规范**：
   - 执行 `python studio.py init -w workspace/<书名> -t "书名" -g "题材" -p "主角名"` 后，模板自动全量实例化；
   - 由 `Architect`（架构师）在独立纯净沙盒中完成全部 `{{slot:...}}` 的深度填充，字数规模应达到 **10,000+ 字**；
   - 填实后运行 `python studio.py check`，未填槽位将以警告清单逐文件点出（Stage 0C 门禁要求全部清零后方可开盘连载）。

2. **全局统一物理 ID 编码前缀矩阵 (Canonical Entity ID Matrix)**：
   全书所有实体均拥有全生命周期不可变唯一物理 ID，作为底层持久化与跨章精准检索键：
   - 👤 **角色 (person)**：`p_001`（主角恒定为 `p_001`）, `p_002`, `p_003`...
   - ⚔️ **物品与法宝 (item)**：`it_001`, `it_002`, `it_003`...
   - 🏰 **势力与组织 (faction)**：`fac_001`, `fac_002`, `fac_003`...
   - 🗺️ **地点与关节点 (location)**：`loc_001`, `loc_002`, `loc_003`...

3. **二八实体分级管理法则 (Tiered Entity Management)**：
   彻底杜绝长篇小说中“路人甲都要建个卡片”导致的千张碎卡爆炸灾难：
   - 🌟 **核心实体（占 20%，决定 80% 叙事）**：主角、核心女主、长线宿敌、阵营重臣、核心重器、首府要塞。
     - **标准**：必须在 `characters/` 或 `entities/` 建立独立的 `.md` 全息卡，锁定称谓矩阵、Want/Fear 与物象；
     - **台账**：在 `实体四表（persons/items/factions/places）` 中配置对应 `card: "characters/<名字>.md"` 路径。
   - 🍃 **次要/临时实体（占 80%，服务即时情节）**：客栈掌柜、巡逻守卫、传话执事、临时消耗符箓、路过村庄。
     - **标准**：**坚决不建 `.md` 冗余卡片**，避免文件污染与磁盘膨胀；
     - **台账**：直接在提案中登记入 `实体四表（persons/items/factions/places）`（设置 `card: ""`），记录其姓名、ID、境界、阵营与正文引文即可。

4. **强类型物理通用字段（Entities Schema 核心白名单）**：
   底层状态表 `实体四表（persons/items/factions/places）` 按白名单读取以下法定字段（未知字段被引擎忽略、不参与校验）。各角色向状态表登记实体时，**应严格使用以下法定字段**：
   - 🆔 **标识与类型**：
     - `id`: 唯一物理 ID（终身不可变：`p_001`, `it_001`, `fac_001`, `loc_001`；台账侧另有引擎自动生成的 `GUN-001` 伏笔 / `KNO-001` 知识点 / `MIS-001` 谜团 / `DEBT-AUTO-<hash>` 恩怨（引擎按「章节+双方+类型」自动派生，细纲无需填写 id）/ `LOCK-001` 锁定 / `ms_001` 里程碑，发号一律走 `id next`）
     - `name`: 实体中文法定全名（唯一主键）
     - `type`: 实体类型（严格枚举：`person`, `item`, `location`, `place`, `faction`, `other`）
     - `role`: 角色叙事定位（合法白名单：`protagonist` / `deuteragonist` / `antagonist` / `ally` / `supporting`（配角，引擎缺省值）等）
     - `aliases`: 别名、代号、尊号列表（`array[str]`）
     - `card`: 对应全息卡相对路径（核心实体如 `"characters/主角.md"`，次要路人留空 `""`）
     - `summary`: 实体一句话核心定位（`str`）
   - ⚡ **战力与位阶（防通胀标尺）**：
     - `tier_rank`: 实力/品阶梯阶整数（`1 ~ 12` 级，用于侧对侧数值对比）
     - `tier_name`: 境界/职级法定称号（如 `"通玄境后期"`、`"玄阶中品"`、`"A级"`）
     - `realm`: 修炼大境界划分（`str`）
     - `power_benchmark`: 破坏力与防御物理实物标尺（`str`）
     - `stats`: 量化属性/能力面板（`dict[str, Any]`，如 `{"hp": "...", "mp": "...", "combat_power": 120}`，用于游戏/高武/异能/科幻等量化题材；非量化题材可省略）
   - 🩺 **生命与存在状态**：
     - `status`: 实体活跃状态（严格枚举：`active` 活跃, `retired` 隐退/沉睡）
     - `life_status`: 生命体生死状态（枚举：`alive` 在世, `deceased` 阵亡, `missing` 失踪/下落不明, `unknown` 生死不明）
       · `unknown` 与 `missing` 都**不等于死亡**：不进已故黑名单、可正常登场；区别是 `missing` 讲下落不明，`unknown` 讲存活状态本身未确认（坠崖/沉船/爆炸后生死未卜）。引擎会在编剧简报里单立「❓ 生死不明人物悬念账」，提醒后续章节不得擅自坐实其生死；真要定论时显式改写 `life_status`（如 `unknown` ➔ `alive`/`deceased`）即可。
       · 枚举外的写法不再报错：引擎按同义词自动归一（「生死不知/生死未卜」➔ `unknown`，「失联/杳无音信」➔ `missing`），归一不了的原样保留并只给一条提醒。
     - `condition`: 肉身或物性状态（如 `"重伤"`、`"经脉受损"`、`"完好"`）
     - `injury_level`: 伤势等级 `0~5`（`0`=无伤，`5`=濒死；人物专用可算字段，建议与 `injury_desc` 同写）
     - `injury_desc`: 伤势文字说明（如 `"左臂骨折"`）
     - `renown`: 声望/悬赏整数值（人物/势力；正=美名，负=恶名/悬赏）
   - 🗺️ **地缘与归属**：
     - `location`: 当前具体所在空间/据点（`str`，严禁用 `current_location`）
     - `faction`: 所属门派、势力或组织名称（`str`）
     - `attitude`: 对主角/阵营的政治态度（严格枚举：`hostile` 敌对, `neutral` 中立, `friendly` 友善, `allied` 结盟，严禁用 `disposition`）
   - ⚔️ **道具与重器专用**：
     - `holder`: 当前实际支配/持有者角色名（`str`，严禁用 `current_owner`）
     - `charges`: 剩余可用充能/催动次数（**合法范围 `>= -1`**：非计数型道具直接写 `-1` 或省略本字段，
       引擎视 -1 为无限耐久、永不因扣减报错；`sync` 对计数型道具执行 `>= 0` 硬约束，透支会被阻断）
     - `max_charges`: 最大充能上限（`int >= 1`）
     - `cost_per_use`: 单次催动代价/消耗说明（`str`）
     - `durability`: 物理磨损/耐久度（`str`）
   - 🏰 **势力与据点专用**：
     - `scale_tier`: 势力规模梯级（`1 ~ 10`）
     - `leader`: 最高掌权领袖角色名（`str`）
     - `headquarters`: 总部据点/山门祖庭地名（`str`）
     - `core_assets`: 核心垄断王牌资产清单（`array[str]`）
     - `diplomacy`: 势力外交网络映射（`{"势力名": "hostile"|"neutral"|"friendly"|"allied"}`，词表同 `FactionAttitude` 枚举；⚠️ 本字段是自由字符串字典，引擎不校验取值也不会读它做推断，写错枚举值不会报错——请以枚举为准）
     - `danger_tier`: 地点危险系数（`1 ~ 10`）
     - `danger_level`: 危险评级文字说明（`str`，如“安全腹地/争端前线/绝地死境”，与 `danger_tier` 形成数值孪生）
     - `environment_rules`: 地理环境法则与准入门槛（`array[str]`）
   - 🎭 **感官物象、叙事元数据与称谓锁（防冷脸与防吃书）**：
     - `sensory_anchor`: 标志性外观、穿戴与视觉记忆物象（`str`；**严禁气味/嗅觉**）
     - `micro_actions`: 标志性习惯动作与神态库（`array[str]`）
     - `address_matrix`: 对特定实体的法定称谓映射（`{"目标名": "我称呼对方"}`）
     - `relations`: 与特定实体的动态张力网络（`[{"target": "角色名", "type": "rival", "desc": "宿敌"}]`）
     - `dossier`: 恩怨羁绊、历史过节与交互备忘（`str`）
     - `scope`: 所属分卷生命周期（如 `vol_01`；省略表示全书通用）
     - `golden_quote`: 首次高光定稿切片（100~200字物象细节；卡片级展示字段，引擎忽略）
     - `schema_version`: 卡片或实体规范版本（`str`，如 `novel-studio.character/v2`；卡片级元数据，引擎忽略）

---

## 五、 底层台账全息架构与新书通电规范（State Tables Blueprint for New Books）

在新书初始化后，由 **Stage 0B (`novel-architect-story`)** 对 `state/` 八表进行全息通电，并由 **Stage 0C (`novel-architect-inspector`)** 进行硬闸门核验。各表规范与核心要素如下：

1. `state/persons.json`（角色全息台账）：
   - 登记主角 `p_001`、反派 `p_002` 及首卷核心配角；
   - 必须包含 `id`, `name`, `type: "person"`, `role`, `tier_rank`, `tier_name`, `power_benchmark`, `faction`, `status: "active"`, `card`；
   - 若为量化题材（游戏/高武/数值异能），必须配置 `stats` 字典（如 `{"hp": "...", "combat_power": 100}`）。

2. `state/places.json`（场景与空间台账）：
   - 登记开局核心场景与首卷关键地标；
   - **硬性规范**：除 `id`, `name`, `type: "place"`, `danger_tier`, `danger_level` 外，**必须完整同步 `sensory_anchor`（空间采光、核心视觉物象）与 `environment_rules`（环境准则/出入法则）**。严禁留空，确保 `studio.py check` 0 警告，并为 `pack.md` 场景时空胶囊提供高浓度感官锚点。**⚠️ `sensory_anchor` 严禁写入任何气味/嗅觉描写**——禁令①已彻底禁用嗅觉（Gemini 无法正确使用嗅觉感官），视觉、听觉、温度、触感不在禁用之列。

3. `state/items.json`（核心道具与资产台账）：
   - 登记主角初始道具、反派核心重器或关键信物；
   - 必须包含 `id`, `name`, `type: "item"`, `holder`, `charges`, `max_charges`, `cost_per_use`, `durability`, `sensory_anchor`；
   - 非计数型道具 `charges` 设为 `-1`；有磨损的道具必须明确 `durability`（如 `"98/100"` 或 `"成色良好"`）。

4. `state/factions.json`（势力与组织台账）：
   - 登记开局势力；包含 `id`, `name`, `type: "faction"`, `scale_tier`, `leader`, `headquarters`, `core_assets`, `diplomacy`。

5. `state/current.json`（第一现场动态时空锚点）：
   - 开局初始锚点：`chapter: 0`, `time`, `location`, `persons_present`, `atmosphere`, `mc_status`, `turn_count: 0`。

6. `state/lines.json`（线索与伏笔雷达表）：
   - 埋设首卷长线：`GUN-001`（危机倒计时/悬顶之剑）、`KNO-001`（致命信息差）、`MIS-001`（外界认知偏差）。

7. `state/locked.json`（不可逆既定事实表）：
   - 登记开局世界与主角不可逆事实 `LOCK-001`。

8. `state/milestones.json`（战略里程碑台账）：
   - 对应分卷大纲 `volume_outline.md` 中的【本卷战略里程碑排产】；
   - 使用命令 `python studio.py milestone add --title "<标题>" --target-ch <章号> --desc "<描述>" -w "workspace/<书名>"` 添加，或由 Stage 0B 直接以 JSON 数组写入；
   - 格式：`[ { "id": "ms_001", "title": "...", "desc": "...", "target_ch": 5, "scope": "vol_01", "status": "pending", "achieved_ch": null } ]`。

9. `state/ledger.json`（经济与货币资产对账表）：
   - 对应分卷大纲 `volume_outline.md` 中的【本卷经济与核心资源池预设】；
   - 声明 `pools` 与 `pools_baseline`：`{ "pools": { "货币名": 初始值 }, "pools_baseline": { "货币名": 初始值 }, "history": [] }`。

10. `state/debts.json`（人际恩怨与血仇对账表）：
    - 登记开局未清算恩怨：`[ { "id": "DEBT-001", "type": "blood_debt", "source_char": "p_001", "target_char": "p_002", "desc": "...", "created_ch": 1, "status": "active" } ]`。