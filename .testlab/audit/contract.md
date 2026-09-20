# Novel Studio v4.4.0 引擎静态审计报告 —— 契约层 6 模块缺陷候选清单

- 审计对象：`engine/id_tracker.py`（实 1023 行）、`engine/parser.py`（实 523 行）、`engine/schema.py`（实 210 行）、`engine/config.py`（实 155 行）、`engine/errors.py`（实 28 行）、`engine/ledger.py`（实 12 行）
- 审计方式：全文件 read 通读 + 关联调用链静态走查（engine/state.py、engine/ops.py、engine/cli.py、engine/check.py、templates/README.md）。未执行任何引擎代码，不确定项已标 [需动态验证]。
- 行数说明：任务描述的行数（931/477/176/134/20/10）与实际文件不符（全部偏少），本报告一律以实际行号为准。
- 严重度定义：
  - **L1** = 在常规路径上静默丢失/污染台账数据，或发放撞号 ID，且全链路零告警（假绿）。
  - **L2** = 有明确触发场景的功能缺陷：边界失效、校验假绿、退出码违背契约。
  - **L3** = 触发面较窄的一致性/健壮性/体验问题。
- 背景锚点：AGENTS.md 退出码铁律 0/1/2/3/4；法定 ID 矩阵 p_001/it_001/fac_001/loc_001 + GUN/KNO/MIS/DEBT-AUTO/LOCK/ms_ 引擎派生；强类型字段白名单与三大被禁别名 current_location / disposition / current_owner。

---

## 一、engine/id_tracker.py

### ID-1 [SEVERITY: L1] id_tracker.py:89-190（id_next 纯读无预留）+ 调用点 engine/ops.py:1017、engine/ops.py:1070
- **问题描述**：`id_next` 是纯只读函数——扫 state 表 + beats + 文档目录求 max+1，**不发号、不落占位、无锁**。核心爆点在自动打捞路径：`ops.py` 的 emergent 循环（999-1024 行）对同章涌现的每个新实体连续调用 `tracker.get_next_id(cat)`，而 persons.json / items.json 尚未落账、beats 文件也要等循环结束后（ops.py:1083）才整体回写。于是同一章若涌现 ≥2 个新实体（如两个新有名配角、或两个新道具），两次调用读到完全相同的状态，返回**同一个 ID**（如都是 p_004）。细纲 frontmatter 因此写入两条同 ID 条目；sync 时 `state.py` 的 `if eid not in xxx_db` 使第二条被静默跳过（id_tracker.py:824-852 的注释自认这条路径"无声吞掉"）——第二个实体永久不入账，check 全程 0 error。
- **触发场景**：Stage 4A 审计一章正文，该章同时涌现两个以上未建档实体（长篇常态路径，非边角）；或两个终端/两个巡航批次并发执行 `id next`。
- **建议修法**：`get_next_id` 增加 `exclude` 参数或在调用方循环内维护本地已用号集合逐次自增；更彻底的做法是引入 `state/.id_reservations` 预留文件（分配即落盘、实体真正建档后释放）。并发场景加文件锁或至少文档明示"仅限单线程顺序调用"。
- **重复调用语义补充**：同状态下重复 `id next` 结果稳定（幂等，这是设计优点）；不稳定的是"分配后未及时建档"的窗口期。**[需动态验证]**：构造一章双新实体 emergent，复现两条同 ID 与 sync 静默丢一条。

### ID-2 [SEVERITY: L2] id_tracker.py:156-179（扫描范围盲区）
- **问题描述**：双扫描只覆盖 `outlines/**/beats/*.md` 与 `characters/ entities/ bible/ worldview/ docs` 下的 .md。**卷纲规划文件**（如 `outlines/vol_01/outline.md`、roadmap/backlog）、**正文定稿与草稿**（`manuscript/**/final|raw/*.md`）、`log/` 一律不在扫描范围。若某 ID 只先行出现在卷纲规划或定稿正文中（先规划 GUN-005、beats 尚未落），`id next gun` 会重发已占用号 → 跨文档撞号。
- **触发场景**：编剧按卷纲预排的 ID 手工写入细纲；或 final 正文先行引用某道具 ID 而 beats 未同步。
- **建议修法**：扫描目录扩为 `workspace.glob("**/*.md")` 或至少补齐 `outlines/**/*.md` + `manuscript/**/*.md`，并对超大树做深度/大小上限保护。

### ID-3 [SEVERITY: L2] id_tracker.py:198-296（id_list 缺 milestones 类目）
- **问题描述**：`id_list` 返回值字典只有 persons/items/lines/places/factions/debts/locked_facts 七个键，**没有 milestones**；各 filter 元组（209/223/236/251/262/273/286 行）也不含 ("ms","milestone")。因此 `python studio.py id list milestone` / `id list ms` 静默输出空清单——ms_ 是法定 ID 类目（id next milestone、trace milestone 均正常），却在总账清册中永久隐身，"清册与实际表漂移"。
- **触发场景**：作者想核对已有里程碑编号，跑 `id list milestone` 得到空，误判无里程碑而重发 ms_001。
- **建议修法**：result 增补 `"milestones": []` 键与对应 filter 分支，字段取 id/title/status/target_ch。

### ID-4 [SEVERITY: L1] id_tracker.py:54（debt 发号）+ 关联 engine/state.py:1265-1289（DEBT-AUTO 种子）
- **问题描述**：DEBT 侧两套发号体系并存且种子会语义碰撞：
  1. `id next debt` 仍发序号 `DEBT-001`（pattern `DEBT-(\d+)` 只匹配数字，自动键不计入水位），而台账中 99% 记录是 `DEBT-AUTO-<hash>`——作者若采用速查表手填编号，即与引擎自动键两套并存（ops.py:496-498 已在速查表规避此诱导，但 `id next debt` 命令本身未规避）。
  2. 真正的 L1 点：DEBT-AUTO 派生种子为 `f"{ch_id}|{source}|{target}|{type}"`（state.py:1267），**不含 desc**。同章、同双方、同类型、不同事由的两条恩怨（如 ch_008 中 p_001→p_002 既结"杀父之仇"又欠"夺财之恨"，type 均为 grudge）会算出**同一 hash id**；sync 的"同 id 先删后加"语义（state.py:1272）把前一条静默抹掉——恩怨记录无声丢失，永不平账。sha1 截断 8 hex 的生日碰撞另计（概率低，非主因）。
- **触发场景**：单章内对同一对角色声明两条同类型不同 desc 的 debts 增量；`--force` 重放时反而是期望行为（幂等），但正常首写同样中招。
- **建议修法**：种子追加 desc（或 desc 归一化哈希）；或种子碰撞时自动追加序号后缀并 warning。`id next debt` 输出改为"由引擎按章节+双方+类型自动派生，无需手填"。
- **[需动态验证]**：构造同章双恩怨条目观察 debts.json 最终条数。

### ID-5 [SEVERITY: L2] id_tracker.py:814-1002（ID 格式校验只覆盖 p_/it_）
- **问题描述**：`check_id_integrity` 只对 `p_`（869-871、966 行）与 `it_`（981 行）引用做 `^\w+_\d+$` 格式校验；`loc_`/`fac_`/`GUN-`/`ms_`/`DEBT-`/`LOCK-` 引用零格式校验；**章节 ID 完全零校验**——细纲里写 `chapter_id: ch_1` 或 `CH_001` 均可入账（CLI 入口有 argparse 归一，cli.py:148-153，但 frontmatter 内 chapter_id 用原值）。`trace_id` 的 `detect_id_category` 只认小写 `ch_` 前缀（id_tracker.py:84-85），`CH_001` 落 unknown 兜底"未检索到"——同一 ID 在 check/trace 两个入口结论不一致。
- **触发场景**：作者手写细纲用 `CH_001`/`ch_1`；跨卷复制粘贴产生大小写变体；cockpit/trace 按 ID 查章节时误报不存在。
- **建议修法**：建立全类目统一 ID 正则表（各前缀 + `\d{3,}`，大小写不敏感比对），check 阶段对全部引用字段执行；trace 的 detect 前先归一化大小写。

### ID-6 [SEVERITY: L3] id_tracker.py:727-764（trace 兜底两处隐患）
- **问题描述**：(a) 10.1 精确逆查 `return trace_id(workspace, p_id)`（729-747 行）——若台账条目 id==name（手工编辑产生的畸形数据，如人物 id 就叫"张三"且 name 也是"张三"），递归无限进行 → RecursionError → exit 4；(b) 10.2 模糊匹配（750-761 行）以 `tid in p_id` 命中即返回首个实体且 `found=True`，报告不标注"模糊命中"——`trace p_0` 会返回某个人物的完整档案，误导使用者以为精确命中。
- **触发场景**：(a) 手工改 state 表后 trace；(b) trace 短 ID/短名。
- **建议修法**：(a) 递归加 visited 集合或深度上限；(b) 模糊命中在 profile/human_readable 首行标注"⚠️ 模糊匹配结果"并列出全部候选。

### ID-7 [SEVERITY: L3] id_tracker.py:26-38（_strip_html_comments 两个边角）
- **问题描述**：(a) slot 清洗正则 `\{\{slot:[^|}]*\|` 只处理**带默认值**的槽位；无 DEFAULT 的 `{{slot:p_004}}` 不被清洗，其中伪 ID 会被编号正则计入（正是 32-34 行注释想防的场景的漏网形态）；(b) HTML 注释剥离用 DOTALL 非贪婪，若作者手写出现**未闭合的 `<!--`**，剥离会一直吃到文件尾，其后所有真实 ID 被静默忽略 → 发号撞号。
- **建议修法**：slot 正则兼容无管道形态；未闭合注释至少记 warning 或保守跳过该文件并在 warning 中明示。

### ID-8 [SEVERITY: L3] id_tracker.py:783-790（declared_card_ids 过宽）
- **问题描述**：扫描 characters/entities/bible 卡片时把 `mf.stem`（卡片文件名）直接加入 declared_card_ids（790 行）。于是 beats 中引用任何与卡片同名的字符串即视为"已声明"——例如引用"灯火司"只要 `entities/灯火司.md` 存在就放行，即使 factions.json 无此势力。"防悬空引用"被放宽到近乎失效。
- **触发场景**：卡片先行、台账滞后的工作流中，引用实际未入账实体。
- **建议修法**：stem 仅在与合法 ID 正则匹配时计入；其余情况仅做 warning 级提示。

### ID-9 [SEVERITY: L3] id_tracker.py:795-807（单章校验目标缺失即假绿）
- **问题描述**：`check_id_integrity(workspace, chapter_id)` 在指定章的 beats 文件不存在时（vol_01 硬编码路径 + glob 兜底均未命中），beats_files 为空 → 静默返回 0 errors。下游 check.py:534-535 有"细纲文件不存在"的独立报错兜底，故当前不可被利用，但函数自身契约不自洽（调用方若只用它会被假绿）。
- **建议修法**：指定 chapter_id 但找不到文件时返回一条 warning/error，而非静默空转。

### ID-10 [SEVERITY: L3] id_tracker.py:41-58 + 119-124（line 类目跨前缀共用计数器）
- **问题描述**：`id next line`（无 sub_type，仅编程路径可达，CLI 未暴露）用 pattern `(?:GUN|KNO|MIS)-(\d+)` 取三者最大值 +1——若台账已有 KNO-001，则第一发 GUN 会得到 GUN-002，违反法定矩阵"GUN-001 伏笔"的首号预期。CLI 的 `id next gun/kno/mis` 各用各的前缀，不受影响。
- **建议修法**：`line` 类目按 sub_type 拆分计数器，或文档明示共享编号空间。

---

## 二、engine/parser.py

### P-1 [SEVERITY: L2] parser.py:184-213（_strip_comment 不符合 YAML 注释规范）
- **问题描述**：行内遇见任意非引号内 `#` 即截断（208 行），**不要求 `#` 前有空白**（YAML 1.2 规范要求注释起始 `#` 前必须是空白或行首）。值中合法含 `#` 的场景被静默截断：`desc: 货号 C#117` → "货号 C"；`summary: 第#3章` → "第"。数据静默丢失且解析不报错。
- **触发场景**：任何含 `#` 的道具编号/标题/代码片段值。
- **建议修法**：仅当 `#` 位于行首或其前一个字符为空格/tab 时视为注释；否则按普通字符处理。

### P-2 [SEVERITY: L2] parser.py:240-247（tab 缩进静默改变树结构）
- **问题描述**：缩进计算只数空格（246 行 `lstrip(" ")`），**tab 不计入缩进**。用 tab 缩进的嵌套块会被判为根级键合并进顶层 dict，或被 `min_indent` 边界静默截断——整棵 YAML 树错位，无任何报错。Windows 编辑器（VS Code 默认）极易产出 tab 缩进。
- **触发场景**：作者/子代理用 tab 缩进写 frontmatter 嵌套结构（state_deltas、new_entities）。
- **建议修法**：清洗阶段检测到行首 tab 即抛 BusinessError（退出码 1，人话提示改用空格）；或先把 tab 确定性展开为空格并记 warning。

### P-3 [SEVERITY: L2] parser.py:336-353（无冒号行与块标量被静默丢弃）
- **问题描述**：dict 分支对不含 `:` 的行直接 `idx += 1` 跳过（351-352 行）。YAML 块标量（`key: |` / `key: >`）完全不受支持：`|` 被当标量值，后续多行内容因无冒号被逐行静默丢弃——多行描述文本整体消失且零告警。
- **触发场景**：作者用多行字符串写伏笔 desc / 锁定事实 fact。
- **建议修法**：至少识别 `|`/`>` 值形态并抛"暂不支持块标量，请改用引号单行 + \n 转义"的业务错误，杜绝静默吞数据；无冒号行记 warning。

### P-4 [SEVERITY: L2] parser.py:324、347（重复键静默后写覆盖）
- **问题描述**：`result_dict[k] = v` 直接赋值，重复键**后者静默胜出**（YAML 规范要求报错）。作者笔误写两遍 `chapter_id` / `new_entities`，前一份被无声丢弃，check 无感。
- **触发场景**：长 frontmatter 手工编辑复制粘贴出错。
- **建议修法**：同层重复键至少记 warning（或在确定性引擎语境下直接报错）。

### P-5 [SEVERITY: L3] parser.py:118-158（锚点/别名/合并键不支持且无报错）
- **问题描述**：`&anchor` / `*alias` / `<<: *base` 均按字面量落入数据结构（`key: &a` 的值成为字符串 "&a"，`<<: *base` 成为键 "<<" 值 "*base"）。从标准 YAML 复制片段会得到语义错乱的数据而非错误提示。
- **建议修法**：检测到行首/值首的 `&`/`*`/`<<` 时抛业务错误明示"本解析器不支持 YAML 锚点与别名"。

### P-6 [SEVERITY: L3] parser.py:152-157（方括号字符串被误转为列表）
- **问题描述**：值以 `[` 开头且以 `]` 结尾时先试 `json.loads`，失败后退化为逗号切分并**剥掉方括号**：字符串值 `"[主角]"` 变成列表 `["主角"]`，字段类型从 str 静默变 list，下游按字符串消费的代码得到 list。
- **触发场景**：值恰好以 `[` 开头 `]` 结尾的中文文本。
- **建议修法**：json 解析失败时保留原始字符串（不做括号剥离）。

### P-7 [SEVERITY: L3] parser.py:13-17、123-124（中文弯引号不剥离）
- **问题描述**：`_strip_quotes`/`_parse_scalar` 只认 ASCII `"` 和 `'`。从 Word/微信粘贴的 `name: “张三”` 会带着弯引号原样落账——人物名永久含引号，后续名称匹配、防撞名、死者检索全部静默失配。
- **触发场景**：作者从办公软件复制名称/对白进 frontmatter。
- **建议修法**：成对剥离 `“”‘’`（仅当成对出现时）。

### P-8 [SEVERITY: L3] parser.py:216-229（_split_key_value 行尾冒号早退）
- **问题描述**：`s.endswith(":")` 早退把整行当键（219-220 行）。标量值本身以冒号结尾时（`note: 待定:`、`title: 尾声:`）值被静默丢弃，整行沦为键名。
- **建议修法**：先按第一个未转义 `:` 拆分，仅当右侧 strip 后为空时才判为"键行（值在下一层）"。

### P-9 [SEVERITY: L3] parser.py:118-158（针对"重启解析注入"的专项核查——结论：通过）
- **问题描述**：专项核查 `issuer: "on"` / `issuer: on` 是否被 YAML 1.1 布尔化。`_parse_scalar` 的引号剥离先于布尔判断（123-124 行早退），且布尔集合仅 `true/false/null/none/~`（126-131 行）——**不含 on/off/yes/no**。结论：引号与不引号的 `on` 均得字符串 `"on"`，**不存在 PyYAML 式布尔注入面**；`TRUE/True` 归一为 True 属 YAML 1.2 合法行为，可接受。此项为核查通过记录，非缺陷。

### P-10 [SEVERITY: L3] parser.py:355-370（frontmatter 缺失/顶层非 dict 静默返回空）
- **问题描述**：`parse_mini_yaml` 根为 list 时返回 {}（355-356 行）；`parse_frontmatter` 对**首行前置空行**或缺少闭合 `---` 的文件静默返回 `({}, content)`（363-366 行）。全书扫描模式下 `check_id_integrity:812-813` 的 `if not fm: continue` 使该章校验被静默跳过—— beats 文件顶部多一个空行即可让整章 ID 校验假绿（单章模式有 check.py:539 兜底，全书模式无）。
- **触发场景**：文件头有空行/编辑器加 BOM 后未用 utf-8-sig 的调用方。
- **建议修法**：全书扫描遇到无 frontmatter 的 beats 记 warning；parse_frontmatter 增加"检测到 --- 起始但未闭合"的显式报错。

### P-11 [SEVERITY: L3] 全链路 read_text(errors="replace")（如 parser 调用方 id_tracker.py:810、ops.py:653）
- **问题描述**：非 UTF-8 字节被静默替换为 U+FFFD 后参与 ID/名称匹配——带乱码的 beats 会让 `p_00X` 引用报"未定义"（错误信息含替换符难定位），或名称带替换符后与台账永不相等，防撞名/死者检索静默失配。BOM 本身已被全链路 utf-8-sig 覆盖（已 grep 证实 49 处 read_text 全部带 utf-8-sig），非问题。
- **建议修法**：对 state 与 beats 读取改用 errors="strict"，编码错误转为 exit 1 业务提示并指明文件路径。

---

## 三、engine/schema.py

### S-1 [SEVERITY: L2] schema.py:19-204 vs engine/state.py:100-112（契约字段与 sync 透传白名单不同步）
- **问题描述**：state.py 的 `_PERSON_FM_FIELDS/_ITEM_FM_FIELDS/_PLACE_FM_FIELDS/_FACTION_FM_FIELDS` 是细纲显式声明字段的实际透传白名单，但相对 schema dataclass 仍有缺项：ItemRecord 承诺的 **durability** 不在 _ITEM_FM_FIELDS；PlaceRecord 承诺的 **danger_level / environment_rules** 不在 _PLACE_FM_FIELDS；CharacterRecord 的 **sensory_anchor / address_matrix** 无 person 侧透传；模板 README:134-136 的 **scope / golden_quote / schema_version** 全引擎零读取（README 自称"引擎忽略"，但这三个字段在 schema.py 中也无对应 dataclass 字段，声明即丢弃）。这正是 FIND-L 注释（state.py:91-99）想消灭的"细纲声明→静默丢弃"模式，白名单仍有漏网点。
- **触发场景**：作者在 new_entities 写 `durability: 80%` 或 place 写 `environment_rules: [...]`，落账后查询不到，check 不报。
- **建议修法**：以 `dataclasses.fields(record)` 为唯一事实源自动生成透传白名单，消手工枚举。[需动态验证]：上述字段是否在 state_deltas 其他分支（items 增量等）有独立落账路径。

### S-2 [SEVERITY: L3] schema.py:96（max_charges 默认值违反契约）
- **问题描述**：强类型白名单称 `max_charges >= 1`，dataclass 默认却是 `-1`（借用了 charges 的 -1 语义）；id_tracker trace 仅在 `>=0` 时展示上限（id_tracker.py:502）——新建道具永远不显示充能上限。
- **建议修法**：默认改 0 或 1，并统一"未声明上限"的判定口径（None 而非 -1）。

### S-3 [SEVERITY: L3] schema.py 全模块（零类型强制点）
- **问题描述**：dataclass 无 `__post_init__` 校验、无转换。细纲里未加引号的 `tier_rank: 三`、`charges: 若干` 会以 str 一路落账；check.py:383-432 只校验枚举类字段（type/role/status/life_status/attitude），**数值区间（tier_rank 1~12 / injury_level 0~5 / danger_tier 1~10 / scale_tier 1~10 / charges >=-1）零校验**。
- **建议修法**：__post_init__ 或 sync 落账处做 int 转换 + 区间钳制/告警。

### S-4 [SEVERITY: L3] schema.py:207-210（兼容别名层核查——被禁三别名结论：不存在）
- **问题描述**：专项核查"兼容别名映射表是否包含被禁三别名"：schema.py 的别名层只有类名别名 `CharacterState/ItemState/ForeshadowingState`（208-210 行），**没有任何字段别名映射**；全引擎 grep 证实 `current_location` / `current_owner` 零出现，`disposition` 仅出现在 templates/README:111（禁令原文）与 check.py:424-425（越界告警）——三项被禁别名均未被 schema 接受，此项通过。但反向风险：旧字段名（如 `tier`）也无迁移映射，存量书升级时旧字段被静默丢弃。
- **建议修法**：显式建立"废弃字段→新字段"迁移表，或至少在 check 中对已知废弃字段名告警。

### S-5 [SEVERITY: L3] schema.py:36 vs id_tracker.py:218、341（condition 默认值双标）+ 里程碑无 dataclass
- **问题描述**：(a) CharacterRecord.condition 默认 `"完好"`，而 id_tracker 的 trace/id_list 缺省显示 `"正常"`——同一字段两个缺省口径，大盘与台账展示不一；(b) `ms_`  milestones 是法定 ID 类目，但 schema.py 无 MilestoneRecord，milestones.json 全程裸 dict 消费，无契约保障。
- **建议修法**：统一 condition 缺省值；补 MilestoneRecord dataclass 并纳入 sync 契约。

---

## 四、engine/config.py

### C-1 [SEVERITY: L2] config.py:108-123（列表型配置项元素类型零校验）
- **问题描述**：`config set words_per_chapter abc` → json.loads 失败 → 逗号切分回落 → `["abc"]` 合法落盘。下游（probes 等按数字比较字数区间）拿 str 与 int 比较 → TypeError → 落 exit 4 大盒子——**用户输入错误被升级为系统故障**，违背退出码契约（应为 1）。
- **触发场景**：`config set words_per_chapter abc` 或 `config set dialogue_ratio 高中低`。
- **建议修法**：列表元素强制 `int()` 转换，失败抛 BusinessError（exit 1）并给正确示例。

### C-2 [SEVERITY: L2] config.py:125-126（int 转换 TypeError 逃逸出 exit 1 通道）
- **问题描述**：`value = type(default)(value)` 对整型旋钮强转；value 为 None 时 `int(None)` 抛 TypeError，而 cli.py:739 的捕获元组 `(BusinessError, ValueError, FileExistsError, FileNotFoundError, KeyError)` **不含 TypeError** → 落 cli.py:793 通用 Exception → exit 4。用户少传值/编程调用传 None 的错误呈现为"未预期异常"。
- **触发场景**：`config set token_cap` 缺值（取决于 argparse 是否 nargs="?"）或以 None 调用 API。**[需动态验证]** CLI argparse 对该参数的缺省形态。
- **建议修法**：转换包 try/except (TypeError, ValueError) → BusinessError；或在 cli 捕获元组补 TypeError。

### C-3 [SEVERITY: L2] config.py:83-88（load_config 不校验 engine 段现值类型）
- **问题描述**：`cfg[k] = v` 原样透传 project.json.engine 的值，**读路径无类型对齐**（写路径 set_config_value 做了）。手工编辑 project.json 写入 `"token_cap": "15000"` 后，pack 的预算比较（cli.py:491-493）str vs int → TypeError → exit 4。读写两侧类型策略不对称。
- **触发场景**：手工编辑 project.json（Stage 0A 或人类作者）。
- **建议修法**：load_config 按 DEFAULT_CONFIG 的类型做一次 coercion，非法值抛 BusinessError 并指引 `config set` 修复。

### C-4 [SEVERITY: L3] config.py:74-81（scope.words_per_chapter 解析失败静默回落）
- **问题描述**：scope 段 len!=2 或元素不可 int 化时 `except: pass` 静默回落默认 [1500,2600]——作者的商业体量设定没生效却无任何提示，与 engine 段"损坏即硬失败"（_read_project）的策略不对称。
- **建议修法**：记 warning 或抛 BusinessError 指明 project.json.scope.words_per_chapter 形态。

### C-5 [SEVERITY: L3] config.py:101-140（无取值范围校验）
- **问题描述**：`token_cap: 0` / 负数、`cruise_max_chapters: 0`、`cruise_wait_timeout: 0` 均被接受。token_cap=0 会让每章装配包恒报超预算；cruise_max_chapters=0 可能使巡航空转。
- **建议修法**：正整数旋钮加 >0（或 >=1）下限校验，越界拒绝或 warning。

### C-6 [SEVERITY: L3 信息项] config.py:103-107、91-98、71-88（核查通过项）
- **核查结论**：`config set` 未知键**正确拒绝**（BusinessError→exit 1，103-107 行）；`config get` 未知键同样拒绝（95-98 行）；优先级 `engine > scope > DEFAULT` 实现正确（71-88 行）；`cruise_human_gate: 0` 关闭语义符合 CONFIG_GUIDE 描述。此项记录备查，非缺陷。

---

## 五、engine/errors.py

### E-1 [SEVERITY: L3] errors.py:18-23（__str__ 静默丢弃 solution 的分支）
- **问题描述**：消息内已含 "💡" 时 `__str__` 直接返回 message，**构造时传入的 solution 参数被静默丢弃**（20-21 行）。调用方读 `e.solution` 属性无恙，但依赖 `str(e)` 的展示路径（如审计日志、二次包装）会丢失修复建议，且 message 与 solution 内容可能实际不同（不等同去重）。
- **建议修法**：始终附 solution（message 已含 💡 时跳过重复段落，而非整体丢弃）。

### E-2 [SEVERITY: L3] errors.py:10-27 + cli.py:739-803（裸 Exception 逃逸路径清点）
- **问题描述**：错误类族仅 BusinessError/GuardError 两类，其余全靠 cli 兜底。静态清点出的逃逸路径（全部以 exit 4"未预期异常"呈现，缺人话指引）：① config int(None)→TypeError（C-2）；② 列表元素类型错误下游 TypeError（C-1）；③ trace id==name 无限递归 RecursionError（ID-6a）；④ id_tracker.py:844 `_db[_nid].get("name")` 在 persons 条目为非 dict（如被写成字符串）时 AttributeError——_load_json 只校验顶层类型（state.py:403-414），不校验每条目形态。
- **建议修法**：cli 捕获段补 TypeError/AttributeError/RecursionError 细分映射（数据形态类给 exit 1 + "台账条目形态非法"指引）；或 _load_json 增加条目级形态抽检。

### E-3 [SEVERITY: L3 信息项] errors.py + cli.py + studio.py（退出码契约核查——总体闭合）
- **核查结论**：0/1/2/3/4 五通道均有落点：BusinessError 族→1（cli.py:739-779）；RuntimeError（坏表/不可读）→4（781-791）；未预期→4（793-803）；argparse 语法→SystemExit(2)（cli.py:68）；Python 版本环境→ENV_EXIT_CODE 3（studio.py:39-53）；GuardError 标题正确优先于 BusinessError（740-743 行）。契约总体闭合，缝隙仅 E-2 所列细分缺失。

---

## 六、engine/ledger.py

### L-1 [SEVERITY: L3] ledger.py:1-12（模块身份判定：既非死代码，亦非资金池入口）
- **问题描述**：10+2 行的实际内容是——从 `engine.state` 再导出 `StateManager/_ensure_dir/_load_json/_save_json`，并起别名 `StateLedger = StateManager`。结论：
  1. **与资金池 ledger 表无直接关系**。资金池真入口是 `state.py` 的 `ledger_file`（state/ledger.json）与 `schema.LedgerRecord`（pools/transactions），消费方全部以 `StateLedger(workspace)` 当 StateManager 使用（ops.py:22、230、303、1196、1276、1337、1360、1390、1481、1554、1697、1759；cruise.py:299-301）。
  2. **不是死代码**——ops/cruise 的导入依赖此路径存在。
  3. 它是"统一别名/导入转发层"。风险在于双导入路径（engine.state 与 engine.ledger 导出同名符号）造成认知分歧——文件名 ledger.py 极易被误读为"资金账本入口"（本次审计任务本身的疑问即源于此）；且该转发层无任何测试锚定 state.StateManager 的签名演进。
- **建议修法**：docstring 补一句明示"本模块为 StateManager 统一别名转发层，资金池台账见 state/ledger.json 与 schema.LedgerRecord"；或将 ops/cruise 的 `from engine.ledger import ...` 统一收敛到单一导入源，减少路径分叉。

---

## 附：缺陷计数与优先级建议

| 严重度 | 计数 | 编号 |
|---|---|---|
| L1 | 2 | ID-1（发号无预留+打捞循环撞号静默丢实体）、ID-4（DEBT-AUTO 种子碰撞静默抹恩怨） |
| L2 | 11 | ID-2、ID-3、ID-5、P-1、P-2、P-3、P-4、S-1、C-1、C-2、C-3 |
| L3 | 20 | ID-6~ID-10、P-5~P-11、S-2~S-5、C-4~C-6、E-1~E-3、L-1 |
| **合计** | **33** | |

修复优先级建议：ID-1 ≈ ID-4 > P-1/P-2/P-3（解析器静默吞数据三兄弟）> C-1/C-2/C-3（退出码契约）> ID-3 > S-1 > 其余 L3。

核查通过记录（非缺陷，备查）：P-9（无 YAML 布尔注入）、S-4（三大被禁别名不存在）、C-6（config 未知键拒绝+优先级）、E-3（退出码五通道闭合）、BOM/CRLF/空文档/超长行处理（全链路 utf-8-sig + splitlines，无缺陷）。
