# probes.md — engine/check.py 与 engine/probes.py 静态审计缺陷候选报告

- 审计对象：`engine/check.py`（649 行，全书 16 表巡检）、`engine/probes.py`（719 行，确定性物理事实探针矩阵）
- 交叉核对：`engine/state.py`（1623 行）、`engine/id_tracker.py`（1023 行）、`engine/config.py`、`engine/parser.py`、`engine/ops.py`、`engine/cruise.py`、`engine/cli.py`
- 授权依据：人类作者已授权全文件读写（含 engine/ 源码），本报告只读不写，未修改任何代码
- 严重级定义：
  - **L1** = 违反既定契约 / 合规数据被硬阻断 / 整节防护被静默卸载 / 两个阻断级探针之一的漏检通道
  - **L2** = 规则缺口或对合理数据的 error 级误报，不直接造成不可逆事故但削弱巡检可信度
  - **L3** = 边缘场景、warning 级噪音、性能与输出一致性细节
- 计数：**共 34 项候选缺陷（L1×7 / L2×17 / L3×10）**，其中假阴性 13、假阳性 11、健壮性 6、其他 4

---

## 一、任务清单逐项覆盖度矩阵

| # | 该查的规则 | 实现在哪 | 覆盖度评估 |
|---|---|---|---|
| 1 | 死亡角色复活（present_characters vs life_status）跨章 | `id_tracker.py:897-925`（Anti-Resurrection Guard，ID+姓名双路，短路上报） | **部分覆盖**：只查细纲 present_characters；正文 prose 层零检测（FN-8）；倒叙章无豁免（FP-4） |
| 2 | 道具 holder 指向不存在角色 / 幽灵 ID | `check.py:129-139`（b 节，`_known_person` 解析 ID/姓名/别名/泛指） | **基本覆盖**：但归一化能力弱于 sync 的 `_resolve_person_id`（FP-3）；死者持有只匹配 name/pid 不匹配别名（FN-9）；`fac_`/`loc_` 前缀豁免但 ID 存在性未验（FN-13） |
| 3 | 伏笔 plant 未 resolve | `check.py:336-347`（3.2 超期，**仅当有 target_ch**）＋`id_tracker.py:998-1006` | **部分覆盖**：无 target_ch 的 active 伏笔永久静默（FN-5） |
| 3b | resolved 无回收章 | `check.py:169-179`（e 节 error） | 已覆盖 |
| 4 | locked.json 指向未入账章节 | `check.py:186-198`（f 节 error） | **覆盖有洞**：被 `if _tl_chs:` 整体短路；timeline 条目缺 `chapter_id` 键时反向批量误报（FN-1） |
| 5 | timeline 时间倒序 / 同日冲突 | **无任何实现** | **假阴性候选**（FN-2）。timeline 条目只存自由文本 `timeline` 字段（`state.py:1444`），全书零消费方 |
| 6 | ledger 负余额 | **无任何实现** | **假阴性候选**（FN-3）。`state.py:1246` `pools[p]=baseline+sum(delta)` 本身不设下限 |
| 7 | debts 引用了已删除实体 | `check.py:141-153`（c 节 error） | 已覆盖（但空引用被 `_known_person` 放行且无独立必填校验） |
| 7b | debts 双方引用同一实体 | **无任何实现** | **假阴性候选**（FN-7） |
| 8 | relations history 重复章 | **无任何实现** | **假阴性候选**（FN-6）。sync 侧按 chapter 去重（`state.py:1373`），但手工编辑无校验 |
| 9 | 称谓矩阵全匹配/部分匹配误伤 | `probes.py:214-266` | 全匹配过严（FP-6）；无 present_characters 时退回旧假阳性口径（FP-5） |
| 10 | 字数遥测阈值误伤正常章节 | `probes.py:672-690`＋`check.py:574-579` | warning 级可接受，但 `long` 贴线无容差且字数口径与官方 `count_prose_words` 不一致（FP-8） |
| 11 | 未填槽位扫描误报正常空块 | `check.py:34-54` | `new_entities: []` 不涉槽位、无误报；但围栏代码块内 slot 说明仍计数（FP-10） |
| 12 | 实体名大小写/空格/别名归一化 | `check.py:94-110` vs `state.py:169-185` | **check 侧弱于 sync 侧**，合规引用被判断裂（FP-3） |
| 13 | 16 表可解析性 | `check.py:265-278` | 只查"损坏"不查"缺失"（FN-10）；`state/history/`、`state/inbox/` 不在清单（OT-4） |
| 14 | 未填槽位闸门 | `check.py:34-54`（warning 清单） | 按契约 warning 级，正确 |
| 15 | ID 完整性/台账一致性深度校验 | `id_tracker.py:767-1012`＋`check.py:499-512` | 深度足够，但整节可被一行畸形数据静默卸载（RB-2） |
| 16 | 单章 check vs 全书 check 差异 | `check.py:526`（`if chapter_id:` 才跑探针） | 差异未文档化（OT-2） |
| 17 | --json 与文本输出一致性 | `cli.py:452-466` | 阻断数据同源一致；文本模式丢弃 probe_results 细节（OT-3） |

---

## 二、候选缺陷清单

### A. 假阴性（13 项）

---

**[SEVERITY: L1] [类型: 假阴性] probes.py:182-198（`probe_epistemology_leaks` 对白循环）**

**问题描述**：内层 `for speaker, content in dialogues:` 循环在检查完**第一段**含关键词的对白后无条件 `break`（第 198 行），无论该段是合法陈述还是泄露。每个关键词的判定样本永远只有 1 段对白。

**触发场景**：机密「半枚铜灯签在裴砚贴身藏品之中」在第 5 段被知情人合法陈述（说话人可归属、盲区角色不在场 → 静默通过并 break），盲区角色沈拂云本人在第 9 段说出同一机密 → 因第 5 段已 break，确认级泄露**永久漏检**。这是仅有的两个阻断级探针之一的漏检通道；且泄漏证据越多（对话越多）越可能被一段合法陈述挡掉。

**建议修法**：删除第 198 行的无条件 `break`，改为仅在 `secret_confirmed` 置位或该段触发 suspected 时 break；或在循环前先用一遍全 dialogues 做「本人对白」铁证扫描，再做静默通过判定。

---

**[SEVERITY: L2] [类型: 假阴性] check.py:186-198（f) 锁定事实指向未入账章节）**

**问题描述**：整个 f) 校验被 `if _tl_chs:`（第 188 行）包裹——timeline.json 缺失、为空、或所有条目都缺 `chapter_id` 键时，`_tl_chs` 为空集/`{""}`，校验整体跳过。反向地，若 timeline 条目是手工写成的不含 `chapter_id` 的 dict，`_tl_chs={""}` 非空 → 每条 locked fact 都报「指向未入账章节」批量假阳性。`established_ch` 键名硬编码，不兼容 `chapter`/`ch` 变体。

**触发场景**：Architect 手工在 locked.json 建档 `established_ch: ch_099`，而该章已被回滚删除、timeline.json 恰好为空 → 0 error 放行，锁定事实悬空。或反向：手工维护 timeline 漏写 chapter_id → 全书 locked facts 批量误报。

**建议修法**：改为无条件校验；timeline 为空时用「beats 文件名集合 ∪ sync_log 键 ∪ final 章号」兜底构造已入账章节集；读取时兼容 `chapter_id`/`chapter`/`ch` 三个键名并做章号归一（`_ch_order`）后比较。

---

**[SEVERITY: L2] [类型: 假阴性] check.py 全文（ledger 负余额零实现）**

**问题描述**：16 表清单中 ledger.json 只参与 2.5 节 JSON 可解析性巡检；`scan_ledger_integrity`（57-206 行）七个子校验 a)~f) 完全不碰 ledger。`state.py:1246` 的池余额恒等式 `pools[p]=baseline+sum(delta)` 允许负值累积，sync 与 check 双通道均不设下限。transactions 条目结构（pool/delta/chapter_id 必填、delta 可解析）也无校验。

**触发场景**：细纲连续写 `ledger: {delta: -500}` → 通用资金池 -300；check 0 errors、cockpit 照常展示，资金穿仓成为永久静默数据污染。

**建议修法**：新增 3.x 节：`pools` 任一余额 <0 报 warning（经济死锁可升 error）；校验 transactions 每条 `pool`/`delta`/章号可解析、delta 为整数；与 debts 平账记录做引用一致性抽查。

---

**[SEVERITY: L2] [类型: 假阴性] check.py:336-347（3.2 伏笔时钟）**

**问题描述**：超期巡检的入口条件是 `lrec.get("status")=="active" and lrec.get("target_ch")`——只覆盖**排了目标章**的伏笔。plant 后从未排 target_ch、也从未 resolve 的伏笔（纯粹的「埋了忘了」）全书零提示。id_tracker 的 4) 节只校验 resolve/reveal 引用的 ID 存在性，同样不覆盖此类。

**触发场景**：ch_003 `plant GUN-002`（血书暗桩），后续大纲遗忘、既无 target_ch 也无 resolve → 16 章过去 check 0 errors 0 warnings，伏笔静默蒸发。

**建议修法**：对 `status=="active"` 且无 `target_ch` 的伏笔，按 `planted_ch` 与 `current_ch` 的账龄给 warning（如账龄 > 卷均章数 ×0.5）；或至少在 cockpit 活跃伏笔列表标注「未排期」。

---

**[SEVERITY: L2] [类型: 假阴性] check.py:155-167（d) 关系网双方引用）**

**问题描述**：relations 只校验 `source_id`/`target_id` 可解析，不校验二者归一后是否为同一实体；`history` 数组（`state.py:1334/1373-1381`，每条含 chapter/dynamic/subtext/affinity/tension）的章号唯一性与单调性零校验。

**触发场景**：(a) 手工编辑 relations.json 写成 `{source_id: p_001, target_id: p_001}` → 0 error（自怨条目）；(b) novel-evolution 手工补历史写出两条 `chapter: ch_005` → 重复章静默入账，对账时关系轨迹出现分叉。

**建议修法**：d) 节增加 `_resolve_person_id(source)==_resolve_person_id(target)` 同实体 warning；增加 history 内 `chapter` 唯一性校验（用 `_ch_order` 归一后查重）与章号非降序提示。

---

**[SEVERITY: L2] [类型: 假阴性] check.py 全文（debts 双方同一实体）**

**问题描述**：c) 节（141-153 行）只查 source_char/target_char 可解析，`source_char == target_char`（或解析到同一 pid）无任何校验；且 `_known_person` 对空引用直接返回 True（第 98 行「交由各自的必填校验处理」），而 debts 的必填校验**并不存在**——空 source/target 的恩怨条目也静默放行。

**触发场景**：手改 debts.json：`{"id":"DEBT-007","source_char":"p_001","target_char":"p_001","desc":"自责"}` → 0 error。

**建议修法**：c) 节补同实体 warning；对空 `source_char`/`target_char`/`desc` 补「恩怨字段残缺」warning（与 e) 节伏笔字段残缺同构）。

---

**[SEVERITY: L2] [类型: 假阴性] id_tracker.py:897-925（复活闸门的作用域）**

**问题描述**：Anti-Resurrection Guard 只扫描细纲 `present_characters`。正文 prose 层零检测——final 文本里已故角色继续说话/行动，只要 beats 没列他，全链路无感。`probe_unregistered_fatalities` 只查「死亡未登记」，不查「已死者再次登场」，两个探针方向互补但这一半缺失。

**触发场景**：韩姨 ch_007 阵亡入账；ch_009 Drafter 笔误写「韩姨端着药碗进来」，beats 也未列她 → beats 层无违规、prose 层无探针 → 0 error，死者复活直接流落入定稿。

**建议修法**：单章 check 模式（或 Librarian 巡检）对 final 文本做「已故角色名/别名 × is_deceased」共现扫描，命中报 warning（交 Auditor 判别倒叙/误写）；至少覆盖说话人归属成功的对白。

---

**[SEVERITY: L2] [类型: 假阴性] check.py:324-331（3.1 死者持有活跃道具）**

**问题描述**：匹配条件是 `h in {prec.get("name",""), pid}`——holder 写成别名、去括号基准名或大小写变体时漏判；且只查 `status=="active"`（缺省才算），`retired` 等状态不查。与 b) 节的 `_known_person`（支持别名解析）口径不一致：同一份数据，b) 认为引用合法、3.1 认为死者不持有，两节对「何为同一人」的理解漂移。

**触发场景**：items.json `holder: "老裴"`（裴砚别名），裴砚已阵亡 → 3.1 不报警；道具随死者蒸发。

**建议修法**：3.1 改用 `_resolve_person_id(h, persons_scan)` 归一后判 `is_deceased`，与 `_known_person`/sync 三方口径统一。

---

**[SEVERITY: L2] [类型: 假阴性] check.py:271-274（16 表巡检的存在性盲区）**

**问题描述**：`if not f.exists(): continue`——文件缺失一律静默。`_load_json` 的残骸保护只覆盖「损坏被隔离后正主缺席」一种形态；被直接 rm 掉的 relations.json / timeline.json / sync_log.json / milestones.json 在任何账龄的书上都 0 errors。`history/` 章快照与 `inbox/` 提案文件也不在巡检清单（OT-4）。

**触发场景**：误操作删除 `state/timeline.json`（或清理磁盘时当临时文件清掉）→ check 全绿，巡航继续，sync 以空 timeline 重建，历史章节入账记录全丢。

**建议修法**：按 `current_ch` 章号分流——`current_ch > ch_001` 时对核心 14 表做存在性 error（首跑豁免，与「首跑合法缺表」的自愈边界兼容）；history 快照数 < 已 sync 章数时报 warning。

---

**[SEVERITY: L3] [类型: 假阴性] probes.py:170-172 / 666（blind_spots 键名与值类型静默失效）**

**问题描述**：`probe_epistemology_leaks` 的 `blind_spots.items()` 要求 dict-of-list；`run_all_probes` 第 666 行 `(frontmatter.get("epistemology") or {}).get("blind_spots", {})` 要求 epistemology 为 dict。若 beats 用**角色姓名**而非 p_ ID 作键（模板未强制 ID），或 secrets 写成单个字符串，`name_by_id.get(char_id)` 永远为空 → `owner_name` 为假 → 确认级分支（185 行）不可达，全部降级 suspected。首章新角色尤其容易踩中（人物尚未入账，作者倾向写名字）。

**触发场景**：细纲 `epistemology: {blind_spots: {"沈拂云": ["她是韩家的人"]}}` → 沈拂云正文亲口说出机密，只到疑似级 warning，error 永不触发。

**建议修法**：`owner_name` 增加按姓名反查 persons_db 的回路；`secrets` 接受字符串并包裹为列表；epistemology 形态非法时降为 warning 而非静默跳过（见 RB-3）。

---

**[SEVERITY: L3] [类型: 假阴性] probes.py:546-549（audit_text 死亡打捞过宽）＋ probes.py:561/573（短名跳过）**

**问题描述**：audit_text 打捞判据是「行内含 阵亡/死亡/牺牲 且含角色名」——「裴砚的死亡是假象，他活了下来」这类行会把裴砚永久移出死亡检测集（acknowledged_deaths 只加不减）。另 `len(cname)<2` 的单字名角色与 pid 键（"p_001"）整条跳过死亡扫描。

**触发场景**：审计报告写「关于裴砚死亡的推断不成立」→ 后续章节裴砚真阵亡的描写被静默。

**建议修法**：audit 打捞行增加否定/假象守卫（不成立|假象|并非|误判|没有死）；单字名走别名或 present_characters 声明补齐后再扫。

---

**[SEVERITY: L3] [类型: 假阴性] check.py:134（loc_/fac_ 前缀豁免不验存在性）**

**问题描述**：holder 以 `loc_`/`fac_` 开头直接放行，但该 loc_/fac_ ID 是否真的存在于 places.json/factions.json 从未校验。

**触发场景**：`holder: "fac_999"`（势力已删）→ 0 error，道具挂在幽灵势力名下。

**建议修法**：放行前查 `factions_db`/`places_db` 存在性，不在则报引用断裂。

---

### B. 假阳性（11 项）

---

**[SEVERITY: L1] [类型: 假阳性＋契约违反] check.py:571-572（未登记死亡以 error 级消费）＋ probes.py:576-591（措辞共现窗口）**

**问题描述**：双重问题。(1) **越权定级**：probes.py 模块 docstring（第 9-12 行）与 check.py 头部注释（第 8-9 行）均白纸黑字写着「阻断级仅 2：空正文(0字) / 确认级认知泄露」，但 probes.py:697-698 把 `p_fatalities["passed"]` 纳入 `all_passed`，check.py:571-572 将其升级为 errors —— 第三个阻断级，未经契约变更。BUG#47 的分层治理注释（probes.py:395-400）明说这些正则「只用于提醒、不做硬裁决」，实现却拿去硬裁决，文档与代码直接对打。(2) **误判窗口**：`NAME[^\n。！？]{0,35}(?:PAT)|(?:PAT)[^\n。！？]{0,35}NAME` 的 35 字同句共现不区分主语/宾语/旁观者，`_NON_DEATH_GUARDS`（411-417 行）不含回忆、旁述、观察类语境。

**触发场景**（均为完全合规的高频正文写法）：
- 「裴砚望着脚边的尸体，冰冷僵硬，一动不动」→ NAME 在前 + 尸体类范式 → 判【裴砚】疑似阵亡 → **exit 1 硬阻断**；
- 「他没有忘记父亲死于十年前的那场大火」→ 回忆旁述含「死于」→ 父亲若已建档且此时未登记 → 误报未登记阵亡；
- 「她险些死于那场车祸」中「险些」不在 probes 的守卫表（只在 state 侧守卫表里有）→ 误报。

**建议修法**：(a) 按 docstring 契约把 fatalities misses 降为 warning（交 Auditor）；若确要保留第三阻断级，先修订 docstring/README 立项并配回归测试。(b) 正则层加观察/回忆/旁述守卫（望着|看着|瞧见|想起|记得|回忆|坟前|遗像|遗物|险些|差点|几乎），以及「NAME 的 +亲属称谓+死亡词」结构排除；共现窗口从 35 字收紧到同一意群（如 15 字）并优先取 NAME 后最近动词。

---

**[SEVERITY: L1] [类型: 假阳性] check.py:383-389（枚举白名单与引擎自身写入口径冲突）**

**问题描述**：`_ENUMS["status"]={"active","retired"}`，但 `state.py:1047-1054` 的 sync **合法写入** `destroyed` / `consumed` / `lost` 三种道具状态（注释原文：「状态流转 (status): active, consumed, destroyed, lost」）。即引擎最核心的写入方自己就在生产「法定枚举」之外的值。

**触发场景**：任何有道具损毁/消耗/遗失情节的书（战斗、末世、消耗品题材必然出现），每件道具一条「强类型枚举越界」warning，且越界值恰是引擎生产的——作者按 warning 去「修正」成 active/retired 反而破坏数据语义。长期效果是训练所有作者忽略 check 的 warning 列表，把 `life_status` 非法值（该节真正要抓的目标，见 420-423 行自述）一并淹没。

**建议修法**：`status` 白名单改为「引擎写入口径 ∪ 文档枚举」= {active, retired, consumed, destroyed, lost}；或该字段的校验改为只认文档枚举、引擎口径单独豁免；修完后补一条回归测试锁定 sync↔check 白名单一致。

---

**[SEVERITY: L2] [类型: 假阳性] check.py:94-110（`_known_person` 归一化弱于 `_resolve_person_id`）**

**问题描述**：check 判定引用可解析只做 `str.strip()` 后的精确匹配（ID/name/aliases 三向等值）；sync 侧的 `_resolve_person_id`（state.py:169-185）额外支持**去括号基准名**（「裴砚（主角）」→「裴砚」）。check 对大小写折叠、内部空格（「崔 敬亭」）、全角/半角差异同样零处理。同一份数据 sync 能正确入账、check 报引用断裂 error。

**触发场景**：evolution 手工编辑时把 holder 写成英文名大小写变体或带入全角空格 → check 硬报「道具持有者在 persons.json 中不存在」→ exit 1，而该数据 sync 其实认得。

**建议修法**：check 侧直接复用 `state._resolve_person_id`（失败再退回泛指占位集 `_generic_refs`），消除两套解析口径；顺带做 `str.casefold()` 与内部空白归一。

---

**[SEVERITY: L2] [类型: 假阳性] id_tracker.py:897-925（复活闸门无倒叙/回忆豁免）**

**问题描述**：`_ch_num(ch) > _ch_num(d_ch)` 一刀切。beats 的 `chapter_type` 枚举（破局/铺垫/过渡/爆发/回收/余韵，见 pack.md：21）没有 flashback 语义，回忆章里已故角色合法登场（死亡前的时光）会被判「因果严重冲突」error 硬阻断，逃生通道只有把角色从 present_characters 删掉——而回忆章删掉在场者会连带弄坏在场称谓/认知探针的输入。

**触发场景**：ch_020 为回忆章，讲主角与三年前身亡的师兄共事 → present_characters 含师兄 → error 阻断，必须绕过引擎人肉处理。

**建议修法**：`chapter_type` 增加 `flashback` 值并在复活闸门放行（或允许 `locked_facts` 显式豁免）；至少在错误信息中给出「若为倒叙章」的处置指引。

---

**[SEVERITY: L2] [类型: 假阳性] probes.py:245-256（称谓矩阵过滤器双空档）**

**问题描述**：`if _present and pid not in _present`（说话人在场过滤）与 `if _present_names and tgt not in _present_names`（称谓对象在场过滤）都以 `_present` 非空为前置条件。当 beats **缺 `present_characters` 字段**（旧模板、手写细纲、打包丢失）时两个过滤器同时失效 → 退回到缺陷#32 修复前的口径：全程未出场、仅被对话提及的角色也被苛求「应称 XX」落地——正是#32 实测场景（崔敬亭被裴砚沈拂云提起）原样复活。

**触发场景**：作者手写细纲忘填 present_characters → 称谓探针对每个被提及的已建档角色发难，真实疏漏被淹没。

**建议修法**：present_characters 缺失时，用「对白归属成功的说话人 ∪ 正文出现频次 TopN 人名」推导在场集合；或维持更严口径「至少说话人有可归属台词且称谓对象同为可归属说话人」。

---

**[SEVERITY: L2] [类型: 假阳性] probes.py:251-258（称谓落地只认精确字符串）**

**问题描述**：`if addr not in text` 要求法定称谓**整串精确出现**。称谓在实际行文中存在大量合法变体：matrix 存「裴大人」而正文写「大人」「裴大人您」（后者是子串，OK）、「老裴」；matrix 存「云丫头」而该作者章写「云姐姐」——凡变体即报「法定称谓本章未落地」。任务重点问的全匹配/部分匹配问题：现状是全匹配且不做别名展开，部分匹配（bigram）反而没有，误伤面集中且无法通过任何单一写法消除。

**触发场景**：亲属称谓随情节演变（丫头→姐姐）属正常创作演进，check 每章 warning。

**建议修法**：address_matrix 支持多形态数组（`address_variants`），命中任一即落地；或按人物 `aliases`+称谓词干做部分匹配；对「演化型称谓」允许 Auditor 在 log/audit 登记豁免名单。

---

**[SEVERITY: L2] [类型: 假阳性] probes.py:139-144（4 字滑窗横跨通用边界）**

**问题描述**：≥8 字机密切全部 4 字滑窗并全部计为强证据。机密「半枚铜灯签在裴砚贴身藏品之中」产出「灯签在」「在裴砚」「裴砚贴」等窗口——「灯签在」是通用结构（唯一切割点在动宾边界上），盲区角色合法说一句「灯签在桌上」即触发 confirmed error。FIND-O 只修复了「短机密切窗」的一半，没修复「窗口跨越停用结构」的另一半。

**触发场景**：盲区角色anywhere 说了含该 4 元组的日常句 → exit 1 硬阻断，且泄露的是公共短语而非机密本体。

**建议修法**：窗口内含结构词（的|在|是|不|有|与|和|了|着|过）时降级为 weak；或要求同句 ≥2 个窗口共现才升确认级；单窗口命中至多 suspected。

---

**[SEVERITY: L3] [类型: 假阳性] probes.py:672-690 ＋ probes.py:22-26（字数遥测口径）**

**问题描述**：(1) `long` 档只要 `> _wc_max` 即 warning，默认上限 2600 时 2601~2700 字的正常章必 warning，无容差带。(2) `_count_total` 把传入文本**全文**计数，而 `run_all_probes` 收到的是 final/raw 文件原文（check.py:561 直接 read_text），含 YAML frontmatter 与 Markdown 标题行；官方口径 `count_prose_words`（ops.py:34-52，BUG#35 声明的「全书唯一合法字数口径」）剥离这两者。同一章在 audit 报告里出现两个字数（净字数 vs 探针字数），且探针用偏大的数去比阈值。

**触发场景**：2600 字上限的书，正文 2590 + 标题/frontmatter 30 → 探针 2620 → 「超出参考上限」warning，实为合规章。

**建议修法**：`long` 用 1.1×容差或仅保留 severe_short 直报；探针字数改复用 `count_prose_words` 口径（或剥离 frontmatter/标题后计数），与 audit body 展示值统一。

---

**[SEVERITY: L3] [类型: 假阳性] probes.py:431-457（对白占比遥测）**

**问题描述**：(1) 判据是「行内含任一引号字符即整行计为对白行」——旁白句内嵌引用的词（所谓「天道」）、英文 scare quotes 全部计入，分子虚高。(2) `ratio_range` 为**字符串**（如 project.json 手写 `"25,55"`）时，`ratio_range[0]` 是 `"2"`，`float("2")=2.0` 成功、不被 433-435 行的 except 捕获 → lo=2.0, hi=5.0 静默畸变，全章 100% 误报越界。(3) 短章行数少，一行之差即 0%/100%，波动巨大。

**触发场景**：`config set dialogue_ratio "25,55"` 的旧写法 → 每章都报「高于上限 5%」。

**建议修法**：对 str 型配置先 `json.loads` 再兜底 split；引号判据收紧为「行首或句中成对引号含 ≥N 字」；短章（<20 行）跳过或放宽。

---

**[SEVERITY: L3] [类型: 假阳性] check.py:31/48（行内代码剥离不覆盖围栏代码块）**

**问题描述**：`_INLINE_CODE` 只匹配不含换行的 `` `...` `` 跨度；``` 围栏代码块**内部**的 `{{slot:...}}` 示例文仍被 `_SLOT_PATTERN` 计数。缺陷#29 的修复动机（文档在描述槽位语法）对围栏形态无效。

**触发场景**：某 bible/outlines 文档在 ``` 围栏里展示槽位用法（如 readme 式说明段落被抄进 bible/）→ Stage 0C「全部填实」门禁永远差几条，每本新书init 后背一个消不掉的 warning——正是#29 想消灭的现象。

**建议修法**：计数前先剥离 ```...``` 围栏块（含行号跟踪的多行状态机），再剥行内代码，最后计数。

---

**[SEVERITY: L3] [类型: 假阳性] check.py:603-617（审计涌现事实消化的实体名抽取）＋ probes.py:70-78（回忆式引语错配）**

**问题描述**：(1) 涌现事实的实体名用「名称: X」精确抽取后要求 `X in fm_blob`；审计写「角色: 崔敬亭（崔通判）」或名内带空格，即判未消化 → 假 warning；audit 模板自带的示例行若不含白名单里的「待填写」占位短语，也会被当成真涌现事实。(2) `_find_before` 用 `context.rfind(name)` 取 60 字符内最后一次出现+其后 4 字内言语动词：「他想起赵管事说过的话，喃喃道：『……』」——「说」紧邻「赵管事」→ 该对白错配给赵管事，认知泄露判定跟着错配（既可能误报合法台词为泄密，也可能把真泄露归错的而静默）。

**触发场景**：审计报告按模板填写带括号全称 → 每章一条「审计涌现事实未消化」；回忆式引语章 → 认知探针指向错误的说话人。

**建议修法**：实体名抽取后做括号剥离/空白归一再比对 fm_blob；示例行过滤改为「行内含 slot 占位符或模板标记即跳过」；`_find_before` 增加「想起|记得|忆及|昔日」回忆前缀排除，并把言语动词邻接窗口对前置式从 4 字收紧到排除「过」（说过≠此刻说）。

---

### C. 健壮性（6 项）

---

**[SEVERITY: L1] [类型: 健壮性] check.py:527/564（§5 未包裹的状态表读取）＋ check.py:315-318（非 dict 值直接崩溃）**

**问题描述**：三个未设防路径。(1) 第 564 行 `state_mgr.get_persons()` 与第 527 行 `get_current()`：persons.json/current.json 损坏（或被隔离后正主缺失）时 `_load_json` 抛 RuntimeError，穿过 run_full_check 直达 CLI → exit 4「系统/数据完整性故障」，**已积累的 2.5 节等全部诊断报告被丢弃**，cruise 链（cruise.py:155）中断。(2) 第 315-318 行 `it.get("charges")`：`_load_json` 的顶层类型契约只校验 dict-vs-list，`items.json = {"it_001": ["oops"]}` 这类 dict-of-list 数据直接 AttributeError（3.1/3.2/3.3 至少在 try 内，315 行在 try 外）。

**触发场景**：persons.json 被误编辑为半截 JSON → `check ch_005` 本应输出「状态表损坏+其余章节级诊断」，实际 exit 4 且无报告；items.json 某条记录手滑写成数组 → check 直接崩。

**建议修法**：§5 整体包 `try/except RuntimeError → errors.append(...) + 跳过探针`（与 506-510 行同构）；315 行循环前过滤 `isinstance(v, dict)`，非 dict 值单独报 warning。

---

**[SEVERITY: L1] [类型: 健壮性] check.py:203-204（scan_ledger_integrity 外层裸吞）**

**问题描述**：`except Exception: pass` 位于整个 a)~f) 六项校验之外。任一子项遇到非预期数据形态即整体卸载：relations 值为 list → `_r.get` AttributeError；timeline 条目为 str → `t.get` AttributeError；arc_history 为 str 等。而 199-202 行精心设计的「RuntimeError 上抛、由调用方降级」通道被 AttributeError 完全旁路——缺陷#20/#24 修复的**全部**防线（生死自相矛盾、道具断裂、恩怨断裂、关系断裂、伏笔字段残缺、锁定事实悬空）可被一行畸形数据同时静默关闭，且报告里毫无痕迹。这正是「假阴性工厂」结构。

**触发场景**：手工编辑 state/relations.json 时把某个 pair 的值写成数组 → check 0 errors ✅，evolution 平账验收闸门形同虚设（该函数 docstring 自述的危害原样复发）。

**建议修法**：a)~f) 各自独立 try/except，单节失败降为一条 warning「X 交叉校验因数据形态异常跳过」；外层 except 至少 append 一条总告警，禁止静默 pass。

---

**[SEVERITY: L1] [类型: 健壮性] probes.py:666/347/523/170（畸形 frontmatter 零防御）**

**问题描述**：四处形态假设全部裸奔：`(fm.get("epistemology") or {}).get(...)`（epistemology 为 list 即崩）、`fm.get("state_deltas") or {}` 后 `sd.get("items")`（state_deltas 为 list 即崩，347 行与 523 行两处）、`blind_spots.items()`（blind_spots 为 list 即崩）。且 `run_all_probes` 的三个调用方——check.py:564、ops.py:662（audit_chapter）、cruise.py:155 链路——**均不捕获异常**。一份手写错误的细纲让 `check ch_XXX`、`audit ch_XXX`、无人值守巡航同时 exit 4「未预期异常」，探针报告中途全丢，作者看到的是「系统故障」而不是「你第 38 行 YAML 写成了列表」。

**触发场景**：细纲 `state_deltas:` 下误写成 `- key: value` 列表形态（mini-YAML 合法解析为 list）→ 后续所有探针命令连环崩溃。

**建议修法**：`run_all_probes` 入口对 epistemology/state_deltas/blind_spots/present_characters/foreshadowing_deltas 做 isinstance 归一（非预期类型 → `{}` 并记一条形态 warning）；各 probe 函数内部沿用同一归一；调用方对非 RuntimeError 异常降级为「探针跳过」而非崩出去。

---

**[SEVERITY: L2] [类型: 健壮性] check.py:332/346/370/431/465/496（bare except 家族静默跳节）**

**问题描述**：3.1/3.2/3.3/3.4/3.5/3.6 六节巡检各自 `except Exception: pass`。任何数据形态异常（timeline 条目非 dict、target_ch 为 int 导致 `re.search` TypeError、places 值为 list）都让该节**整体消失且零痕迹**。与 RB-2 同构，只是粒度更细——六节里每节都是一个可被单行坏数据关掉的独立防线。

**触发场景**：`lines.json` 某条 `target_ch: 12`（int）→ 3.2 整节静默死亡，其余伏笔的超期提醒也一起消失。

**建议修法**：统一改为 `except Exception as e: warnings.append(f"X 巡检跳过: {type(e).__name__}（请检查数据形态）")`，让跳节可见。

---

**[SEVERITY: L2] [类型: 健壮性] check.py:341-345 / 352-353（表值为非 dict 的连锁）**

**问题描述**：`lines_scan.items()`/`places_scan.items()` 后直接 `lrec.get`/`prec.get`——值为非 dict 时分别在 try 内（→3.2/3.3 静默死）与 3.1（→try 内死）；`charges` 例外在 try 外（→崩）。同源异构，坏一条记录废掉整节巡检。

**触发场景**：手工编辑 places.json 把某地点写成字符串 → 3.3 地点残缺+重名双校验同时消失。

**建议修法**：循环入口统一 `{k: v for k, v in tbl.items() if isinstance(v, dict)}`，被过滤的键报 warning。

---

**[SEVERITY: L3] [类型: 健壮性] probes.py:431-435 / check.py:483 / probes.py:107-110（零长度边角）**

**问题描述**：三处边角。(1) `dialogue_ratio` 配置为 dict 时 `ratio_range[0]` 抛 KeyError（不在捕获三元组内）→ 崩；为 str 时阈值畸变（见 FP-9）。(2) check.py:483 `isinstance(_tc, int)` 接受 `True` → 里程碑目标章变成第 1 章 → 全书里程碑批量误报超期。(3) probes.py:107 `r"[“「](.*?)[”」]"` DOTALL：引号未闭合时跨段配对，产生跨章节的巨型伪对白跨度，其 `content` 随后进入认知关键词 `in` 匹配——narration 文本被卷进对白判定（确认级泄露的误判输入）；与直引号 spans 混合时还可能重叠计数。

**建议修法**：dict 配置显式报 warning 回退默认；`_tc` 增加 `and not isinstance(_tc, bool)`；弯引号配对限制单行或加跨度上限（如 500 字）并在超出时告警疑似引号不配对。

---

### D. 其他：契约与一致性（4 项）

---

**[SEVERITY: L1] [类型: 契约违反] probes.py:9-12/697-698 ↔ check.py:571-572（探针强弱分级契约自相矛盾）**

**问题描述**：probes.py docstring 与 check.py 头注释均承诺「阻断级仅 2：空正文(0字) / 确认级认知泄露；其余一律 warning 交由 Auditor 审阅」，且强调「探针绝不越权检测文学文风与排版节奏」。实现却把 `probe_unregistered_fatalities`（一个建立在 L2 语义线索词表上的探针——BUG#47 注释自己承认「词表在这一层永远是够用就好」）升格为 error 级硬阻断。≥3 方可信来源（docstring、注释、BUG#47 分层设计）一致指向 2 阻断级，代码给 3。已按 FP-1 单列误报面，此处单列契约违背本身。

**触发场景**：任何按契约审查本模块的审计/测试，都会发现文档宣称的定级与 `all_passed` 公式不一致；按契约写的回归测试（断言只有 2 类 error）直接失败。

**建议修法**：二选一并闭环：(a) 尊重契约——fatalities misses 降 warning，`all_passed` 回到 `(total_words>0) and epistemology.passed`；(b) 确要硬化——修订 probes.py docstring、check.py 头注释、README 探针矩阵三处，立项第三阻断级并配「观尸/回忆不误报」的回归测试。

---

**[SEVERITY: L2] [类型: 契约/覆盖差异] check.py:526（`if chapter_id:` 全书模式不跑正文探针）**

**问题描述**：无 chapter_id 的「全书体检」完全不执行 run_all_probes——确认级认知泄露、未登记死亡、称谓/物象落地、对白占比只对 `check ch_XXX`、`audit`、cruise 单章链可见。Stage 0C 主控体检（scan_ledger_integrity docstring 自称的用途）打 ✅ 不代表正文层清白；而 Librarian 每 10 章巡检若只跑 `check`（手册场景）会系统性漏掉 prose 层问题。该覆盖差异在 help/README 均无说明。

**触发场景**：全书 `check` 0 errors 通过 → 主控认为健康 → 实际 ch_003 存在确认级泄露（只有 audit ch_003 才发现）。

**建议修法**：help/README 明示「全书 check = 台账层；正文层须 audit/单章 check」；或提供 `check --probes` 全量模式（遍历 final 章跑探针，限量报错）。

---

**[SEVERITY: L3] [类型: 一致性] cli.py:452-466（--json 与文本输出差异）**

**问题描述**：两者同源同一 dict，阻断数据（passed/errors/warnings/unfilled_slots）一致，可接受。但文本模式**完全不输出 probe_results**（字数、泄露明细、各探针 detail），JSON 模式才暴露；`config` 回显两模式都不打印（JSON 有、文本无——此点为对称性小缺口）。无信息矛盾，属信息量不对称。

**触发场景**：人类作者跑文本 check 看不到「当前 1234 字」的探针原文，审计时与 --json 输出的字段对不上。

**建议修法**：文本模式补一行 probe summary（字数/各探针 passed 计数）；或在 README 注明「文本输出为摘要视图，完整数据用 --json」。

---

**[SEVERITY: L3] [类型: 覆盖缺口] check.py:265-270（16 表清单边界）**

**问题描述**：清单覆盖 state/ 下 14 表 + indices/ 2 索引，但 `state/history/ch_XXX.json`（每章全息快照，README:26 自述的组成部分）与 `state/inbox/proposal_*.json` 不在可解析性巡检内。history 快照损坏不影响运行，但会让 snapshot rollback 缺料——正是 check 反复推荐的恢复手段。

**触发场景**：history/ch_007.json 损坏 → rollback ch_007 时失败，而 check 从未提示该文件损坏。

**建议修法**：history 目录纳入「损坏 warning」（不上 error，避免与蒸发态误判混淆）；inbox 提案做 JSON 可解析性抽查。

---

## 三、汇总

| 类型 | L1 | L2 | L3 | 小计 |
|---|---|---|---|---|
| 假阴性 | 1 | 8 | 4 | 13 |
| 假阳性 | 2 | 5 | 4 | 11 |
| 健壮性 | 3 | 2 | 1 | 6 |
| 其他 | 1 | 1 | 2 | 4 |
| **合计** | **7** | **17** | **10** | **34** |

**假阴性最集中的结构性问题**：`except Exception: pass` 家族（RB-2/RB-4/RB-5）让六节巡检 + 台账七项交叉校验随时可被一行畸形数据整体静默；epistemology 的 break 逻辑（FN-4）让确认级泄露判定退化成「第一段含关键词对白定生死」；timeline/ledger/relations-history/debts-self 四条任务点名规则零实现。

**假阳性最危险的一条**：FP-1——「望着尸体冰冷僵硬」这类每章必现的合规句，经 35 字共现窗口 + 无观察/回忆守卫 + error 级消费，会把一条完全合法的正文打成 exit 1 硬阻断，且与该模块 docstring 的 2-阻断级契约正面冲突。

**修复优先级建议**：RB-3 / RB-1 / RB-2（崩溃与静默卸载，成本最低收益最大，且不触碰业务口径）→ FP-1 / OT-1（契约对齐，先修订文档立项或降级，二者必须同时做）→ FN-4 / FP-2 / FN-3（单点逻辑修）→ 其余按 L2/L3 排期。
