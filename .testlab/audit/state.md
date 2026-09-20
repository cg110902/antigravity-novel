# 静态审计报告 · engine/state.py（Novel Studio v4.4.0 八表持久化与细纲增量合账核心）

- **审计对象**：`engine/state.py`
- **实际规模**：1623 行（任务描述称 1491 行，**以文件实际行号为准**，报告中所有行号基于 1623 行版本）
- **审计方式**：全文件逐行静态阅读 + 交叉核对 `engine/ops.py`（sync_chapter 编排）、`engine/cli.py`（退出码映射）、`engine/check.py`（巡检消费方）、`engine/schema.py`（类型契约）。**未修改任何代码。**
- **审计依据偏差（重要）**：任务契据中的 `apply_state_deltas` 与 `state/sync_log.json` 指纹判定**均不在 state.py 内**。state.py 的真实入口是 `apply_fine_outline_delta`（第 561 行，兼容别名 `apply_chapter_delta` 第 1620 行）；`sync_log.json` 指纹门禁在 `engine/ops.py:1179-1249`，位于 apply **之前**，是外层短路而非本章幂等机制。README（engine/README.md:14,33）沿用的旧函数名 `apply_state_deltas` 属文档漂移，见 D-A。

---

## 一、契约符合性总表

| 契约项 | 结论 | 说明 |
|---|---|---|
| 事务预检先于任何写盘 | ⚠️ 部分成立 | 死者/充能两项预检确在写盘前（881 行 raise），但**预检视线不含同章 new_entities 新道具、且道具预检不解析别名/名称 ID**，见 D1/D2 |
| 按章幂等增量（重放安全） | ✅ 基本成立 | 全部索引表均有按章去重，无漏表；但**去重键为精确字符串**，章号格式变体会翻倍，见 D4 |
| 原子写盘（单表） | ✅ 成立 | tempfile 同目录 + fsync + os.replace，异常路径 unlink tmp 且原文件不动 |
| 多表事务 | ❌ 不成立 | 14+ 次顺序单表写，无回滚；仅靠 ops 哨兵"检测"而非"修复"，见 D6 |
| 损坏硬失败（隔离 + exit 4） | ⚠️ 部分成立 | JSONDecodeError 正确；**非 UTF-8 字节走 UnicodeDecodeError → exit 1 且不隔离**，见 D3 |
| sync 幂等（四张索引表） | ✅ 结构成立 | co_occurrence/entity_timeline/arc_history/relations.history 均按 chapter 去重 |
| 六类硬阻断 | ⚠️ | 本文件仅实现 3.5 类（JSON 损坏 / 死亡登场 / 充能透支〔有盲区〕）；空正文封存、SSOT 覆盖、init 覆盖均在 ops.py，不在本文件 |
| charges 合法范围 >= -1 | ⚠️ | -1 短路与 =0 放行逻辑正确；但**范围/类型无守卫**，见 D7 |
| --force / --refresh | ✅ | 见 ops.py 1185-1249，`--refresh` 只碰指纹与字数（小瑕见下） |

---

## 二、缺陷候选清单

### [SEVERITY: L3 · 系统级]

#### D1. 充能透支预检盲区：同章 new_entities 新道具 + state_deltas.items 扣减 → 硬阻断被绕过且静默吞账
- **行号**：850-878（预检）vs 736-741 / 884-885（实体推迟落盘）vs 1016（items 重新读盘）vs 1075-1078（应用侧）
- **问题**：预检第 851 行 `_items_pre = self.get_items()` 从**磁盘**读取道具表，而本章 `new_entities` 新建档的道具此时只在内存（`items_db`），要到第 884-885 行才落盘。因此对"本章新获得并使用"的道具，预检读到空记录：`_rec.get("charges", -1)` 取默认 -1，`-1 >= 0` 为 False，透支检查整段跳过。预检通过后进入应用侧：1075 行同为 `>= 0` 门（此时 charges=2 真实存在），`new_charges = 2 + (-3) = -1 < 0` → **扣减被静默丢弃，不报错、不入 _fatal**；但 1091-1097 行的 transfer_history 照原样记录 `charges_delta: -3` 与旧 `remaining_charges`。最终 sync **exit 0**，台账内部自相矛盾（充能显示 2，流水显示已扣 3），且该矛盾会被后续所有检查继承。
- **触发路径**：`python studio.py sync ch_007`，细纲 frontmatter 同时写 `new_entities: [{id: it_009, type: item, name: 新手电, charges: 2}]` 与 `state_deltas.items: [{id: it_009, charges_delta: -3}]`。"本章获得并一次性耗尽"是高频作者模式，非边角。
- **建议修法**：预检前先把 `new_entities` 投影合并进预检视图（预检函数改吃内存 `items_db` 而非重读磁盘），或把 884-885 行的落盘提前至预检之前并保留"预检失败即回滚新实体"语义；更稳妥的做法是把两项预检（死者/充能）合并为单一 `_precheck(persons_db, items_db)` 纯函数，输入全部为内存态。

### [SEVERITY: L2 · 深层]

#### D2. 道具预检用裸 id 查盘、应用侧用 `_resolve_item_id` 解析 → 名称/别名引用道具的透支同样被漏检
- **行号**：855-858（`_iid = str(it.get("id","")).strip()`，无解析）vs 1023（`_resolve_item_id(raw_id or iname, items_db)`）
- **问题**：与 D1 同根不同径。作者在 `state_deltas.items` 用道具**名称**而非 ID 书写（模板未强制 ID）时，预检按裸 id 查不到记录 → 视为新道具（charges 默认 -1）→ 跳过透支校验；应用侧却能解析到真实道具并走到 1075 行 → 同样静默吞扣减 + transfer_history 记假账。exit 0。
- **触发路径**：`sync ch_012`，`state_deltas.items: [{name: 旧手表, charges_delta: -9}]`（该道具 charges 剩 3）。
- **建议修法**：预检侧第 855 行起与 1023 行使用同一 ID 解析函数，保证"预检口径 == 应用口径"（代码注释 863-865 行自称口径一致，实际只覆盖了重放冲销、没覆盖 ID 解析）。

#### D3. 非 UTF-8 编码的状态表 → UnicodeDecodeError（ValueError 子类）→ 被 CLI 判为 exit 1 业务阻断，不隔离、不 RuntimeError
- **行号**：382-398（`_load_json` 只捕 `json.JSONDecodeError` 与 `OSError`）；`engine/cli.py:739`（第一层 except 把 ValueError 归为"参数/格式校验阻断"，return **1**）vs `engine/cli.py:781`（RuntimeError → return **4**）
- **问题**：`open(p, encoding="utf-8-sig")` 后 `json.load` 遇到 GBK/ANSI 字节或多字节字符截断时抛 `UnicodeDecodeError`——它是 `ValueError` 子类，既非 `JSONDecodeError` 也非 `OSError`，**直接穿透 state.py 的两层 except**。CLI 第一层捕获后打"参数/格式校验阻断"并 **exit 1**（而非契约规定的系统级 exit 4），且**不发生 *.corrupt-* 隔离**。作者/Agent 会按"业务参数写错"去排查，而实际是状态表编码损坏；按 AGENTS.md 退出码铁律，exit 1 会被当作"对照输出排错修复"而非"停机请示人类"。
- **触发路径**：用 Windows 记事本（ANSI/GBK）保存 `state/persons.json`（含中文未转义时必然 GBK 字节）后运行任意读表命令（`sync`/`check`/`trace`）。
- **建议修法**：`except (json.JSONDecodeError, UnicodeDecodeError, ValueError)` 合并复用同一隔离 + RuntimeError 逻辑；或先读 bytes 再 `json.loads(raw.decode("utf-8-sig"))`。

#### D4. 按章去重键是精确字符串相等 → 章号格式变体（ch_001 / ch_1 / CH_001）导致重复计数
- **行号**：co_occurrence 1502-1505（`ch_id in co_item["chapters"]`）、entity_timeline 1534、arc_history 945、relations.history 1373、transfer_history 1087-1090、timeline 1439、ledger 1235-1238（还叠加 pool 维度）、places.visited_chapters 1120、lines.revealed_chs 1187、synopsis 1423（dict 键）
- **问题**：全部幂等判定均为 `== ch_id` 字符串比较。同一逻辑章以两种书写重放（作者改章节号风格后 `--force`、或多书/多卷命名不一致）时，每张表都会为"另一章"新建条目：`co_occurrence.total_co_occurrences` 虚增、entity_timeline 双 events、arc_history 双记录、synopsis 双键（旧键成永死孤儿）。`ops.py:1136-1141` 只保证"frontmatter chapter_id == CLI 参数"，不保证跨次运行的命名一致，暴露面收窄但未闭合。
- **触发路径**：细纲从 `ch_007.md` 改名为 `ch_7.md` 后 `sync ch_7`（或 `--force` 重放改名后的同章）。
- **建议修法**：引入 `_chapter_key(cid)` 归一化（提取 `(\d+)` 数字、统一零填充）作为全部表内 chapter 键与比对基准；ledger 流水去重键还应去除 pool 维度或改为 `(chapter)` 单键（现按 `(chapter, pool)` 去重，同章换池名会双记流水，使 `pools` 余额按 `sum(transactions)` 重算时虚增，见 1244-1246 行重算式）。

#### D5. `_chapter_num` 对无尾数字章号返回 0 → 章序比较全线退化，死者登场预检可被绕过
- **行号**：268-271（`re.search(r"(\d+)$", ...)` 无匹配 → 0）；死者预检 825、834 (`_chapter_num(ch_id) > _chapter_num(_d_ch)`)；连带 `_entity_update_guard` 142、`last_seen_ch` 936/1082、co_occurrence `last_seen_ch` 1499
- **问题**：章 id 形如"序章/尾声/卷末/番外·雪夜"（尾部非数字）时 `_chapter_num` 恒为 0。死者预检 `0 > _chapter_num("ch_004")` = `0 > 4` = False → **不阻断**：已阵亡角色可在无编号章合法"登场"。同时 `_entity_update_guard` 退化为恒真（旧章重放可回退字段）、各处 last_seen_ch 单调守卫失效（每次重写）。
- **触发路径**：`sync 尾声`，细纲 `present_characters` 含已于 ch_004 阵亡的角色 → exit 0 放行，随后 check 可能才在别处报矛盾（若 check 用别的章序解析则表现为难回溯的拉扯）。
- **建议修法**：`_chapter_num` 无法解析时返回一个显式哨兵（如 `None`/`-inf`）并在调用方分级处理：死者预检在章号不可解析时降级为"同名即阻断"或要求人类确认；`_entity_update_guard` 与 last_seen_ch 守卫在不可解析时跳过而非放行。

#### D6. 多表顺序写盘无回滚：预检通过后任一写盘失败 = 半写状态
- **行号**：884-1604（persons→items→places→lines→ledger→debts→relations→locked→synopsis→timeline→current→co_occurrence→entity_timeline→history 快照，共 14+ 次 `_save_json`）
- **问题**：单表原子 ≠ 多表事务。`os.replace` 成功到一半时进程被杀 / 磁盘满 / 权限变化（如只读目录中 places.json 可写而 indices/ 不可写），台账停在跨表不一致中间态。现有缓解在 state.py **之外**：`ops.py:1282-1297` 的哨兵 + `_save_count()` 区分"零写盘清哨兵/有写盘保留"，`check.py:248-259` 识别残留哨兵并指引 `sync --force` 恢复。即：**检测与恢复都存在，但 state.py 自身零回滚能力，且该安全性完全依赖"调用方恰好包了哨兵"这一外部契约**——已确认当前唯一调用方 `ops.py:1289` 已包裹，但 `apply_chapter_delta` 作为公开兼容别名（1620 行）对任何未来调用方都是无哨兵裸奔。
- **触发路径**：`sync ch_020` 执行中 Ctrl-C（落在第 7 张表之后）；或 `state/indices/` 权限被安全软件锁定导致 co_occurrence 写失败（此前 13 张表已改）。
- **建议修法**：短期把哨兵立/清移入 `apply_fine_outline_delta` 自身（函数入口立、出口清），使契约与实现同文件；中期提供卷级 journal（写前 diff 快照）实现真回滚；至少在 docstring 与 README 标注"仅允许在哨兵窗口内调用"。

#### D7. charges 类型/范围守卫缺失：str 引发 TypeError（exit 4 裸异常）、float/布尔静默破坏 int 契约
- **行号**：873 与 1075（`>= 0` 与 str/int 混比）、1076-1078（str + int）、1060 与 860（`int(c_delta)` 截断）、1031 行 new_entities 侧 `ne.get("charges", -1)` 无范围校验
- **问题**：① 手工编辑使 `charges` 为字符串（`"3"`）→ 873/1075 行 `str >= int` 抛 TypeError → 穿透至 `cli.py:793` 通用 except → **exit 4「未预期异常」+ 一条 `TypeError: '>=' not supported...` 原文**，无结构化修复指引（注意：若崩在 1075 行则前 13 张表已写盘，退化为 D6 半写态）；② float（`3.5`）顺利通过并参与运算，`charges` 契约（schema.py:95 `int`）被静默改写，浮点随每次扣减漂移；③ `charges_delta: 2.7` → `int()` 截断为 2、`charges_delta: -0.5` → 0，静默改变剧情语义；④ `charges_delta: "abc"` 在预检侧 `continue` 跳过检查、应用侧置 0，且 transfer_history 仍按原语义记档 → 假账；⑤ `charges: -5`（契约要求 >= -1）被 new_entities 原样接收且此后被当作"非计数型"冻结，不告警。
- **触发路径**：用编辑器把 `state/items.json` 某道具 charges 改成 `"3"` 后 `sync` 下一章；或细纲写 `charges_delta: 1.5`。
- **建议修法**：新增 `_norm_charges()`：读表时对非 int（bool 除外）抛结构化 RuntimeError（复用 exit 4 通道）并指引修复；写侧对 `charges_delta` 非整字面量 warning 而非静默 0；new_entities 落账时 clamp/校验 `charges >= -1`，非法值告警。

#### D8. debts `settle` 按 target_char 命中即结清，忽略 source/type → 误结清他人恩怨
- **行号**：1290-1294
- **问题**：`action: settle` 时循环条件是 `(d_item.get("target_char") == d_target or d_item.get("id") == d_id) and status == "unpaid"`。派生 id（1265-1268）种子含 `ch_id`，对往章创建的恩怨永远匹配不上，**实际匹配全靠 target_char 单字段**：同一目标的多条未了恩怨（不同 source、不同 type）被一次性全部 settled。与 `record` 分支的稳定四元组键（chapter|source|target|type）口径不一致。
- **触发路径**：`state_deltas.debts: [{action: settle, target: p_001, source: p_002}]`，而 p_003 对 p_001 也有一笔未了恩怨 → p_003 的恩怨被误判已清。
- **建议修法**：settle 匹配改为 `(source, target, type)` 全等或强制要求显式 `id`；无 id 时按与 record 相同种子派生并提示。

#### D9. present_characters 仅 name 无 id 的 dict 条目被静默丢弃；同名字符串条目却被当 ID 建档 —— 同一输入两种结局
- **行号**：758-775（`_resolve_person_ref`：`probe = rid or rname`，id 优先，查不到返回 `("", rname)`）、793-801（`_pc_dedup` 以空 id `continue` 丢弃）、887-895（persons 循环同样 `if not cid: continue`）
- **问题**：dict 形态 `- name: 周楚`（未建档）→ id 解析为 "" → 被去重循环丢弃 → 该角色**本章全部状态静默丢失**（无弧光、无共现、无 entity_timeline、不进 char_names_present）。而字符串形态 `- 周楚` → 原值成为 id → 建出一条 `id="周楚", name=""` 的幽灵记录（与"周楚"真身并存双轨）。第 755-757 行注释明确宣称"查不到才按原值走自注册"，dict 路径的实现与注释直接矛盾。混合书写时还会造成同一人物两条档案，后续死亡判定/关系键分裂。
- **触发路径**：细纲 `present_characters:` 列表写 `- name: 新配角` 或 YAML mapping 形态（见 D16），且该配角此前未建档 → 该章合账对此人完全静默。
- **建议修法**：`_resolve_person_ref` 在 rid 未命中时回退用 rname 反查；仍未命中则统一以 name 生成稳定 id（如 `p_auto_<slug>`）并补 warning；`_pc_dedup` 不得丢弃空 id 条目（改为先建档再入列）。

### [SEVERITY: L1 · 轻瑕]

#### D10. 非法 life_status 值在 new_entities / present_characters 通道静默落账，与 character_status 通道的告警不一致
- **行号**：629、645、931（`_LIFE_STATUS_NORM.get(v, v)` 原值透传）vs 981-991（FIND-L3 告警）
- **问题**：写 `life_status: 诈尸` 之类的非枚举值 → 原样入库 → `is_deceased` 判 None → 永久"非 deceased"，零告警；而 character_status 通道对同类拼写错误有明确 warning。三入口三待遇。含中文"死亡/阵亡"等是合法映射（151-166 行），仅**表外拼写**漏管。
- **建议修法**：抽 `_norm_life_status(v, ctx)`：命中枚举表归一，未命中则 warning + 保持原值，三通道共用。

#### D11. `os.replace` 后未 fsync 父目录
- **行号**：423-427
- **问题**：file fsync 保证内容、不保证目录项。断电/掉电场景 rename 可能丢失（文件回退到旧 inode 或消失）。Windows/NTFS 上概率低但非零。`[需动态验证]`
- **建议修法**： replace 后对 `p.parent` 打开目录 fd 做一次 `os.fsync`（ wrapped in try/except OSError 兼容平台）。

#### D12. 进程被 SIGKILL 于 json.dump 中途 → state/ 遗留孤儿 `.tmp`，无清理机制
- **行号**：421（`tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", ...)`）、434-438（仅已捕获异常才 unlink）
- **问题**：SIGKILL/断电时 except 不执行，`.persons.json.abc123.tmp` 永久残留。check 巡检只扫 `*.corrupt-*`（check.py:284），不含 `.tmp`；虽不会被任何读取命中（惰性无害），但会进 snapshot 打包（ops.py:1993 `rglob("*")`）并误导人工排查。
- **建议修法**：命令启动时清理超过一定年龄的 `.tmp`；或 snapshot 排除。

#### D13. co_occurrence 既有条目的 names 不随改名刷新；history 条目 payload 不随 --force 更新
- **行号**：1489-1497（`co_db.get(co_key, {...})` 仅新建时写 names）、1515-1520（`already_synced` 为 True 时不追加 history，而 `last_interaction_summary` 1507-1514 无条件更新）
- **问题**：角色改名后，旧 pair 条目的 `names` 恒为旧名；`--force` 重放修订版细纲时 `last_interaction_summary` 刷新但 `history` 保留首版 dynamic/subtext → 同一文件两种时效的数据。
- **建议修法**：命中既有条目时同步刷新 names；history 改为"按 chapter 替换"（与 relations.history 1373-1381 同构）而非"仅追加"。

#### D14. relations pair 方向敏感：`p_001->p_002` 与 `p_002->p_001` 双轨存储，重放不去重
- **行号**：1308-1318、1373（history 按 pair_key 去重）
- **问题**：pair_key 保留书写方向。作者时而写 `A->B` 时而 `B->A` 即产生两条独立关系记录（affinity/trust/tension/history 各一套），`co_occurrence` 查询侧虽做了双向兼容（1507），relations 自身不归一 → 关系图谱实际分裂。
- **建议修法**：pair_key 统一按 id 排序生成（与 co_occurrence 1487 同口径），保留原始书写于 history 便于溯源。

#### D15. 字符串顶层 `relation_deltas` 被丢弃，对应解析分支是死代码
- **行号**：1298-1303（`[raw_rels] if isinstance(raw_rels, dict) else (...)`，随后 `isinstance(rd, dict)` 门把字符串条目 continue 掉）vs 1314-1318（`isinstance(pair_val, str)` 分支）
- **问题**：`relation_deltas: "p_001 -> p_002"` 会被包成 `["p_001 -> p_002"]` 然后在循环首行被丢；1314-1318 行处理的字符串 pair 只可能来自 dict 内部的 `pair:` 字段，顶层字符串形态永不可达。契约暗示支持、实现静默丢弃且无 warning。
- **建议修法**：删除死分支，或在归一化处把顶层字符串转成 `{"pair": "..."}` 并登记 warning。

#### D16. `present_characters` YAML mapping 形态（`周楚: {...}`）静默丢空
- **行号**：748-749（顶层 dict 被包成单元素 list）、784-790（`.get("id")`/`.get("name")` 取不到键 → 空 id）→ 落入 D9 丢弃路径
- **问题**：mapping 写法在该表中无任何提示地被完全忽略（与字符串/dict-list 形态行为不一致）。
- **建议修法**：mapping 形态显式阻断并给出正确写法示例（GuardError），比静默丢弃更符合"零噪音但不错账"原则。

#### D17. `chapter_id: null`（键存在、值为空）→ 以 None 入账，synopsis/timeline 键失配并累积
- **行号**：567（`frontmatter.get("chapter_id", "ch_001")` 对显式 null 返回 None）、1423（`synopsis_db[None]`，json.dump 序列化为字符串键 `"null"`）、470-486（`get_synopsis().get(chapter_id)` 取不回）、1439（timeline 过滤 `!= None` 清不掉 None 条目）
- **问题**：ops.py:1136-1141 的一致性守卫只挡"非空且不一致"，null 穿透。结果是本章 synopsis 永远读不回来、快照切片丢剧梗、timeline 中 None 条目逐次累积。
- **建议修法**：567 行改为 `str(frontmatter.get("chapter_id") or "ch_001").strip()` 并对空值显式阻断。

#### D18. `line_summary` planted/revealed/resolved 对同 fid 重复追加 → 报告层计数虚增
- **行号**：1183、1189、1193
- **问题**：台账幂等（lines_db 按 fid 覆盖）但返回给 CLI 的汇总列表按条目追加，同一章重复声明同一条伏笔时数字虚高，用户可见误导。
- **建议修法**：append 前 `if fid not in line_summary[...]` 或统计时按 set 去重。

#### D19. ledger 重算式对手工编辑的字符串 delta 抛 TypeError；"1e3"/"1.5"类增量被静默忽略
- **行号**：1245-1246（`sum(t.get("delta", 0) ...)`）、1219-1226
- **问题**：transactions 中 delta 为字符串时 1246 行 TypeError → exit 4 裸异常（同 D7 家族）；`delta: "1.5"` → `int()` ValueError → 忽略 + warning（已有），但 `delta: "1e3"`/`" 100 "` 等形态无统一口径说明。
- **建议修法**：ledger 数值统一走 `_to_int()` 归一，失败走结构化告警而非裸崩。

#### D20. 无长度/规模上限：任意超长字符串与超大列表直接持久化
- **行号**：全函数（如 1202 evidence、619/1035 summary/condition、1144 places）
- **问题**：作者把整段原文粘进 `evidence` 或 `condition` 时无截断/无警告，state JSON 线性膨胀，拉低所有读表命令性能；单表内存峰值无保护。
- **建议修法**：对自由文本字段设软上限（如 2000 字）超长 warning 并截断；对 new_entities/present_characters 列表长度设上限告警。

---

## 三、已检查无明显问题项

1. **预检先于写盘的结构正确性（限定范围内）**：881 行 `raise GuardError` 之前无任何 `_save_json`；new_entities 推迟落盘（736-741 → 884-885）落实了"阻断章零污染"（v4.3.2 缺陷#18 修复有效）。
2. **单表原子写**：`_save_json`（418-439）mkstemp 同目录 + `f.flush` + `os.fsync` + `os.replace`，dump/replace 失败均 unlink tmp 且原文件保持不动。
3. **JSONDecodeError 损坏路径**：隔离为 `*.corrupt-<ts>` + RuntimeError（exit 4，cli.py:781-791 映射正确）。
4. **隔离残骸 + 正主缺席 → 持续硬失败**（367-379）：不发空表、不让发号器重发已占 ID。
5. **顶层结构类型契约校验**（403-414）：dict/list 误写即时 RuntimeError 并给修复指引，不静默隔离。
6. **四张索引表的按章去重无漏表**：co_occurrence.chapters（1502）、entity_timeline.events（1534/1553，chapter+event 双键）、arc_history（945）、relations.history（1373）；另有 transfer_history（1087）、timeline（1439）、synopsis 键、locked id、debts 稳定派生 id（1265-1268，sha1 四元组）、lines.revealed_chs（1187）、places.visited_chapters（1120）。**仅去重键格式一致性有瑕（D4）。**
7. **charges 语义核心**：-1 短路正确（873/1075 的 `>= 0` 门）；`charges == 0` + 负 delta → 预检硬阻断（正确放行边界）；同章 `--force` 重放冲销 `_prev_d`（866-872 / 1067-1074）实现正确，不会连扣。
8. **死亡登场检测的双通道**：ID 直查（822-827）+ 全库 name/aliases/括号基准名反查（829-842），别名路径已覆盖；present_chars 归一化层 `_resolve_person_ref` 亦含别名解析。
9. **显式生死契约优先**：life_status/status 命中枚举表时绝不让 condition 文本翻案（225-226）；`_infer_life_status` 反事实守卫（249-265）防"几乎死了"误判。
10. **last_seen_ch 单调不倒退**（936-937、1082-1083、1499-1500）。
11. **`--refresh` 只碰字数**（ops.py:1185-1228）：仅更新 sync_log 指纹 + timeline/synopsis 的 word_count + project 累计字数，不触发 apply；`refresh` 无指纹时 GuardError 阻断（1229-1235）。小瑕：timeline/synopsis 条目缺失时静默跳过（`_tl_hit`/`in` 守卫），属 D4 键失配的下游表现。
12. **哨兵语义**（ops.py:1282-1327 + check.py:248-259）：零写盘业务阻断清哨兵、写盘中途中断保留哨兵并由 check 报 error 指引 `--force` 幂等复原；`_save_count` 正确排除哨兵自身写（432 行）。
13. **边界归一化**：items / relation_deltas / locked_facts / foreshadowing_deltas / present_characters / new_entities 的 null、单 dict、字符串、非列表形态均有 isinstance 归一化，不崩不抛（但部分静默丢弃，见 D9/D15/D16）。
14. **`_entity_update_guard` 旧章重放不回退**（132-142）：`--force` 重放旧章不会把后续章的字段演化覆盖回退。
15. **ledger pools_baseline 首触固化**（1227-1234）：初始手工池余额不因重放蒸发（v4.3 缺陷#A3 修复有效）。

---

## 四、[需动态验证] 清单（静态证据不足，以下结论未经运行时确认）

1. D1/D2：以 mock 工作区实跑 `sync`（new_entities 新道具 + 超额 charges_delta），确认 exit 0 且 charges 不变、transfer_history 记假账；并确认 `check` 是否有旁路发现该矛盾（check.py 全量未审）。
2. D3：构造 GBK 编码坏表，实测退出码（预期 1，契约要求 4）与无隔离行为。
3. D5：以"尾声"类章号实跑死者登场预检，确认放行。
4. D6：长事务中段中断（模拟 OSError）后哨兵保留行为与 `--force` 复原的完整性（依赖真机中断或注入故障）。
5. D11：目录 fsync 缺失在目标文件系统上的实际风险（Windows/NTFS 下大概率可忽略）。
6. D12：孤儿 `.tmp` 是否影响 `snapshot create/rollback` 与 `rollup` 的计数（ops.py:1993 rglob 归档路径疑似包含）。
7. D4：章号格式变体在 `sync_log`/`synopsis`/`co_occurrence` 三处的键归一化差异，是否被 ops 层守卫完全阻断。

---

## 五、附：审计判据与实现的命名偏差

- 契约中的 **`apply_state_deltas` 在本文件不存在**；真实函数为 `apply_fine_outline_delta`（561 行）/ `apply_chapter_delta`（1620 行）。engine/README.md:14、33 仍引用旧名，属文档漂移，建议同步。
- 契约中的 **`state/sync_log.json` 指纹判定不在本文件**；本文件的幂等是"按章结构性去重"，指纹门禁（同稿跳过 / 异稿 GuardError）在 ops.py:1179-1249，是 apply 的外层前置条件。二者叠加才构成完整幂等链，审计时不应把 ops 层的短路算作 state.py 的去重能力。

---

*报告完。未改动 engine/ 下任何代码。*
