# engine/ops.py 静态审计缺陷候选报告（Novel Studio v4.4.0）

- **审计对象**：`engine/ops.py`（实际 **2191 行**；任务描述称 1939 行，本报告行号以实际文件为准，末行 `from engine.id_tracker import id_list, id_next, trace_id` 位于 L2191）
- **审计方式**：全文通读 + 关联层核对（`engine/cli.py` 退出码/参数校验/错误渲染、`engine/check.py` 体检覆盖、`engine/parser.py` frontmatter 序列化保真度、`engine/errors.py` 错误契约、`engine/state.py` 接口层）。**未修改任何代码。**
- **严重级定义**：
  - **L1** = 可致不可逆数据丢失 / 安全边界突破 / 核心契约失效，且引擎侧无任何内置缓解；
  - **L2** = 明确功能缺陷或假阴性/假阳性误判（有条件触发，或存在部分缓解）；
  - **L3** = 边缘健壮性、一致性、语义体验问题（不影响主链路正确性）。

---

## 一、缺陷候选清单

### 🔴 L1（2 项）

#### [SEVERITY: L1] D-01 位置参数章号/卷名零校验，全命令面路径穿越
- **行号**：ops.py L550, L628–632, L648, L660, L750–752, L768–771, L796, L841, L861–863, L875, L1087, L1107–1109, L1143, L1465–1468, L1500–1502, L1674, L1737；cli.py L189/198/203/209/216/223/230/292/300/307
- **问题描述**：`chapter_id` / `volume_id` 未经任何格式或路径净化，直接参与 `workspace / "outlines" / vol_id / "beats" / f"{chapter_id}.md"` 一类拼接。`pathlib` 语义下，**绝对路径参数会整体覆盖前缀**（`ws / "a" / "/etc/x.md"` → `/etc/x.md`），`../` 序列可逐级逃逸。受影响写入面：`beats new --write`（L550）、`audit --write`（L660）、`finalize`（L841）、`proposal auto`（L1087）、`sync`（L1107–1143）、`evidence`（L1465–1502）、`reconcile --write` 报告名 `reconcile_{volume_id}.md`（L1674）、`state rollup` 产物名 `rollup_{volume_id}.json`（L1737）。CLI 仅对 `--target-ch` 挂了 `_chapter_num_arg` 类型钩子（cli.py L147–154, L269），**全部章节位置参数是裸字符串，无第二道防线**。
- **触发路径**：`python studio.py finalize /abs/target -w <ws>`（任意路径写正文）；`python studio.py beats new "../../evil" --write`（越出工作区写脚手架）；`python studio.py reconcile "../../x" --write`（报告文件越界）；LLM 幻觉章号（`ch_1`/`ch_001_extra`）落入字面路径。**附带放大效应**：Windows 大小写不敏感文件系统下 `CH_001` 能命中真实 `ch_001.md`，audit/proposal/evidence 会按 `log/audit/CH_001.md` 等错位文件名落盘，与 finalize/sync 期望的 `log/audit/ch_001.md` 脱节——配方静默丢失。
- **建议修法**：ops.py 公共入口加 `_validate_chapter_id()`（如 `^ch_\d{3,}$`，或复用 cli 的 `(?:ch[_-]?)?0*\d+` 全匹配），`_validate_volume_id()`（`^vol_\d+$`）；非法即 `GuardError`/`BusinessError`（exit 1，CLI 层收口为 exit 2 语法错误）；兜底用 `Path(os.path.normpath(ws / ...))` 后断言 `is_relative_to(workspace)`。

#### [SEVERITY: L1] D-02 `init --force` 全域台账清空，备份范围远小于覆写范围
- **行号**：ops.py L159–164（仅备份 5 个文件）vs L230–253 + L290（无条件重写 16 个状态文件）；cli.py L173（帮助文本只写"覆盖 project.json"）、L444–446（`init` 无条件转发 force）
- **问题描述**：`--force` 前只对 `project.json / outlines/vol_01/outline.md / characters/protagonist.md / state/current.json / state/milestones.json` 做 `.bak`；随后 `_save_json` 把 `items / places / factions / lines / locked / debts / relations / ledger / timeline / synopsis / co_occurrence / entity_timeline / sync_log / persons` 等约 16 个台账全部覆写为空（persons 仅剩 p_001/p_002 种子）。即：**一本已合账 N 章的书，一次 `init --force` 静默抹掉全部人物/伏笔/道具/资金/恩怨/时间线事实，且这些文件无 `.bak` 可恢复**（唯一补救是既有 snapshot）。CLI 帮助文本"强制重置（覆盖 project.json）"与实际的全域 wipe 严重不符，构成误导性授权。
- **触发路径**：人类/Agent 想改书名或题材 → `python studio.py init -t 新名 -g 新题材 -w <ws> --force` → 台账全毁，exit 0 且无任何警告。
- **建议修法**：备份清单与覆写清单对齐（重置前对全部将被重写的 `state/*.json` 自动 `.bak`），或 `--force` 时强制要求先 `snapshot create`（无近期快照即阻断）；帮助文本改为"将清空全部台账状态并重置为种子数据"。

---

### 🟠 L2（8 项）

#### [SEVERITY: L2] D-03 `proposal_auto` 回写细纲经过有损 mini-yaml 往返，SSOT 静默失真
- **行号**：ops.py L1083–1085；parser.py L184–213（`_strip_comment`）、L232–353（`parse_mini_yaml`）
- **问题描述**：`proposal_auto` 把 `parse_frontmatter` 得到的 dict 用 `dump_mini_yaml` **整体重写** beats 文件（`f"---\n{dump_mini_yaml(fm)}\n---\n{body_text}"`）。mini-yaml 是有损子集：frontmatter 内 YAML 注释被 `_strip_comment` 静默删除；块标量（`|`/`>`）、锚点、多行流式结构解析期即被拆解/丢弃；值内未加引号的 `#` 被当注释截断。重写**无 `.bak`、无 diff、无回执提示**。细纲是 SSOT，静默丢失编剧批注直接侵蚀"唯一事实源"完整性。
- **触发路径**：Screenwriter 在 beats frontmatter 写注释 → Auditor 第 3 节登记涌现事实 → `proposal auto <ch>` 回写 → 注释消失且无任何痕迹。
- **建议修法**：回写改"定位补丁"式（仅在 frontmatter 文本内插入/替换 `state_deltas`、`new_entities` 两个键的文本块，其余原样保留）；或重写前自动 `.bak`；至少做往返等价校验（re-parse 比对），不等价即阻断并提示。

#### [SEVERITY: L2] D-04 `finalize` 配方提取静默漏抽 + 计数失真（假阴性放行）
- **行号**：ops.py L800–839（`_apply_recipe` L807–820；`pattern_block` L823–828；`pattern_inline` L833–839）
- **问题描述**：(a) **版式敏感**：`pattern_block` 要求 Target fence 与 Replacement fence 紧邻（中间只容许空白与 `- `）；Auditor 把"- 理由:"行插在两者之间、或使用别名表外的写法（`改为:` / `替换成:` / `修订为:`，表内只有 `替换为`）时，整条配方**静默丢弃**，回执却报"审计报告中无配方，按原文定稿"且 exit 0——违背"吸纳配方做确定性替换（回执含命中/未命中）"契约，属该拦未拦。(b) **计数失真**：`recipes_total += 1`（L815）在空判之前，空 `TargetContent`（fence 内空行）计入总数但既不计命中也不计未命中，回执 X/Y 虚高。(c) 同一 `tc` 配两条不同 `rc` 时，第二条因 prose 中 `tc` 已被首条替换而计入 `missed`——把版式冲突误报为"未命中"。
- **触发路径**：Auditor 未严格按模板版式书写 → finalize exit 0 但硬伤未修 → sync/export 全线绿灯。
- **建议修法**：替换正则扩充别名（改为/替换成/修订为）并容许 Target 与 Replacement 之间穿插理由行；空 TargetContent 直接跳过不计数；同 tc 多 rc 输出冲突清单；审计报告含"修补配方"字样但提取为 0 时给 warning 或阻断。

#### [SEVERITY: L2] D-05 `proposal_auto` 对引擎自家模板的 `[道具变动] ｜ 变动:` 键完全不读
- **行号**：ops.py L942–958
- **问题描述**：`istatus_or_holder` 只查 `持有人/持有者/支配人/归属/获得者/状态/holder/status` 八个键。而 audit 模板第三行示范格式为 `- [道具变动] 道具: X ｜ 变动: 持有者流转或耐久变动`（ops.py L706 自家模板）——**"变动"键从未被读取**，`holder_or_status` 回落到 `pos[1]` 或 `"active"`：已建档道具被写成 `status: active`（真实流转/损毁丢失）；未建档道具 `default_holder = protagonist`（L1071）凭空记到主角身上。按模板填写的 Auditor 100% 命中此坑，错误事实随后经 sync 入账。
- **触发路径**：Auditor 照模板填 `[道具变动] 道具: 玄铁令 ｜ 变动: 已损毁` → proposal auto → 道具未损毁/错挂主角 → sync 入账错误事实。
- **建议修法**：kv 键表增加 `变动/变更/流转/结果` 并做语义归一（含"损毁/销毁/遗失/消耗"→destroyed/lost/consumed，"损坏"→durability 变更，其余按人名解析 holder）；无法解析的变动值显式告警而非静默兜底。

#### [SEVERITY: L2] D-06 `evidence_candidates` 裸 except 吞异常，假阴性回报"台账完备"
- **行号**：ops.py L1504–1541（try L1504；`except Exception: pass` L1540–1541）
- **问题描述**：细纲解析全程 try 包裹后静默 pass；`parse_frontmatter` 对畸形 frontmatter 返回 `{}` 而非抛错，于是命令返回 `"未发现未登记关键次要实体，台账完备"`——把"我没读成"报告成"没问题"。这正是 v4.3.2 #24 注释想补的 Librarian 盲区，却在 evidence 侧留下静默吞异常后门（check.py `scan_ledger_integrity` L203–204 有同款 `except Exception: pass`，见 [需动态验证]）。
- **触发路径**：beats frontmatter 含 mini-yaml 不支持的结构 → candidates 恒空 + "台账完备" → Librarian 漏报 Level 2。
- **建议修法**：except 分支把 `解析失败: {e}` 回填进 candidates/message；或让解析失败显式冒泡由 CLI 报 exit 1。

#### [SEVERITY: L2] D-07 `_audit_has_author_content` 漏检行内配方与无括号涌现行，Auditor 成果可被静默覆盖
- **行号**：ops.py L579–604
- **问题描述**：守卫只识别 (a) 三反引号 fenced 配方（L591–596）、(b) `[标签]` 开头的涌现事实行（L598–603）。而 finalize 的行内提取器明确支持 `TargetContent: \`原句\` ｜ ReplacementContent: \`新句\`` 反引号格式（L833–839），proposal_auto 也支持 `阵亡: 张三` 无括号前缀（L904–906）——**引擎自己支持的这两种格式写的成果，守卫判"无成果"**，于是 `audit` 重跑时无 `--force` 也无 `.bak` 直接覆写 `log/audit/ch_XXX.md`。`cruise.supervise_once` 每章起手调 `audit_chapter(write_file=True)`，任何重跑路径都会静默销毁这类成果，AGENTS.md 公理一的"双向闭环"在巡航路径上再次失效。
- **触发路径**：Auditor 用行内反引号格式写配方 →（巡航或手工）再跑 `audit <ch> --write` → 配方/涌现事实被抹掉，无迹可查。
- **建议修法**：守卫与 finalize/proposal 的提取正则共用同一套模式定义（单一事实源）；或写入前对既有文件做"非占位内容"diff 兜底，检测到即拒绝并提示 --force。

#### [SEVERITY: L2] D-08 `evidence_candidates` 字符串形态 `present_characters` 假阳性
- **行号**：ops.py L1519–1526
- **问题描述**：字符串分支判据为 `cid not in persons_db and (not cname or cname not in known_names)`，而 `cname = persons_db.get(cid, {}).get("name", "")`——cid 不是 persons 键时 cname 恒为 `""`，`cname not in known_names` 恒真。于是 `present_characters` 写**人物姓名**（init 的 `current.json` 就是姓名形态，L237）时，凡已建档角色全部被报成"未登记候选"。（dict 分支 L1527–1531 的姓名判定是正确的，仅字符串分支漏。）
- **触发路径**：beats frontmatter `present_characters: [齐鸣]`（齐鸣已建档）→ `evidence candidates ch_XXX` 报齐鸣为未登记实体 → 救捞清单被假信号稀释。
- **建议修法**：字符串分支补 `cid not in known_names and cid not in persons_db` 双向判定（姓名命中 known_names 即排除）。

#### [SEVERITY: L2] D-09 `milestone_achieve` 无状态机校验
- **行号**：ops.py L2045–2070
- **问题描述**：(a) 对已 `achieved` 的里程碑可无限重复达成（时间戳覆盖）；(b) 不校验达成章 vs `target_ch`/`current_ch`——target_ch=200 的里程碑可在 ch_010 登记达成，check.py 3.6 节"排产超期"巡检被静默消警；(c) `title` 重名时 `m.get("title") == milestone_id` 命中第一条，可能标错里程碑（`milestone_add` 也不查 title 唯一性）；(d) `-c ch_12` 非规范写法原样落库 `achieved_ch="ch_12"`，与 trace 期望的 ch_XXX 形态不一致。
- **触发路径**：`python studio.py milestone achieve ms_001 -c ch_005`（目标第 200 章）→ 静默改状态，cockpit 显示已达成。
- **建议修法**：达成时校验 `status == pending`、达成章号 ≤ target_ch（超前达成要求显式确认）；chapter 归一复用 `_chapter_num_arg` 逻辑；title 匹配歧义时列出候选要求改用 ID。

#### [SEVERITY: L2] D-10 ops.py 槽位闸门未剥离行内代码跨度（check.py 已修同类，ops 侧漏改）——假阳性阻断
- **行号**：ops.py L66–71（`_find_unfilled_slots`）；用于 finalize L754、sync L1122；对照 check.py L26–31（`_INLINE_CODE`）、L48
- **问题描述**：`_find_unfilled_slots` 裸匹配 `{{slot:...}}`，未先剥离行内代码跨度。check.py 的闸门为同一类文件专门修过此问题（v4.3.2 #29：反引号代码跨度内是"在描述槽位语法本身"），ops.py 的孪生实现漏改。后果：beats 正文/脚注里用反引号引用槽位语法示例（如编剧备注"`{{slot:foo}}` 待 Stage 0C 消灭"）时，**finalize 与 sync 双双重阻断**，提示"细纲仍含 N 处未填占位符"——该放行却阻断，且工作需手工删示例才能过，提示信息具有误导性。
- **触发路径**：Screenwriter/Auditor 在 beats 中反引号引用槽位语法 → `finalize`/`sync` exit 1 假阻断。
- **建议修法**：`_find_unfilled_slots` 与 check.py 共用同一 `_INLINE_CODE.sub("", text)` 预剥离逻辑（提取为 engine 级公共函数）。

---

### 🟡 L3（17 项）

| # | 行号 | 问题 | 触发路径 | 建议修法 |
|---|------|------|----------|----------|
| L3-01 | ops.py L1196–1205 | `--refresh` 对 timeline 缺该章时 `_tl_hit=False` 静默跳过更新，却回报 refreshed 成功 | sync_log 有条目但 timeline 缺章（半提交残留态）时 refresh 假成功 | 未命中时 warning 或降级为错误 |
| L3-02 | ops.py L1236–1249 vs L1250–1274 | 幂等短路先于 inbox 提案融合：首次 sync 后 Auditor 补充涌现事实，再跑 `proposal auto` + sync（无 `--force`），新事实被静默跳过且无提示 | 定稿后修订审计报告再提案 | 检测 inbox 提案新于 sync_log 时提示"需 --force 重入账" |
| L3-03 | ops.py L1136–1141 | 细纲 `chapter_id` 为空时跳过一致性校验（`if fm_ch and ...`） | beats 缺 chapter_id 字段仍可合账 | 缺失即阻断（SSOT 必填） |
| L3-04 | ops.py L1263–1274 | inbox 融合未判 `state_deltas` 类型，非 dict（字符串/列表）时 AttributeError → CLI 通用异常 exit 4 | 手改/损坏的 proposal_*.json | isinstance 守卫 + 坏提案隔离报 exit 1 |
| L3-05 | ops.py L339–346 | `re.sub` 以未净化的 `chapter_id` 作替换串，含 `\1` 等反斜杠序列时抛 `re.error` → exit 4（参数问题却报系统故障） | 章号参数含反斜杠 | 用 `str.replace` 或 `lambda m: chapter_id` 替换式 |
| L3-06 | ops.py L1577–1580 | 逾期判定：`target_ch` 非纯数字结尾时 `_num` 返回 0，`0 < latest_ch_num` 恒真 → 格式异常伏笔被误列"已逾期" | lines.json 中 target_ch 写"第12章"等 | `_num==0 且 target_ch 非空` 时单列"目标章格式异常" |
| L3-07 | ops.py L1699–1702、L1728–1734 | `rollup` 排序键：`t.get("chapter_id","0")` 键存在但值为 None 时 `re.search(None)` TypeError；`sorted(l.get("id") ...)` 混 None 崩溃；均 exit 4 | timeline/lines 条目字段缺失或手改 | `str(t.get("chapter_id") or "0")`、`(l.get("id") or "")` |
| L3-08 | ops.py L1984–1987 + L2128 | 快照名时间戳粒度仅到秒：同一秒内两次 `snapshot create pre_rollback`（连续回滚）互相覆盖，安全备份静默丢失 | 一秒内连续 rollback | 冲突时追加序号或微秒时间戳 |
| L3-09 | ops.py L2152 | `zf.extractall` 无原子性：中途 IO 失败留半恢复态，且 L2160 对齐清除未执行，工作区处于快照与现状混合态且无报告 | 回滚时磁盘满/文件被占用 | 先解压临时目录再整体替换；失败时提示用 pre_rollback 恢复 |
| L3-10 | ops.py L143–147 | 模板目录缺失报 `BusinessError`（exit 1），环境/安装问题应为 exit 3；且单个模板文件缺失时静默半初始化（project.json 不生成，后续命令才以"工作区未建档"失败） | 安装不全/误删 templates/ | 分类退出码 + 模板清点校验 |
| L3-11 | ops.py L858–1096 + cli.py L224–225 | `proposal auto` 的 `--write`/`--force` CLI 旗标是空操作（函数无 write 形参，恒写），与 beats/audit 的 `--write` 语义不一致——用户以为预览，实则细概已被改 | `proposal auto ch_001`（不带 --write）也落盘 | 补 write 形参或 CLI 移除旗标 |
| L3-12 | ops.py L750–753 | beats 整体缺失时跳过槽位闸门直接定稿生成 final/，直到 sync 才报"未找到细纲" | 跳序执行 finalize | beats 缺失即阻断（先建细纲） |
| L3-13 | ops.py L447–454、L468 | beats 简报：地点匹配用子串互含，`curr_loc` 为默认串"待定（如 宗门大殿/核心现场）"时与短地名误配；伏笔到期用 `ftarget == chapter_id` 精确串比，`ch_05` vs `ch_5` 形态不一即漏"到期"标注 | 默认地点值 / 非规范章号 | 地点匹配改规范化全等/前缀；到期按 `_chapter_num` 数值比较 |
| L3-14 | ops.py L2011–2027 | `milestone_add` 的 GuardError 手工内嵌 `💡` 而未用 `solution=` 参数，靠 CLI `split("💡")` 兜底渲染；与其他错误构造方式不一致，split 逻辑一旦变动即丢三件套 | 所有内置 💡 消息路径 | 统一 `GuardError(msg, solution=...)` |
| L3-15 | ops.py L360–364 | 上一章回查硬编码 `f"ch_{num:03d}"`，非规范章号（ch_5）时 prev_id 形态错位 → 简报"上一章"区块静默缺失（回落开篇文案） | 章号非 ch_XXX 规范形态 | 枚举实际存在的上一章文件 |
| L3-16 | ops.py L1152–1167 | 空 final 时 sync 自动 raw→final 补齐，绕过 finalize 的配方处理（Auditor 修补被跳过），仅一行 print 提示 | 未跑 finalize 直接 sync | 提示中明确"未经 finalize 配方处理"，或要求先 finalize |
| L3-17 | ops.py L1430–1451 | `ask_fact` 每次查询全量读 `bible/*.md` 全文并对全部 final 做 `find`，大体量书每次 ask 全量 IO | 大本书频繁 ask | 建索引或限制扫描范围 |

---

## 二、契约核对无问题项（逐项确认通过）

1. **`beats new` 拒覆盖已填细纲（--force + .bak）**：ops.py L552–564，已填（与脚手架不同）即 GuardError 三件套，`--force` 先写 `.bak` 再覆写；空/相同脚手架重写无副作用。✔
2. **`init` 已有书籍拒覆盖（--force）**：ops.py L135–141，GuardError + solution 齐全。✔（但 `--force` 的数据销毁面见 D-02）
3. **`sync` 空正文拒绝封存**：ops.py L1170–1174 GuardError；raw 自动补齐为既有设计（v4.2.4）并有 print 提示（瑕疵见 L3-16）。✔
4. **`sync` chapter_id 一致性**：ops.py L1136–1141，细纲声明与参数不一致即 BusinessError。✔（空值跳过见 L3-03）
5. **`sync` 事务预检/写盘前拦截**：哨兵语义完整——写前立哨兵（L1287）、零写盘异常清哨兵（L1290–1297）、完成后清除（L1327）；预检本体（死者登场/充能透支）在 `state.py apply_chapter_delta`（L730 注释证实先预检后写盘），[需动态验证]。
6. **`sync` 幂等分层**：同指纹幂等跳过（L1236–1244）、异指纹拒（L1245–1249）、`--refresh` 刷字数不重复入账（L1185–1228）、`--refresh` 对未同步章阻断（L1229–1235）。✔
7. **退出码 0/1/2/3/4**：errors.py + cli.py L739–803（Business/Guard→1，argparse→2，RuntimeError→4，未预期→4；环境码 3 由 studio.py 启动层发）。✔（init 模板缺失分类见 L3-10）
8. **❌【阻断原因】+ 💡【解决方案】三件套**：cli.py L771–778 统一渲染，message/solution 拆分逻辑完备（含内嵌 💡 的兜底 split）。✔（构造不规范见 L3-14）
9. **finalize 命中/未命中回执**：ops.py L845–855，`replacements_applied / recipes_total / recipes_missed / missed_targets` 齐全；占位配方（待修改原句/通俗修改后原句）过滤正确（L803–804, L813–814）；`str.replace` 字面替换天然免疫正则特殊字符。✔（漏抽/计数见 D-04）
10. **proposal auto 回写目标**：细纲 frontmatter（`state_deltas.character_status` / `new_entities` / `state_deltas.items`）+ `state/inbox/proposal_{ch}.json` 留档；state 表由后续 sync 经 apply_chapter_delta 入账——链路自洽。重复执行基本幂等（name/id 去重 + setdefault 守卫）。✔（保真度/道具键见 D-03/D-05）
11. **snapshot create 名净化**：ops.py L1986，`../`、`*?"<>\|`、空白全部替换，`strip("._")` 防纯点名。✔
12. **snapshot rollback pre_rollback 自动备份**：L2128；备份位于 `snapshots/`，而 L2160 对齐清除的受管域清单（bible/characters/entities/outlines/state/manuscript/log）**不含 snapshots/**——备份自身不会被卷入清除。✔（秒级碰撞见 L3-08）
13. **rollback 按快照清单对齐清除**：L2144 zip_names 取自 infolist（即快照清单）；L2160–2177 按路径深度逆序清除清单外文件、`.bak` 与 `.corrupt-*` 豁免、空目录 rmdir 仅删腾空目录。✔（extractall 原子性见 L3-09）
14. **rollback 安全三闸**：带外快照拒绝（L2097–2114）、zip-slip 严格前缀校验（L2133–2143，已修 `startswith` 兄弟目录绕过）、缺 project.json 判非快照（L2147–2151）。✔
15. **beats new 简报注入**：卷位置（L340）、事件看点/断章（L343–346）、伏笔雷达（L461–470）、主角名（L342）、ID 速查块（L484–502）齐全；`_clean_slot_value` 槽位清洗（L74–82）防槽位串漂流。✔（地点/到期匹配见 L3-13；ID 速查的 `except Exception` L501–502 有可见降级文案，可接受）
16. **reconcile 第五节自洽体检覆盖**（委托 check.py `scan_ledger_integrity` L112–198）：生死状态 vs 弧光互斥（a）、道具 holder 幽灵 ID（b）、恩怨双方幽灵 ID（c）、关系双方幽灵 ID（d）、伏笔 resolved 缺回收章 + planted_ch 残缺（e）、锁定事实指向未入账章节（f）——**六项全部实现，无漏项**；reconcile 侧异常有透明降级行（ops.py L1655–1656）。✔（scan 内部吞异常见 D-06 关联）
17. **simulate impact**：空实体阻断（L1751–1755）；实体归一为 ID+名+别名后扫 timeline/synopsis/entity_timeline/lines/locked/debts/relations/items/places/milestones 十表（L1784–1940），含 target_ch 未来章波及（L1882–1883）；风险分级合理。✔（子串过匹配为已知设计取舍）
18. **milestone add 入口校验**：target_ch 类型/范围校验（L2011–2015）、目标章不得落后于 current_ch（L2022–2027）、发号按现存最大编号+1 且避撞（L2029–2038）。✔
19. **ask 空查询拒答**：L1387–1388。✔
20. **ops.py L2191 的 `id_list/id_next/trace_id` 导入**：cli.py L36–37、L49 从 engine.ops 再导入，为承重再导出，非死代码。✔

---

## 三、[需动态验证] 清单

1. **`state.py apply_chapter_delta` 的死者登场/位阶冲突/事务预检实际行为与 `_save_count` 哨兵计数语义**——sync 契约"写盘前拦截全部冲突"的实体在 state 层，本次仅核对到注释层（state.py L730、L819–848、L898）。
2. **dump/parse 往返对存量真实 beats 的保真度**（D-03 的实际杀伤面）：建议对全部 `outlines/**/beats/*.md` 跑一次 `parse_frontmatter → dump_mini_yaml` 往返 diff，统计注释/结构丢失文件数。
3. **Windows 大小写不敏感 FS 下 `CH_001`、`ch_001_extra`、空串等变体的实际命中行为**（D-01 的放大效应）。
4. **proposal_auto 以"姓名"为键的 `character_status` 在 sync → apply_chapter_delta 时能否被 `_resolve_person_id` 归一**——若不能，未建档死者会同时留下姓名键与建档后 PID 键两份 deceased 声明（轻微非幂等）。
5. **check.py `scan_ledger_integrity` 内部 `except Exception: pass`（check.py L203–204）的假阴性面**——单项记录解析异常即令后续全部扫描静默跳过，reconcile 第五节可能打 ✅（与 D-06 同源）。
6. **simulate impact 别名子串匹配在真实实体名（短名/互相包含名，如"齐鸣"vs"齐鸣远"）下的虚报率**（D-04 之外的风险分级漂移）。
7. **snapshot rollback 对齐清除对符号链接的实际行为**（zip 不存 symlink、`rglob` 是否跟随symlink 目录未实测；潜在循环或重复解包风险）。

---

## 四、统计

| 严重级 | 数量 | 编号 |
|--------|------|------|
| L1 | 2 | D-01, D-02 |
| L2 | 8 | D-03 ~ D-10 |
| L3 | 17 | L3-01 ~ L3-17 |
| **合计** | **27** | |

**报告结论**：ops.py 主体契约（防覆盖守卫、幂等合账、哨兵事务语义、快照三闸与对齐清除、reconcile 六项体检、退出码与三件套）实现完整且历史缺陷修复注释密度高；主要风险集中在 (1) 位置参数零校验导致的路径穿越面（D-01）、(2) `--force` 语义与实际数据面不符（D-02）、(3) proposal/finalize 两条"静默兜底"路径把格式差异转化为数据失真而非显式告警（D-03/D-04/D-05）、(4) 三处 `except Exception: pass` 型吞异常制造假阴性绿灯（D-06 及其关联）。
