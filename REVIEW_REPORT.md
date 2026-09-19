# 🔍 Novel Studio 全案交叉审查报告（文档↔文档 / 文档↔代码 / 字段契约 / 引擎预演）

> 审查方法：通读全部 10 份 SKILL 文档 + AGENTS.md + engine/README + templates/README + 全部模板；
> 逐行通读 engine/ 全部 4900 行源码；在沙箱中**实弹预演**完整流水线（init → beats → pack → raw v1/v2/v3 → audit → finalize → proposal → sync → snapshot → reconcile/rollup/export/cruise/rollback），并对每类守卫做破坏性测试，共 38 组实测。
> 结论先行：**架构设计成熟、防御意识优秀，但存在 5 个高危、6 个中危、10+ 个低危问题**，其中 3 个属于"文档指挥你把数据写进引擎永远读不到的地方"，1 个属于"成书导出每章吃第一行"的实打实数据丢失。

---

## 一、 总体健康度评估

| 维度 | 评分 | 说明 |
|---|---|---|
| 退出码契约 (0/1/2/3/4) | ✅ 实测全对 | 0 通过 / 1 业务阻断 / 2 参数错误 / 3 环境 / 4 系统故障，与 AGENTS.md 一致 |
| 六类硬阻断 | ✅ 全部生效 | JSON损坏、死者登场、充能透支、空正文封存、SSOT覆盖、init覆盖，实测均正确拦截 |
| 幂等与原子性 | ✅ 基本可靠 | 原子写盘、sync 幂等跳过、--force 重放不翻倍（共现/弧光/恩怨实测）、快照 zip-slip 防护、快照名净化均通过 |
| 文档↔代码命令面 | ⚠️ 97% 一致 | 33 个命令仅 `rollup`（少写 `state`）1 个错误，但错误命令恰好出现在最高频的卷末流程 |
| 文档↔代码字段面 | ❌ 有 3 处硬伤 | debts 位置、life_status 枚举、（见第三节 B/C）——都会造成**静默数据丢失** |
| 数据终产物正确性 | ❌ export 有实质 bug | 每章首行被吃、rollback 残留未来章节、初始资金池被蒸发 |

---

## 二、 🔴 高危问题（建议立即修，均有实测证据）

### A1. `export` 成书导出吃掉每章正文第一行【代码 bug · 数据丢失】
- **现象**：正文文件若无 `#` 开头的 markdown 标题行，导出成书时**第一章第一段第一行被静默丢弃**。
- **实测**：ch_001 final 首行"酸雨砸在劣质霓虹灯牌上…"，导出 `export/测试之书.md` 中 `grep -c "酸雨砸在"` = **0**。导出总字数 208 ≠ 台账累计 312。
- **根因**：`engine/exporter.py` 章节标题规范化循环——扫描第一个非空行时，无论该行是否为 `#` 标题，都执行 `body_start = i + 1`，导致非标题首行被跳过：
  ```python
  for i, ln in enumerate(lines):
      if ln.strip():
          m = re.match(r"^#\s+(.+)$", ln.strip())
          heading = m.group(1).strip() if m else ""
          body_start = i + 1   # ← 非标题首行也被跳过
          break
  ```
- **修法**：仅当该行确实是标题时才 `body_start = i + 1`，否则 `body_start = i`。
- **影响面**：Drafter 系文档均未要求正文以 `#` 标题开头，全题材全部书籍的每一章都丢开场白。

### A2. architect SKILL 指示把恩怨写进 `ledger.json`，引擎只读 `debts.json`【文档 bug · 开局恩怨静默蒸发】
- **现象**：`.agents/skills/architect/SKILL.md` Stage 0B 工序 2 原文：「`state/ledger.json`：在 `debts` 中登记开局未清算血仇/恩怨 `DEBT-001`…」。严格照做后，引擎全景失明。
- **实测**：按文档写入后 `beats new` 机要简报与 `pack.md` 的恩怨区块均显示"暂无未清算因果血仇"，cockpit 恩怨账 0 笔。引擎全部读取路径（`state.py get_debts` / beats 简报 / pack 恩怨区块 / cockpit / id list）只认 **`state/debts.json`（独立文件，顶层 list 结构）**。
- **修法**：改 architect SKILL 为「`state/debts.json`：顶层数组登记 `DEBT-001`…」；`ledger.json` 仅保留 `pools` 与 `transactions`（schema.py `LedgerRecord` 本就无 debts 字段）。
- **次生问题**：见 A3——即使把初始池声明对了，也会在第一次 sync 蒸发。

### A3. 初始资金池余额在第一次 sync 时被静默清零【代码 bug · 资金蒸发】
- **现象**：`state.py` 账本同步块：`ledger_delta = state_deltas.get("ledger") or {}`——空 dict 也是 dict，`isinstance(ledger_delta, dict)` 恒真，于是**每一次 sync（哪怕本章毫无经济变动）都会执行全量重放**：`pools[池名] = sum(全部流水)`。Stage 0B 手工声明的初始余额（如 `"功德": 100`）没有流水支撑，直接被清零；同时凭空多出一个 `通用资金池: 0`。
- **实测**：建书时声明 `"功德": 100`，ch_001 sync 后快照内 `功德: 0`，还多出 `通用资金池: 0`。reconcile 报告显示"结余 0，合规"——蒸发完全无痕。
- **修法**：仅当 beats 的 `state_deltas.ledger` 真实声明（非空 dict 且含 delta/pool）才进入账本块；或引入 `initial_balance` 字段参与重放。
- **文档冲突**：architect SKILL 明确要求 0B「在 `pools` 中声明本题材货币池」，当前引擎使该动作沦为无效甚至误导。

### A4. `snapshot rollback` 是覆盖式解压，回滚后"未来章节"残留并被继续导出【代码/设计缺陷】
- **现象**：rollback 只以快照内容覆盖还原，**不删除快照之后才产生的文件**。回滚到 ch_001 后，`manuscript/vol_01/final/ch_002~004.md` 仍在磁盘上；`export` 只 glob final 目录（不看 sync_log），被回滚的章节照常进入读者成书。
- **实测**：rollback 后 `sync_log=['ch_001']` ✓ 正确，但 final 目录仍有 4 章，`export` 导出 4 章。
- **修法**：rollback 前对受管目录（`manuscript/`, `outlines/`, `state/` 等快照覆盖域）做"删除快照外多余文件"的全量对齐，或至少在 rollback 回执中列出残留孤儿文件并提示手工清理；`export` 建议以 sync_log 为准校验封存集（`_sealed_chapters` 逻辑已有，可复用）。
- **关联**：director Scenario F【时光机回滚就绪卡】宣称"当前最新有效章节 ch_YYY ｜ 台账平账 100%"——对账是平的，成书却是混的。

### A5. `sync` 无槽位闸门：`{{slot:...}}` 占位符被当作实体 ID 注入核心台账【代码缺闸 · SSOT 污染】
- **现象**：编剧若漏填槽位，`sync` 会原样采信 frontmatter：实测垃圾 sync 后 `persons.json` 出现键 `{{slot:char_1_id|p_001}}`、`lines.json` 出现 `{{slot:line_1_id|GUN-001}}`、`relations.json` 出现 `{{slot:...}}->{{slot:...}}`。`check_id_integrity` 对含 `{{` 的 ID 一律跳过（宽容设计），谁也拦不住。
- **连锁污染**：槽位串还会经 synopsis（dramatic_goal/cliffhanger 正则从正文抓槽位串）→ 写进下一章 beats 简报（实测 ch_002 简报出现 `【上一章断章定格】{{slot:ch_001_cliff|自行设定}}`）→ 写进 export 章节标题。
- **对照**：`check` 有完善的未填槽位闸门（307 处逐项点名），但 `sync`（巡航链中的自动入账者）没有任何同等校验；巡航模式 `supervise_once` 的 check 只看 errors，槽位只是 warnings，垃圾照封。
- **修法**：`sync` 前置校验 frontmatter 中**将入账的字段**（id/name/action/holder/target 等）是否含 `{{slot:`，含则 GuardError 阻断并给出解决方案文案；此为 SSOT 咽喉，值得硬闸。

---

## 三、 🟡 中危问题（逻辑错误/承诺不兑现，建议本季度修）

### B1. 紧凑形态 `present_characters: [p_001, p_003]` 下共现矩阵与实体时间线静默丢失【代码 bug —— "已修复"注释名不副实】
- state.py 在人物处理循环内对字符串条目做了**局部**归一化（重新赋值局部变量 `c`），但第 9 步 `co_occurrence` 与第 10 步 `entity_timeline` 遍历的仍是**原始未归一化列表**，`if not isinstance(c1, dict): continue` 把字符串条目全部跳过。代码注释明确写着"v4.2 修复……死亡阻断、出场事件、共现统计全部旁路"——**只修了一半**。
- **实测**：`present_characters: [p_001, p_003]` sync 成功，但共现矩阵无 `p_001<->p_003`、`entity_timeline` 中 p_003 无出场事件；死亡阻断对字符串列表有效（第一步归一化覆盖了预检），persons/arc_history 正常。
- **修法**：在函数开头做一次列表级归一化（`present_chars = [ normalize(c) for c in ... ]`），后续全部步骤共用。

### B2. `trace` 命令对 `fac_*` / `ms_*` / `ch_*` 三类合法 ID 无处理分支；按名 trace 势力会"命中后递归落空"【代码 bug】
- `detect_id_category` 能识别 faction/milestone/chapter，但 `trace_id` 只有 person/item/line/location/debt/lock 分支；兜底逆查（7.1/7.2）按**名字**检索且不含 milestones。实测：`trace fac_001` → 未检索到；`trace ms_001`、`trace ch_001` 同样；更戏剧性的是 `trace 黑虎帮`：兜底命中 fac_001 后递归，又回到"未检索到"。
- **影响**：主控 Scenario D"剧情推演"、Librarian/Evolution 依赖的穿透追踪对势力/里程碑/章节三类全废。CLI help 文案宣称支持"物理 ID 全生命周期穿透追踪"，名实不符。
- **修法**：补 faction/milestone/chapter 三分支（factions.json / milestones.json / timeline.json+synopsis.json 均有数据）；兜底循环补全表。

### B3. director SKILL 卷末三连命令中的 `rollup` 是不存在的命令【文档 bug · 恰好卡在高频流程】
- `director/SKILL.md` L282：`python studio.py rollup vol_XX -w "<wk>"`。CLI 只有 `state rollup`。实测 exit 2 invalid choice。
- **放大器见 B4**：argparse 的 exit 2 错误**不带 💡【解决方案】盒子**，直接打印 usage——违背 AGENTS.md/director"有阻断必有方案（Problem + Direct Remediation）"铁律。主控遇到此错无法按 Level 1 契约"提取终端方案自愈"，只能干瞪眼。
- **修法**：文档改 `state rollup vol_XX`（顺便统一顺序：引擎 cruise 自动刹车顺序是 rollup→reconcile→export，文档是 reconcile→rollup→export，建议对齐）；CLI 可考虑给 `rollup` 加兼容别名。

### B4. CLI 参数错误的输出形态不统一【契约漏洞】
- 引擎自制的 PARENT_COMMANDS 缺失分支（如裸 `beats`）有 ❌/💡 盒子 ✓；但 argparse 原生错误（invalid choice、`beats -w X` 把路径当子命令等）输出裸 usage，无解决方案文案。对"主控绝不猜测、只执行终端方案"的协议是硬伤。
- **修法**：顶层 `parser.error` 覆写或 try/except SystemExit 包装统一盒子。

### B5. 损坏 JSON"隔离一次后静默空表继续"【设计矛盾】
- `_load_json` 首次遇坏表：隔离为 `*.corrupt-*` + exit 4 ✓ 符合承诺。但**文件被改名后就不存在了**，后续所有命令走"文件不存在→返回默认值"路径：实测同步隔离后 `check` EXIT=0、sync 以空 relations 表照常运行。"绝不静默以空表继续"只兑现了一次。
- **修法**：state/ 下存在任何 `*.corrupt-*` 文件时，check/写类命令应持续报 warning（甚至 errors），直到人类处理。

### B6. `life_status: "missing"` 被静默吞掉【字段契约破裂】
- schema.py `CharacterRecord.life_status` 注释枚举 `alive/deceased/missing`，templates/README 同样列为"严格枚举"；但 `state.py _LIFE_STATUS_NORM` 只有 deceased/alive 两族映射。实测 beats 声明 `character_status: {p_003: "missing"}` sync 后 `life_status` 仍为 `alive`。
- **影响**：失踪剧情（网文高频）无法入台账；missing 角色登场无约束（这点或可接受）、pack/cockpit 无失踪视图。
- **修法**：`_LIFE_STATUS_NORM` 增加 `"missing"/"失踪"/"下落不明"` 映射。

---

## 四、 🟢 低危与文档漂移（建议排期清理）

| # | 位置 | 问题 | 证据/修法 |
|---|---|---|---|
| C1 | director SKILL 换卷就绪卡 | 宣称导出 `exports/vol_XX.txt` | 实际是 `export/<书名>.md`（单数目录、md 默认、按书名命名），目录名/文件名/格式三处皆错 |
| C2 | engine/README 数据表 | `log/review/reconcile_vol_XX.json`（卷末对账存档） | 实际 `reconcile --write` 落盘 `.md`（librarian SKILL 写的恰好是对的 `.md`） |
| C3 | auditor SKILL 三节 | 报告区域名为「语义逻辑与出戏审查」 | 引擎骨架实为「语义逻辑、存疑备忘与修补配方（Auditor 专用)」，Auditor 按文档找节名会扑空 |
| C4 | cli.py help "check" | 宣称"七探针" | probes.py 当前实为 4 探针（字数/认知/称谓/物象），系版本漂移措辞 |
| C5 | ops.py `ask_fact` | 不检索 manuscript/ 正文 | librarian 声称用 ask"核查实体正文出处"、evolution 声称用 ask"检索正文绑定"，均落空（实测仅在正文出现的词零命中）。要么扩 ask 扫 final/，要么改两份 SKILL 的说法 |
| C6 | cli help "evidence candidates" vs ops 实现 | 宣称"自动从细纲声明与正文对白中发现未登记实体" | 实现只读 beats frontmatter（`prose` 读入后从未使用）。CLI 文案过度承诺 |
| C7 | probes.py 对白正则 | 只认中文弯引号 `“…”/「…」` | ASCII 直引号写的对白下，认知泄露探针全灭（实测直引号泄密零检出）。建议正则兼容 `"…"` |
| C8 | state.py 2.5 vs pack.py 3.8 | 地点匹配方向不对称 | state 只有 `location in name` 单向，pack 有双向。`location: "黑诊所二楼"` 会在 places.json 重复建档为 loc_002（实测），而 pack 能正确匹配 loc_001 |
| C9 | beats 模板卷纲槽位继承 | `beats new` 用卷纲内容替换槽位 | 卷纲若未填，槽位串原样流入 beats title/goal/cliff，继而污染 synopsis/简报/export 标题（与 A5 同源但入口不同，属于 A5 闸门的第二战场） |
| C10 | state.py `new_entities` 默认 `role="supporting"` | templates/README 的 role 枚举（protagonist/deuteragonist/antagonist/ally…）无 supporting | 引擎自创枚举外取值，白名单文档失同步；同样 `evidence/grounding` 等对"单 dict 不写列表"形态的归一化与 state.py 不一致 |
| C11 | ops.py beats 简报 | 读 `synopsis["summary"]` 键 | state.py 写入的键是 `dramatic_goal`，`summary` 永不存在——简报【上一章核心进展】区块永远缺席（实测仅存断章定格），director 宣称的"提取本章分卷梗概"成色打折 |
| C12 | director S5 与巡航收口命令链 | 全文为 PowerShell 语法（`; if ($LASTEXITCODE -eq 0) {...}`） | bash/cmd 环境直接语法错误；文档未声明平台假设（AGENTS.md 禁脚本但命令链本身依赖 PS） |
| C13 | templates/outlines/volume_outline.md | 硬编码示例 `### ch_001~003` | `_volume_last_chapter` 以卷纲最大 `### ch_XXX` 定卷末：0B 若填卷不勤，巡航把卷末错认成 ch_003 提前刹车（实测） |
| C14 | Screenwriter"绝对零命令" vs ID 发号 | 编剧要声明新 `LOCK-XXX`/新埋 `GUN-XXX` 时无合法途径获得不撞号的 ID | 唯一防撞号工具 `id next` 是 CLI；简报只列 active 伏笔不含全量 ID。属于权限矩阵的设计空隙，建议 beats 简报附"各类型下一个可用 ID" |
| C15 | cruise 等待超时 | 超时刹车后无 results 条目，CLI 仍以 exit 0 结束 | 与"check errors>0 立即停机 exit 1"不对称；无人值守场景下 0 与"没写完"难以区分 |
| C16 | profiler 完工回执 | 头为【工序完工回执】，其余九份 SKILL 均为【章节工序完工回执】 | 统一即可（若未来主控靠回执头做机器识别会踩坑） |
| C17 | 0B 手写 JSON 结构容错 | lines.json 若被 0B 误写成 list（引擎期望 dict），`get_active_lines` 抛 AttributeError → 笼统 exit 4 盒子 | 建议在 `_load_json` 后加顶层类型校验并给出结构化 💡 提示（"该表应为 object/array"） |
| C18 | beats 模板 debts 条目 | 只有 target/type/desc/action，无 source 字段，引擎默认 `source=p_001` | 非主角结怨（p_002 vs p_003）无处表达；要么模板补 source 并注明默认，要么 SKILL 写明 |

---

## 五、 设计合理性专项评估（engine）

**👍 值得肯定的成熟设计**（审查中逐项实证）：
1. **四层数据完整性模型**（事务预检→按章幂等→原子写盘→损坏硬失败）方向正确，幂等实测扎实（`--force` 重放后共现/弧光/恩怨零翻倍）。
2. **"有阻断必有方案"错误盒子**（❌原因 + 💡方案）是 Agent 友好型 CLI 的教科书做法，但仍需覆盖 B4 的 argparse 盲区。
3. **探针强弱分级**（阻断级仅空正文与确认级认知泄露）克制且正确，实测两路均按设计触发/静默。
4. **快照三安全带**（pre_rollback 自动备份、zip-slip 防护、快照名净化）全部实测通过。
5. **pack 四级修剪 + 超预算显式 🔴 旗标**（绝不静默截断）实测成立，P0 保护逻辑清晰。
6. **死锁刹车哲学**：cruise 钳制 min(N, 卷末)、check errors>0 立即停机、守卫即 GuardError——边界清晰。

**🤔 值得深思的设计取舍**：
1. **"宽容自愈"与"硬闸"的边界当前漏在 SSOT 咽喉**：引擎对非核心字段宽容（好），但 `sync` 这个唯一的数据入账口对槽位污染、初始池蒸发、单 dict/列表形态差异都不够防御（A3/A5/C10）。建议把防御密度向 `sync` 倾斜而非分散在 check。
2. **导出（export）与封存（sync_log）双轨事实源**：export 看 final 目录、cruise 看"sync_log+final"、rollback 只还原文。三者不一致是 A4 的总根子。建议全书统一以 `sync_log` 为"已封存"唯一判据。
3. **文档驱动开发的回归风险**：SKILL 文档由人维护、命令由 argparse 生长，缺乏"文档命令↔CLI 真实面"的自动化校验。B3 这类错误（高频流程里的死命令）本可被一次 `studio.py help --json` vs SKILL 命令 diff 脚本拦截——建议把该 diff 做成 CI（恰好 AGENTS.md 禁止的是智能体写脚本，不禁止工程 CI）。
4. **槽位系统是全链路污染物放大器**：槽位串可以通过卷纲→beats→sync→synopsis→简报→export 标题一路漂流（A5/C9/C13）。一个统一原则可斩断：`生成期替换（init/beats new）”与“消费期校验（sync）”任一端对 `{{slot:` 零容忍。

---

## 六、 修复优先级建议

| 优先级 | 条目 | 一句话修法 |
|---|---|---|
| P0（阻塞读者产物） | A1 export 吃首行 | `body_start = i + 1 if m else i` |
| P0 | A5 sync 槽位闸门 | sync 前置扫描入账字段含 `{{slot:` ➔ GuardError |
| P0 | A3 资金池蒸发 | 空 dict 不进账本块 / 支持 initial_balance |
| P0 | A2 architect debts 文档 | 改写指引为独立 `state/debts.json` |
| P1 | A4 rollback 残留 | 对齐删除 or 回执明示 + export 以 sync_log 为准 |
| P1 | B1 紧凑共现半修复 | 列表级归一化前移 |
| P1 | B2 trace 三分支 | 补 fac/ms/ch 分支 + 兜底全表 |
| P1 | B3/B4 rollup 文档命令 + argparse 盒子 | 改 `state rollup` + 统一 💡 盒子 |
| P2 | B5/B6 + C1~C18 | 排期清单化清理 |

**一句话总结**：这套系统的"骨架"（幂等/原子/守卫/退出码/快照）是工业级的，但"关节"处有 5 处正在漏血——`export` 吃首行、`sync` 槽位污染、资金池蒸发、rollback 残留、以及 architect 文档把恩怨指引进了虚空。修掉 P0 四项后，系统可信度会有质的提升。

---

# 🛠️ 修复日志 FIXLOG（v4.3 · 全部闭环 · 已实弹回归）

> 修复完成后在全新沙箱（`/tmp/regr/book`：回归之书/都市高武/林渊）重建并跑通
> init → 0B 通电 → beats → pack → audit → finalize → proposal → sync ×2章 →
> 幂等/--force → export → snapshot/rollback → cruise 全链路，所有断言通过。

## 🔴 高危（A 组 · 全部修复 ✅）

| # | 修法落地 | 回归证据 |
|---|---|---|
| A1 | exporter.py 仅当真标题才 `body_start=i+1`（v4.3 缺陷#注释） | ch_001 首行「酸雨砸在临江医馆…」成书 grep 命中=1 |
| A2 | architect SKILL 改为 `state/debts.json` 顶层数组 + ledger 只声明 pools | 简报【恩怨对手戏】出现「杀父之仇」对手戏，不再空账 |
| A3 | 账本块仅非空 `ledger_delta` 才进入；新增 `pools_baseline` 首次冻结、池=基线+流水重放 | 初始功德 100 ➔ ch_001（无经济变动）池仍 100；ch_002（+50）池=150、baseline 冻结 100、流水×1，--force 重放零翻倍 |
| A4 | rollback 解压后对齐删除快照外受管文件（保 `.bak`/`.corrupt-*`），回执含 removed_files 并打印；export 以 sync_log 为准、未封存章跳过并打印清单 | 回滚后 ch_004 final/beats 自动清除、.bak/.corrupt 保留；export 只收已封存 2 章并打印「已跳过未封存章节」 |
| A5 | sync 前置槽位闸 `_find_unfilled_slots` ➔ GuardError | 35 处槽位实测拦停（exit 4 盒）；cruise 链同步刹车 exit 1 |

## 🟡 中危（B 组 · 全部修复 ✅）

| # | 修法落地 | 回归证据 |
|---|---|---|
| B1 | present_characters/items 在函数开头做列表级归一化，共现/时间线/预检共吃一源 | `present_characters:[p_001,p_003]` ➔ 共现矩阵 `p_001<->p_003` 入账、p_003 时间线出场事件入账 |
| B2 | trace 补 faction/milestone/chapter 三分支 + 兜底补里程碑按标题逆查 | `trace fac_001/ms_001/ch_001/青龙会` 四连全部正确渲染（青龙会不再递归落空） |
| B3 | director SKILL `rollup` → `state rollup`，卷末三连顺序对齐引擎（rollup→reconcile→export），注 bash 等价 | `python3 studio.py rollup …` 触 CLI 盒 exit 2；文档命令与 cruise 自动刹车链同序 |
| B4 | `_StudioArgumentParser.error` 覆写，全部子命令继承 ❌+💡 盒、exit 2 | 裸 `rollup` 实测得盒 + exit 2 |
| B5 | check 扫描 `state/*.corrupt-*` 持续 warning 显形 | `/tmp` 沙箱 check 报「损坏隔离残留 ×1」+ 💡 处置指引 |
| B6 | `_LIFE_STATUS_NORM` 补 missing/失踪/下落不明/失联 | `character_status:{p_003:"missing"}` sync 后 life_status=missing |

## 🟢 低危（C 组 · 全部修复 ✅）

C1 director 导出路径改 `export/<书名>.md`；C2 README `reconcile_vol_XX.md`；C3 auditor 节名对齐引擎骨架；C4 help/注释「七探针」→「四探针矩阵」；**C5** `ask` 补 factions/places 档案 + final 定稿正文证据切片检索（实测「血焰」跨两章命中）；**C6** evidence 文案回归「细纲声明源」真相（CLI help/ops docstring）；**C7** 对白正则兼容直引号 `"…"`，并**顺带重写说话人归属**：后置式句首名+言语动词优先、前置式要求言语动词/冒号，弃用误配根源的「前置宽松兜底」（四用例实测：弯/直引号本人泄密 confirmed、他人合法陈述 suspected、归属失败 suspected）；**C8** 地点匹配双向（`临江医馆二楼密室` 实测匹配 loc_001，不再重复建档 loc_002）；**C9** 卷纲槽位经 `_clean_slot_value` 清洗后不再流入 beats；**C10** templates/README role 白名单补 `supporting`，且 ops evidence/probes grounding/pack items 全部与 state.py 同一单 dict 归一化口径；**C11** 简报【上一章核心进展】改读 `dramatic_goal`（实测 ch_002 简报不再缺席）；**C12** director 全线 PS 链附 bash/zsh `&&` 等价；**C13** `_volume_last_chapter` 忽略纯槽位行 + 模板注明「卷末判定契约」（实测 ch_999 槽位行被忽略、卷末= ch_003）；**C14** 编剧简报注入【🆔 下一可用物理 ID 速查】（九类）+ screenwriter 宪法 2.1 发号契约；**C15** cruise 超时写 `status:"timeout"` + CLI exit 1（实测 3s 超时 exit 1）；**C16** profiler 回执头统一【章节工序完工回执】；**C17** `_load_json` 顶层结构类型校验（list↔dict 颠倒得结构化 💡 指引，不再退化成 AttributeError 饭盒）；**C18** beats 模板 debts 补 `source` 字段并注明缺省按 p_001 记账（ops 同步兼容 target/target_char 双键）。

## 🔧 修复期自发现并肩修复的新问题（超出原报告清单）

1. **发号器自我污染**：简报注释内🆔 速查块自身的 `fac_005`/`GUN-002` 会被 `id_next` findall 计入，逐章把水位顶高 1；另 bible 模板槽位键 `fac_4_name` 中的 `fac_4` 被 `fac_(\d+)` 误计→新书势力直接跳 fac_005。修法：`id_next` 扫描前统一 `_strip_html_comments` 消毒（剥注释块 + 抹除 `{{slot:KEY|` 键名段，DEFAULT 段保守保留）。实测速查块回归 fac_002/GUN-002 正确值。
2. **说话人归属误配**（见 C7，独立成段因其影响确认级探针公允性）。
3. **CLI 可视性补丁**：export/rollback 结果中的 unsealed_chapters、removed_files 原本只在返回值里，CLI 输出补齐打印（用户可见的透明化）。

## 📜 全链回归结论

107 项断言口径全部绿灯：init 防覆盖 → 0B 通电（debts/pools 分表）→ beats 🆔 速查 → pack 预算健康 → audit/finalize/proposal → sync（A5 闸 ✓ / 幂等 ✓ / --force 不翻倍 ✓）→ 台账八表正确（missing ✓ 共现 ✓ 时间线 ✓ 地点双向 ✓ 资金池基线 ✓ 恩怨 ✓）→ export（首行保真 ✓ unsealed 跳过 ✓）→ snapshot 三安全带 + 对齐清除 ✓ → check（0 errors + corrupt 显形 ✓）→ trace 四分支 ✓ → ask 正文证据 ✓ → cruise（卷末槽位忽略 ✓ 超时/刹车 exit 1 ✓）→ argparse/语法/PARENT 盒 exit 2 ✓。
**结论：审查报告全部 29 项（A5+B6+C18）+ 3 项自发现新问题，均已修复并实弹回归，系统达到「全口径可信」水位。**

---

## 🔄 R2 · 二轮精审增量修复（2026-09-19 下午 · 9 项新发现全闭环）

> 方法：对修复轮自身改动回归审查 + 首轮未深挖区域（cockpit/config/schema/exporter/studio.py/ops 末段/时序边界）系统重扫。

| # | 类别 | 问题与修法 | 实证 |
|---|---|---|---|
| R2-1 | 数据契约 | **sync_log 封存条目元数据贫化**：仅存指纹/时间戳，trace ch_XXX 拿不到章节名与入账字数。修法：sync 写入 title/word_count；trace 兼容旧日志回源 synopsis | `trace ch_003` 渲染「黑市风云 · 93 字」真值 |
| R2-2 | 大盘盲区 | **cockpit 对经济系统全盲 + 航标槽位汤**：未填卷纲标题/看点原样糊 `{{slot:}}` 进大盘。修法：💰 资金池与近笔流水遥测（含事由）+ 航标槽位清洗 | 大盘现「功德: 70 ｜ -30（事由: 黑市买凶情报）」 |
| R2-3 | 工程整洁 | exporter 逐章循环内反复读 synopsis.json（N 章 N 次 IO）→ 全书单次载入注入 | 导出口径不变，IO 降 N 倍 |
| R2-4 | 契约漂移 | schema `CharacterRecord.role` 默认 `other` 不在白名单（README 枚举无 other）→ 改默认 `supporting` 并对齐注释枚举 | 与 templates/README 一致 |
| R2-5 | 数据纯度 | **present 紧凑形态把中文名当物理 ID 建档**（幽灵人物 `周楚`/`曹冲` 入键）+ dict 只给 name 无 id 被整体跳过。修法：归一化时按 name/aliases 反查建档 ID | "曹冲"→p_002、{"name":"苏晚"}→p_003、别名"渊哥"→p_001，幽灵键∅，弧光正确 |
| R2-5b | 派生修复 | 别名混写归一化后同人重复 → 产生 `p_001<->p_001` 自配对与重复在场名单。修法：归一化后按 ID 去重，覆盖弧光/名单/共现/时间线全下游 | 4 条混写去重为 2 人，共现仅 `p_001<->p_003` |
| R2-6 | 经济溯源 | ledger 流水只有 delta 无事由（cockpit 与对账无从溯源）→ beats 模板补 `reason` 选填 + state 入账 | 流水含「黑市买凶情报」事由 |
| R2-7 | 版本契约 | 注释/文档全线 v4.3 而 `__version__` 滞留 4.2.4（设计不变量#7 被违反）→ 升 `4.3.0`，README 增修订注记 | `--version` 输出 4.3.0 |
| R2-8 | CLI 透明化 | snapshot rollback help 文案未告知对齐清除语义 → 补「+ 对齐清除快照后新增文件」 | help 契约自解释 |
| R2-9 | 架构注记 | ops.get_cockpit 为无 CLI 调用方的结构化对外 API（与 cockpit.py 渲染版重复易误解）→ 文档注记定位分工，保留兼容 | 分工自说明 |

**R2 终验**：全新沙箱卷末刹车链自动执行（rollup→reconcile→export 一次跑透）+ 全书 check 0 errors + 紧凑混写幽灵人物零产生 + 资金池事由遥测可视。**两轮合计 41 项全部闭环，引擎版本号同步升至 4.3.0。**

---

## 📚 R3 · 三轮文档专项精审（2026-09-19 晚 · engine 之外全部文档 · 7 项闭环）

> 方法：逐份精读 AGENTS.md、10 份 SKILL、templates/ 全部 17 件模板与 README、根 README.md，交叉比对文档↔文档矛盾与文档↔代码漂移（命令旗标/字段名/路径/行为语义）。文档与代码冲突时以代码现状为准改文档；仅当文档三方一致而代码单点偏离时改代码。

| # | 类别 | 问题与修法 | 实证 |
|---|---|---|---|
| R3-1 | 引擎缺陷（文档驱动发现） | **跨卷巡航误触发旧卷刹车链**：0E 交付 vol_02 卷纲后、首章 `sync` 刷新 `project.json` 之前，`cruise ch_031` 仍按 `current_vol=vol_01` 规划 → 目标卷 0 章、误判卷末并跑 rollup/reconcile/export。修法：`plan_cruise` 在 `start_ch` 存在时优先按章在 `outlines/` 中的实际所属卷解析（显式 `--vol` 与无 `start_ch` 路径行为不变，未知章号回落原逻辑） | 沙箱 vol_01 已封存 3 章 + vol_02 含 ch_004：`plan_cruise(ch_004)`→vol_02 且 `cruise ch_004 --once` 正确装配新卷细纲；`--vol vol_01` 显式覆盖有效；ch_099 未知章号回落 vol_01 |
| R3-2 | 字段口径三方对齐 | **地点禁忌读错键**：pack P1 读 `rules_taboos`，而 `schema.PlaceRecord`、`templates/README §4` 白名单、`entities/location_card` fm 三方都用 `environment_rules` → 地点规则永远进不了装配包。修法：pack 改读法定 `environment_rules`（数组以 `；` 连读），向下兼容旧键 `rules_taboos` | loc_001 新键→pack 现「禁忌规则：宵禁后禁止喧哗；医馆内不得动武」；loc_002 旧键→回退渲染成功 |
| R3-3 | 文档安全 | **director 教手工解压 zip 全量覆盖回滚**：与 v4.3 对齐机制冲突（手工覆盖不清除快照后新增的"未来章"文件、绕过 `pre_rollback` 自动备份）。修法：Scenario F 与【时光机回滚就绪卡】姿态 B 改为标准路径唯一推荐 `snapshot rollback`，手工路径标注末路方案 + 先备份 + 先清空受管清单（state/manuscript/outlines/log/pack.md/dossier.md/project.json） | 文档语义与引擎 rollback 行为一致 |
| R3-4 | 文档口径打架 | **卷章数四处三个数**：director/profiler 写「30 章」、architect/screenwriter 写「25~40 章」、`volume_outline.md` 写 `target_chapters: 50`。统一为 25~40 弹性口径：director 2 处、profiler 首卷潮汐规划 5 处（阶段区间改「卷前 1/4」等比表述）、volume_outline fm 40/80000 与导航注、project.json `chapters_per_volume: 40` 且 `target_volumes` 与总字数自洽（4→5 卷） | 全库 grep 无残留「30 章潮汐」 |
| R3-5 | 文档口误 | librarian「单次全读**实体四表**（persons.json, items.json）」——说四列二。修为「实体台账主表 persons/items + synopsis」，并注明卷末大修可追加 factions/places | 表述与准读白名单一致 |
| R3-6 | 文档缺位 | **根 README.md 是 2 行空壳**：无任何上手/导航信息。重写为正式门户（快速开始命令序列、AGENTS/skills/templates/engine 文档地图、引擎能力清单、冒烟自检） | 新 README 命令全部与 cli.py 用法清单核对一致 |
| R3-7 | 版本契约 | 引擎行为增量（R3-1/R3-2）+ 文档轮 → `__version__` 4.3.0 → **4.3.1**，engine/README 追加 v4.3.1 增量注记段 | `--version` 输出 4.3.1；cockpit 动态引用同源 |

**已核干净备案（未改动）**：beats.md fm 与 state 解析全键对账通过（chapter_type/timeline 经 parser 通用回退提取，regr 沙箱时间线块实证）；人物/势力/道具卡的 fm 扩展字段（attitude/faction/core_assets/diplomacy/power_benchmark/address_matrix 等）与 `templates/README §4` 白名单一致，属人读视图不入台账（卡正文由 pack/dossier 注入，系既有架构决策）；screenwriter 🆔 速查块、auditor 双配方格式、evolution/librarian 准跑命令、architect 0B 八表路径与 CLI 全对得上。

**R3 终验**：`py_compile` 全绿｜主回归沙箱 check 0 errors + pack 再生成正常｜跨卷巡航单测 4 断言 + CLI 端到端 1 次｜P1 新键/旧键/无键三分支实证。**三轮合计 48 项闭环，引擎 4.3.1。**
