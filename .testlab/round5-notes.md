# 第五轮 · 工作笔记（完结）

> 作者本轮 6 项指令（原话摘要）：
> 1. 「刚刚的问题都搞完了吗？」
> 2. 「给人物角色的存活状态添加一个"未知"选项，也就是"生死不知"的意思。」
> 3. 「本地引擎 engine 不要去管文学性方面的判断；比如说字数限制，对白占比限制等等。」
> 4. 「engine 的某些判断不要太死板，需要灵活一点；有些字段应该可以是选填，没有检测到也不要去报错；
>     我不希望开启【无人值守】的时候动不动就 error 报错。」
> 5. 「增强系统的自愈能力。」
> 6. 「以上问题全部解决之后，提交所有变更，然后 PR 到主分支。」

---

## 0. 第 1 项回答（第四轮收尾状态）

第四轮全部缺陷（CT52～CT68）已修完并复证：电池 117/117、SKILL 面审计 108/108、
新旧引擎差分回归 12 张状态表逐字节一致、四工作区 `check` 全 exit 0。
两项待人类裁决已按授权代为定案：**FP-4 = 实施**（回忆/闪回豁免，CT68）、
**FN-8 = 驳回**（正文层死亡检测保持 warning-only，避免重新破坏 BUG#47 的契约分层）。
本轮开始时仅剩「文档归档 + 提交 + PR」未做，已与第五轮变更一并交付。

---

## 1. FIND-CT69（第 2 项）：`unknown` 生死不明 = 第四态

| 面向 | 落地 |
|---|---|
| 枚举 | `_LIFE_STATUS_NORM` 新增 `unknown` + 11 个中文同义写法（生死不明/生死不知/生死未卜/存亡未知/未知/未确认…） |
| 推断分流 | `_infer_life_status()`：**先判「生死未确认」再判死亡词**——「坠崖后生死不知，疑似身亡」落 `unknown`，不被后半句死亡词抢判成 deceased |
| 语义边界 | `missing` = 下落不明（人不见了）；`unknown` = 存活状态本身未确认。二者都**不是死亡**：不进已故黑名单、不受复活闸门约束、可正常登场 |
| 展示 | 新增 `LIFE_STATUS_LABELS` + `life_status_label()`（唯一中文标签源，简报/trace/ask 共用） |
| 校验 | `check.py` 枚举白名单纳入 `unknown`（写 `unknown` 不再报「强类型枚举越界」） |
| 简报 | 新增「❓ 生死不明人物悬念账」板块（`ops.py`）：列出 unknown/missing 角色 + 最后现身章 + 「严禁擅自坐实生死」硬约束；在场候选行的状态后追加「生死: 生死不明」；无此类角色时整段不渲染（零噪音） |
| 文档 | `templates/README.md`、`templates/beats.md`（注释态四态示例）、screenwriter/evolution SKILL |

**端到端实证（long-lab 真实链）**：ch_019 幽影使者落河 → `life_status: unknown`；
ch_020～ch_023 四份细纲简报均带 ❓ 悬念账，且该角色**不在**🚫 黑名单、**仍在**👥 在场候选；
ch_023 显式改写 `life_status: alive` 收束悬念 → ch_024 起悬念账整段消失（0 命中）。
中文写法「生死不知」经 sync 自动归一为 `unknown` 并留 🩹 痕（靶点 C-19e）。

---

## 2. FIND-CT70（第 3 项）：引擎彻底退出文学性判断

| 撤除项 | 原位置 | 处置 |
|---|---|---|
| 对白行占比探针（25%~55%） | `probes.py probe_dialogue_ratio` | **整块删除**；`check.py` 对应告警删除；`config.py` 的 `dialogue_ratio` 旋钮退役（旧 project.json 带该键静默容忍、不参与计算） |
| 字数分档判定 | `probes.py` 体量遥测 | `severe_short / short / long` 三档全撤，只余 `ok / empty`；不再输出 `words_range` |
| 体检「正文体量遥测」告警 | `check.py`（BUG#42 引入） | 整块撤销 |
| sync「低字数」告警 | `ops.py sync_low_words` | 删除 |
| cockpit「🟡 节奏黄牌 + 建议换气」 | `cockpit.py _rhythm_panel` | 改为纯事实：「章型连排事实：末尾连续 N 章「X」（纯计量，引擎不评价节奏好坏）」；均章字数标注「不设达标线」 |
| 审计报告字数行 | `ops.py` | 「{words} 字（纯计量，引擎不做体量判定）」 |
| dehydrator SKILL 25%~55% 硬指标 | `.agents/skills/dehydrator/SKILL.md:105` | 改写为纯文学指引 + 明示「引擎已移除该探针，不要为凑百分比增删对白」 |

**唯一保留的字数硬判定**：`空正文（0 字）拒绝封存`——这是数据完整性（封存空章会让整条流水线失去意义），不是文学判断。
`words_per_chapter` 保留在 config，但语义收窄为**作者的体量规划值**（供大纲 `target_words` 与写手提示词参考），不参与任何判定。

**实证**：200 字极短章走完 finalize → sync → check 全链 exit 0、零体量告警（靶点 C-20c）；
体检与审计报告全文再无「对白占比 / 参考区间 / words_range」字样（C-20a/b）。
顺带作废了 `.testlab/audit/probes.md` 里 FP-9（`dialogue_ratio` 配成 dict 崩栈 / 配成字符串阈值畸变）
与 L3「`long` 档假阳性」两项历史档案——判据本身已被移除，缺陷不复存在。

---

## 3. FIND-CT71 / CT72 / CT74（第 4 项）：判据松绑，无人值守不刷屏

### 3.1 `scan_ledger_integrity` 两级重构（CT71）

签名 `List[str]` → `(errors, warnings)`。十项交叉校验重新定级，判据是**「会不会让剧情讲不通」**：

| 项 | 旧 | 新 | 理由 |
|---|---|---|---|
| a 生死状态自相矛盾（弧光记死却标在世） | error | **error** | 真叙事穿帮，必须作者/Stage 4C 定夺 |
| b/c/d 引用断裂（holder / 恩怨双方 / 关系双方幽灵 ID） | error | warning 🩹 | 账面瑕疵，sync 可自动规范/补建 |
| e 伏笔字段残缺（缺 planted_ch / resolved_ch） | error | warning 🩹 | **选填字段**，sync 自动补并标 inferred |
| f 时间线残缺 / 锁定事实指向未入账章 | error | warning | 统计口径受扰，不影响下一章创作 |
| g 资金池透支 / 余额非数值 | error | warning 🩹 | 透支是剧情事实（CT67 sync 侧早已 warning-only，check 侧却仍阻断＝自相矛盾）；非数值由 sync 消毒 |
| h 恩怨自指 / i 关系轨迹重复章 / j 时间线倒置 | error | warning 🩹 | 全部可确定性自愈 |

### 3.2 `check_id_integrity` 定级重排（CT72）

- **仍阻断（2 类）**：① 指定章节的细纲文件不存在（无从校验，不是「缺字段」）；② 已故角色在后续章节登场（复活闸门，CT68 豁免标记除外）。
- **降为 warning + 🩹（11 处）**：ID 格式非法、引用未定义人物/道具、`new_entities` 撞号、ID 与姓名不一致、`character_status` 键非法/未定义、伏笔 ID 未登记、台账槽位污染。
- 降级项统一追加自愈指引（同一份 `_HEAL_SUBSTR` 表驱动），作者一眼看出「这条不用手工改表」。

### 3.3 同类提醒折叠（CT74）

`collapse_similar_warnings()`：同类 ≥3 条只留第一条完整文案（含 💡 方案），
中间插入「📦 同类共 N 条，涉及：…」清单，其余折叠。不改判、不降级、不丢信息。
实测 long-lab ch_010：7 条「地点数据残缺」压成 1 行，报告从 20 行降到 8 行。

### 3.4 无人值守（cruise）

- 定级松绑后，账面瑕疵不再触发 `check errors>0` 停机；
- 心跳行新增 `🩹xN` 计数，批次报告带 `healed` / `healed_count`；
- **FIND-CT75**：巡航报告不再被 `[:1500]` 截断（半截 JSON 无法机器判读，第四轮实测踩坑），
  改为全量落盘 `log/cruise_report.json` + 完整打印；
- 退出码契约不变：0 通过 / 1 业务阻断（真矛盾刹车、等待超时）/ 2 参数 / 3 环境 / 4 系统故障。

**实证**：回滚到 ch_014 后 `cruise --once` → exit 0、明说「等待作者产出」、`planned=["ch_015"]`、
`results=[]`（不带伤入账）、报告可 `json.loads`、零 Traceback 零 ❌（靶点 C-17）；
vol_01 整卷封存后 `cruise --vol vol_01 --once` → exit 0 + 卷末自动刹车三连（C-18）。

---

## 4. FIND-CT73（第 5 项）：自愈层（公理二落地）

新增 `state.py` 自愈层（模块级函数 + sync 收尾 `heal_tables_pass`），**10 类动作**：

| # | 动作 | 触发 | 处置 |
|---|---|---|---|
| H1 | ID 笔误规范化 | `P001` / `p001` / `ｐ＿００１` / `P-012` | NFKC + 正则 → `p_001`；**已合法的 `p_1` 不重编号**（改号会牵动全表引用） |
| H2 | 撞号改派 | `new_entities` 声明的 ID 已属于**另一个名字** | 取新号入账，原记录分毫不动，同章「ID+姓名双匹配」的引用一并改指新号 |
| H3 | 改名留别名 | 细纲给既有实体换了名字 | 旧名降级进 `aliases`（称谓探针/旧章引用不失联）+ 留痕；括号补语差异视为同一人直接更新 |
| H4 | 未建档自动取号 | `present_characters` / `character_status` 引用了不存在或非规范的键 | 规范键直接用；姓名串则 `id_next` 取号建档，**绝不把姓名串当物理 ID**（幽灵记录源头） |
| H5 | 数值自愈 | `tier_rank: "第三重"`、`injury_level: 9`、`charges: 3.5`、`renown: "abc"` | 解析（含中文数字/带单位串）→ 区间夹取 → 实在解析不出则**摘除字段**（选填，留空比塞假值安全） |
| H6 | 伏笔补章 | 缺 `planted_ch` / resolved 却缺 `resolved_ch` | 按最早推进章或本次入账章补，**必须标 `planted_ch_source: inferred`**（不猜真实章） |
| H7 | 经济数值消毒 | 池余额 / baseline / 流水 delta 非数值 | 转整数；转不动置 0 并留痕（避免下游算术崩栈） |
| H8 | 恩怨自指清除 | `source_char == target_char` | 删除幽灵条目 + 留痕 |
| H9 | 关系轨迹去重 | 同章多条 history | 保留每章最后一条（与 sync 按章幂等同口径） |
| H10 | 幽灵记录清扫 | 槽位污染 / 非 dict 畸形条目 | id+name 双槽位 → 删；仅 name 是槽位 → **保号改名**「未命名人物[p_012]」（绝不因一个脏字段删角色） |

**四条设计铁律**（写进 `engine/README.md` 不变量 9）：
1. 能确定性推断的自己修；2. **绝不偷偷改**——每个动作写进 sync 报告 `healed`（🩹 公示，含原值）；
3. **绝不猜剧情**——叙事因果（复活、生死矛盾、真实回收章）只做「可追溯推断值 + 标注」或原样保留并提醒；
4. 幂等——干净数据重放**零自愈动作**。

**数值区间表 `NUMERIC_FIELD_BOUNDS` 由 `state.py` 单点定义，`check.py` 直接 import**：
体检口径 = 自愈口径，杜绝两处漂移（缺陷#15 双份词表是前车之鉴）。

**实证**：
- 撞号：声明 `p_010 = 测试新人甲`（p_010 实为阿福）→ 阿福姓名不变、新人落 `p_012`、输出「撞号自愈」🩹（C-22）。
  这条修掉了旧版最阴的一类污染——`if ename: rec["name"] = ename` 会把既有角色**改名换姓**。
- 数值：`"第三重"`→3、`9`→5（夹取）、`"abc"`→摘除、`"两"`→2（C-23）。
- ID：`P005`→`p_005`，台账零幽灵键（C-24）。
- 伏笔：删掉 `GUN-001.planted_ch` + 让 `GUN-002` resolved 缺章 → check exit 0 + 🩹 指引；
  跑一次 sync 后两章号补齐并标 inferred；复检同类提醒消失（C-21a/b/c）。
- 幽灵：双槽位记录被删、半槽位记录保号改名（C-26）。
- **假自愈回归**：long-lab 30 章全链重建 → 🩹 动作 **0** 条、警告 1 条（ch_022 既有的 ledger 漂移探针）；
  test-lab `sync ch_002 --force` → 🩹 0 条；C-27 单章靶点同为 0。
- **脏数据实证**：field-lab（第三轮批次 B 故意留下的脏类型）跑一次 sync 即自动修好
  `tier_rank "三"`→3、`charges 3.5`→3、`max_charges "三"`→3、`scale_tier "一"`→1、`danger_tier "高"`→摘除；
  第二次重放 🩹 归零（幂等）。field-lab 由此兼作**自愈回归靶场**，故其脏值保留不清洗。

---

## 5. 保留为 error 的判据（裁决记录）

作者要求「别太死板」，但松绑不等于放水。以下仍硬阻断，逐条给出理由：

| 判据 | 理由 |
|---|---|
| 已故角色无豁免登场（复活闸门） | 叙事因果硬矛盾；CT68 已给合法出口（`appearance: "回忆"`） |
| 台账生死状态自相矛盾 | 同上，且引擎无从判断哪一侧是真 |
| 充能透支 | 数值守恒，透支即账目造假；剧情需要欠账请走资金池（池透支已是 warning） |
| 空正文封存 | 数据完整性（不是文学判断）：封存空章让下游全链失去意义 |
| 细纲文件不存在 / 无有效 front-matter | 无从校验，不是「选填字段缺失」 |
| 状态表损坏 / 蒸发 / 半提交哨兵残留 | 台账不可信时任何结论都是假绿 |
| 确认级角色认知泄露 | 一致性范畴（角色知道了不该知道的事），非文学审美 |
| SSOT 覆盖 / init 覆盖已有书籍 | 不可逆毁灭性操作 |

---

## 6. 本轮验证总账

| 项目 | 结果 |
|---|---|
| 长篇电池（A/B/C 三段） | **136/136 ✅**（第四轮 117 项 + 本轮新增 C-17～C-27 共 19 项） |
| SKILL 面审计（10 个 SKILL） | **110/110 ✅**（命令存在性 / 旗标合法性 / 文件契约路径 / 零命令红线） |
| long-lab 全量重建 | 30 章 ｜ 48,178 字 ｜ 事故 **0** ｜ 自愈 **0** ｜ 警告 1（既有探针） |
| 差分回归（第五轮前 vs 后） | 14 张状态表 + 索引：12 张逐字节一致，`milestones.json` / `sync_log.json` **仅时间戳差异** ⇒ 语义零漂移 |
| 四工作区 `check` | long-lab / test-lab / field-lab / probe 全 exit 0、0 errors |
| 编译 | `py_compile engine/*.py` + 三个测试工具全 0 错 |
| 改动文件 | 引擎 9 个（state/check/id_tracker/probes/ops/cli/config/cockpit/cruise）+ 文档 6 个（engine/README、templates/README、templates/beats、screenwriter/evolution/librarian/dehydrator SKILL）+ 测试资产 3 个 |

---

## 7. 已知边界（有意不做）

1. **不重编号**：`p_1` 这类未补零但合法的 ID 保持原样（补零只是美观，改号会牵动全表引用与历史快照）。
2. **不猜剧情**：伏笔真实埋设/回收章、生死定论、改名 vs 撞号的最终裁定，一律交作者/Stage 4C；引擎只补可追溯的推断值并标注来源。
3. **不清洗 field-lab 脏值**：它是自愈层的常驻回归靶场。
4. **test-lab 金基座的既有偏差**（items charges 3 vs 4、多余 DEBT-AUTO 条目）系第三轮遗留，
   第四轮已用新旧引擎差分证明与本轮无关，仍按原样保留。
5. **退出码契约不动**：巡航真矛盾刹车仍是 exit 1（业务阻断），不因「不要动辄报错」而改成 0——
   作者要的是**别把可自愈的账面瑕疵当阻断**，不是要引擎对真矛盾装看不见。

---

## 附录 A · 逐处改动清单（从已提交的 HEAD 机器提取，非手抄）

> 提取方式：`git show HEAD:<文件>` 后按 `FIND-CT69~CT75` 标记逐行定位。
> 每处都带编号注释落盘，便于日后 `grep -rn "FIND-CT7" engine/` 一次性回溯全部改动点。

| 项 | 文件 | HEAD 行号 | 该处做了什么 |
|---|---|---|---|
| CT69 | `engine/ops.py` | 524 | unknown_lines = []   # FIND-CT69：生死不明/失踪的悬念人物（可登场，严禁坐实生死） |
| CT69 | `engine/ops.py` | 534 | FIND-CT69：unknown/missing 既不进黑名单也不算普通在世，单独立悬念账 |
| CT69 | `engine/state.py` | 225 | FIND-CT69（作者需求）：新增第四态 unknown =「生死不知」。 |
| CT69 | `engine/state.py` | 342 | FIND-CT69：先判「生死未确认」再判死亡词——「生死不明」里含「不明」不含死亡词， |
| CT70 | `engine/README.md` | 16 | | `probes.py` | 确定性物理事实探针 | 纯确定性物理/数据探针；阻断级仅 2：空正文(0字)/确认级认知泄露；其余  |
| CT70 | `engine/README.md` | 39 | 8. **引擎不做文学判断（FIND-CT70 · 作者裁定）**：字数区间、对白占比、章型连排"疲劳"等一切审美/体裁裁量**不得 |
| CT70 | `engine/check.py` | 857 | FIND-CT70（作者裁定 · 引擎退出文学性判断）：原「正文体量遥测」 |
| CT70 | `engine/cockpit.py` | 62 | FIND-CT70（作者裁定 · 引擎退出文学性判断）：原「🟡 节奏黄牌 + 建议下一章安排 |
| CT70 | `engine/config.py` | 24 | FIND-CT70（作者裁定 · 引擎退出文学性判断）：本项**只是作者的体量规划值**， |
| CT70 | `engine/config.py` | 28 | 原 dialogue_ratio（对白行占比 25%~55%）已于 FIND-CT70 整项退役：对白配比属 |
| CT70 | `engine/config.py` | 43 | "words_per_chapter": "每章正文体量**规划值** [min, max]：只供大纲 target_words 与 |
| CT70 | `engine/probes.py` | 437 | FIND-CT70（作者裁定 · 引擎退出文学性判断）：原 `probe_dialogue_ratio`（对白行占比 |
| CT70 | `engine/probes.py` | 707 | FIND-CT70（作者裁定 · 引擎退出文学性判断）：字数只保留**事实计量**与「空正文」 |
| CT70 | `engine/probes.py` | 740 | FIND-CT70：level 只剩 ok / empty 两档（empty 是数据完整性问题， |
| CT71 | `.agents/skills/evolution/SKILL.md` | 88 | - **定级现状（FIND-CT71/72）**：手改台账后跑 `check`，幽灵 ID 引用、伏笔缺 `planted_ch`/ |
| CT71 | `.agents/skills/librarian/SKILL.md` | 54 | > 该节现按**两级**输出，分流处置完全不同（FIND-CT71 定级松绑）： |
| CT71 | `engine/README.md` | 13 | | `cruise.py` | 无人值守巡航批次编排 | 计划钳制 min(N+K,M) 且单批 ≤`cruise_max_chap |
| CT71 | `engine/README.md` | 17 | | `check.py` | 全书体检（16 表巡检） | 未填槽位闸门（warning 清单，Stage 0C 验收依据）；sta |
| CT71 | `engine/README.md` | 40 | 9. **两级定级 + 自愈留痕（FIND-CT71/72/73 · 公理二落地）**： |
| CT71 | `engine/check.py` | 105 | """台账内部交叉引用自洽体检（v4.3.2 缺陷#20 / #24 · FIND-CT71 分级重构）。 |
| CT71 | `engine/check.py` | 114 | FIND-CT71（作者裁定 · 判据不要太死板）：旧版把 a~j 十项交叉校验的**全部**结论 |
| CT71 | `engine/ops.py` | 2067 | FIND-CT71：只有真矛盾（error 级）才走 Level 2 上报链；账面瑕疵列作提醒， |
| CT72 | `engine/README.md` | 21 | | `id_tracker.py` | ID 发号/清册/追踪/完整性 | 全表 + beats 双扫描防撞号。**FIND-CT7 |
| CT72 | `engine/id_tracker.py` | 837 | FIND-CT72（作者裁定 · 判据不要太死板 + 增强自愈）：ID 类问题的**定级重排**。 |
| CT72 | `engine/id_tracker.py` | 869 | FIND-CT72 前为 error——但既然引擎自己能扫掉，就没必要拦住整条流水线）； |
| CT72 | `engine/id_tracker.py` | 1176 | FIND-CT72：凡是引擎自己能修的提醒项，统一挂一条 🩹 自愈指引， |
| CT73 | `engine/README.md` | 14 | | `state.py` | 八表持久化与细纲增量合账 + **自愈层** | **原子写盘**（tempfile+os.repla |
| CT73 | `engine/check.py` | 377 | FIND-CT73：凡是 sync 能自己修好的提醒项，统一挂一条 🩹 指引—— |
| CT73 | `engine/check.py` | 673 | FIND-CT73：区间表不再在 check 侧复制一份——直接 import state.NUMERIC_FIELD_BOUNDS |
| CT73 | `engine/cli.py` | 589 | FIND-CT73（公理二 · 自愈留痕）：引擎自己修好的脏数据逐条公示， |
| CT73 | `engine/cruise.py` | 143 | FIND-CT73：自愈动作在无人值守日志里必须可见（🩹xN），否则引擎"悄悄把表改好了" |
| CT73 | `engine/cruise.py` | 289 | FIND-CT73：批次报告带上自愈条目，无人值守跑完能一眼看出引擎改过什么 |
| CT73 | `engine/state.py` | 618 | FIND-CT73（公理二 · 自愈层）：脏数据在**写盘前**就地修正，且每一步都留痕 |
| CT73 | `engine/state.py` | 800 | """改名自愈（FIND-CT73 H3）：旧名**降级为别名保留**，绝不无声蒸发。 |
| CT73 | `engine/state.py` | 1219 | FIND-CT73（公理二 · 自愈层）：本次入账过程中引擎自己动手修好的每一处， |
| CT73 | `engine/state.py` | 1757 | FIND-CT73 H4：物理 ID 必须规范——键是「P001/p001」这类笔误就规范化， |
| CT73 | `engine/state.py` | 2510 | 10.9 FIND-CT73（公理二 · 自愈层）：全表收尾自愈一遍过（幂等）—— |
| CT73 | `engine/state.py` | 2529 | FIND-CT73：🩹 自愈动作清单（引擎自己修好的脏数据，逐条可追溯） |
| CT74 | `engine/README.md` | 17 | | `check.py` | 全书体检（16 表巡检） | 未填槽位闸门（warning 清单，Stage 0C 验收依据）；sta |
| CT74 | `engine/README.md` | 44 | - **假自愈是比漏报更严重的缺陷**：干净数据重放必须零自愈动作（回归靶点 C-27），同类提醒 ≥3 条要折叠成一行（C 段 + |
| CT74 | `engine/check.py` | 58 | """同类提醒折叠（FIND-CT74 · 作者裁定：无人值守不要刷屏）。 |
| CT74 | `engine/check.py` | 928 | FIND-CT74：同类提醒折叠后再交付（不改判、不丢信息，只压重复文案） |
| CT75 | `engine/README.md` | 13 | | `cruise.py` | 无人值守巡航批次编排 | 计划钳制 min(N+K,M) 且单批 ≤`cruise_max_chap |
| CT75 | `engine/cli.py` | 616 | FIND-CT75（无人值守友好）：巡航报告旧版被 `[:1500]` 硬截断—— |

**合计 42 行带编号标记**（表内 44 条＝「项 × 行」组合，个别行同时标注两项，如 `FIND-CT71/72`）；不含未打标记的配套改动（`_LIFE_STATUS_NORM` 同义词表、`LIFE_STATUS_LABELS`、`Tuple` 导入、四处 `if ename: rec["name"]=ename` 改写等）。

### 本轮引擎侧改动量（`git show --stat HEAD -- engine/ templates/ .agents/`）

```
.agents/skills/auditor/SKILL.md      |   1 +
 .agents/skills/dehydrator/SKILL.md   |   2 +-
 .agents/skills/evolution/SKILL.md    |   4 +-
 .agents/skills/librarian/SKILL.md    |  17 +-
 .agents/skills/screenwriter/SKILL.md |   8 +-
 .gitignore                           |   7 +
 engine/README.md                     |  20 +-
 engine/check.py                      | 191 +++++---
 engine/cli.py                        |  39 +-
 engine/cockpit.py                    |  11 +-
 engine/config.py                     |  12 +-
 engine/cruise.py                     |   9 +-
 engine/id_tracker.py                 | 111 ++++-
 engine/ops.py                        | 371 ++++++++++++---
 engine/pack.py                       | 121 ++++-
 engine/probes.py                     |  78 +---
 engine/state.py                      | 846 ++++++++++++++++++++++++++++++++++-
 templates/README.md                  |   4 +-
 templates/beats.md                   |  10 +
 19 files changed, 1617 insertions(+), 245 deletions(-)
```

## 附录 B · 你可以自己复核的 6 条命令

```bash
# 1) 改动是否已提交、是否已推到 PR 分支
git log --oneline -2 && git ls-remote origin arena/01a0bd9b-antigravity-novel

# 2) 本轮 7 项的全部落点（44 处带编号标记）
grep -rn "FIND-CT69\|FIND-CT70\|FIND-CT71\|FIND-CT72\|FIND-CT73\|FIND-CT74\|FIND-CT75" engine/ templates/ .agents/

# 3) 该删的是否真删了（三个都应输出 0）
grep -c "def probe_dialogue_ratio" engine/probes.py
grep -c '"dialogue_ratio"' engine/config.py
grep -c "sync_low_words" engine/ops.py

# 4) unknown 四态是否通电
python -c "from engine.state import _infer_life_status as I, life_status_label as L;\
print(I('坠入护城河，生死不明'), L('生死不知'))"        # ⇒ unknown 生死不明

# 5) 自愈层是否真的会动手（拿脏数据基座 field-lab 的副本跑一次）
cp -r workspace/field-lab /tmp/fx && python studio.py sync ch_017 --force -w /tmp/fx | sed -n '/🩹/,$p'

# 6) 全量回归（电池 136 项 + SKILL 面审计 110 项）
python .testlab/tools/long_lab_battery.py | tail -3
python .testlab/tools/skill_surface_audit.py | tail -3
```
