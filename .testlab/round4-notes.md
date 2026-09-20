# 第四轮测试 · 工作笔记（进行中 · 内部草稿）

> 人类要求（.testlab/人类要求核心重点.txt）：测长篇一致性（各方面）、测各 SKILL（尤其需跑命令的）、
> 顺手修其他 bug、查漏补缺、需裁决处代为拿主意。
> 本轮重点补充：**当前在途修复（v4.3.3 / v4.4.0 标记，REPORT.md 未归档）的回归复证**。

## 0. 环境事实（本轮）
- Python 3.11.2（沙盒），引擎自称需 3.9+；`py_compile engine/*.py` 0 错；`--version` = 4.4.0
- 基座三工作区 check：probe / test-lab / field-lab 均 exit 0

## 1. 在途修复清点（REPORT.md 未记载，代码已落地）
- FIND-CT41 (P-7 中文弯引号) / CT42+42b (P-8 值丢弃 / P-6 类型漂移) / CT43 (P-5 锚点别名)
- FIND-CT44 (ID-7 两处漏网) / CT45 (ID-9 单章校验假绿) / CT46 (ID-6a 无限递归) / CT47 (ID-6b 模糊命中)
- FIND-CT48 (C-5 正整数旋钮下限) / CT49 (E-1 solution 静默丢弃) / CT50 (L-1 ledger.py 身份澄清)
  / CT51 (C-4 scope 段静默回落)
- v4.3.3：BUG#35~#47、FIND-SYNC（跨表事务哨兵）、FIND-B（parser 严格转义/反转义）、
  FIND-D（milestone achieved_ch）、FIND-G（flow mapping）
- v4.4.0：FIND-L（present_characters 白名单透传）、FIND-L3（生死契约归一提示）、
  FIND-M（trace profile 十维补齐）、FIND-N（死亡弧光同源）、FIND-O（机密滑窗长度门槛）、
  FIND-Q（last_seen_ch 单调）、FIND-R（'死' 单字过宽）

## 2. 本轮新发现（FIND-CT52 起编号）

### CT52（L1）pack 未设槽位闸门 ⇒ Drafter 唯一输入源被污染
- 实证：全新 init 工作区，`beats new ch_001 --write`（脚手架 38 槽位）→ `pack ch_001 --write`
  exit 0，回执「🟢 预算健康 (无损全量装配)」，`pack.md` 内含 **54 处 `{{slot:}}`**。
- 影响：Drafter（Stage 2）准读输入**仅** pack.md 且【绝对零命令】，无法自查；
  槽位串会被当事实展开进正文，直到 S5 finalize 才被拦（3 个 LLM 工序白干），
  属报告自定义的 L1「写手输入污染，全链路零告警」。
- 现状对比：finalize（缺陷#30 前移）、sync（缺陷#A5）有闸门；pack / audit / proposal auto 无。

### CT53（L1）proposal auto 未设槽位闸门 ⇒ S5 三兄弟闸门不一致
- 实证：同一工作区 `proposal auto ch_001 --write --force` exit 0，
  产出 `state/inbox/proposal_ch_001.json` 通篇 `{{slot:}}`（present_characters.id、
  epistemology 键、character_status 键全为槽位串）。
- 风险：Auditor 有涌现事实时 proposal auto 会**回写细纲 SSOT**（FIND-CT12 .bak），
  槽位态回写 = 有损 mini-yaml 往返 + 按槽位键分配 ID。

### CT54（L1 存量 + check 假阴性）槽位串被登记为台账实体，体检全绿
- 实证：**金基座** `workspace/test-lab/state/persons.json` 存在
  `id = name = "{{slot:char_1_id|p_001}}"` 的幽灵人物（condition 亦为槽位串），
  `id list person` 显示 5 项（含 1 项垃圾），`check` **0 errors / passed=true**。
  同一幽灵已进入 `state/history/ch_001.json`、`ch_002.json` 快照切片。
- 根因：`state.py:1030` character_status 自动打捞建档 `persons_db[cid] = CharacterRecord(id=cid, name=cid)`
  对键零消毒（宽容自愈公理本身合法，但槽位串/畸形 ID 必须排除）。
- 根因2：`id_tracker.check_id_integrity` 只校验**细纲引用侧** ID 格式，
  对**四表存量记录**的 ID 形态零校验 ⇒ 存量污染永久假绿。

## 3. 待办 / 裁决
- [ ] FP-4 倒叙章死者登场豁免（人类裁决项 → 本轮代为拿主意）
- [ ] FN-8 prose 层死者检测是否立项第三阻断级（人类裁决项 → 本轮代为拿主意）
- [ ] cli.py `_preparse_global_flags` 返回注解用 `Tuple` 但未 import（被 PEP563 掩盖）
- [ ] `status --json` / `cockpit --json` 未实现（matrix C4 声称应为合法 JSON）
- [ ] beats 脚手架 title 兜底为「第ch_001章」（卷纲无预排时）

---

## 4. 第四轮收尾（完结确认）

> 本节为第四轮定稿补记：草稿中「待办 / 裁决」四项的终态。

| 项 | 终态 |
|---|---|
| FP-4 倒叙章死者登场豁免 | **实施（FIND-CT68）**：`present_characters` 条目加 `appearance: "回忆"`（亦接受 倒叙/闪回/梦境/幻境/亡魂/生前/托梦…）即豁免复活闸门，放行并留可追溯提醒；台账 `life_status: deceased` 与卒章**永不因此改变**；无标记仍硬阻断（三选一 💡 方案）。`state.py` 与 `id_tracker.py` 双侧同口径；screenwriter / auditor SKILL 已同步 |
| FN-8 正文层死者检测是否升为第三阻断级 | **驳回**：保持 warning-only。实证三态——已登记死亡章零误报、未登记死亡点名提醒且 exit 0、非死亡修辞（死寂/该死/生死）零假阳性；升为阻断会重新破坏 BUG#47 的契约分层（结构化 `life_status` 才是唯一硬裁决源），残余风险由 probe→auditor→proposal→sync 链自愈 |
| cli.py `Tuple` 注解未 import | 被 PEP563 掩盖、无运行时影响；本轮 `check.py` 已实际引入 `Tuple`（`scan_ledger_integrity` 两级返回），注解一致性顺带收敛 |
| `status --json` / `cockpit --json` | **未实施**（matrix C4 的期望属越权扩张：`help --json` 是唯一承诺的机器可读面）。改为在 `.testlab/matrix.md` 侧修正期望，不给引擎加未被要求的旗标 |

**第四轮总账**：CT52～CT68 共 17 项缺陷闭环（含 3 项 L1：pack/proposal 槽位闸门、存量幽灵记录）；
长篇基座 `workspace/long-lab`（2 卷 30 章 48,178 字）建造完成并作为**主金基座**取代 test-lab；
测试资产三件：`build_long_lab.py`（建造器）、`long_lab_battery.py`（A/B/C 电池 117 项）、
`skill_surface_audit.py`（10 SKILL 命令面审计 108 项）；
新旧引擎差分回归：test-lab / probe / field-lab 共 12 张状态表逐字节一致（零漂移）。

**本轮踩坑备忘（方法论）**：
- 绝不用管道截断采样引擎输出（`| Select-Object` / `| head` 会吃掉退出码与尾部报告）——CT55「token=3」即假警报；
- `echo "exit=$?"` 接在管道后拿到的是最后一个命令的退出码，必须裸跑；
- 注入 YAML 要**替换**目标值而非前置追加（重复键 last-key-wins 会让注入失效，C-03 教训）；
- 快照名带时间戳，回滚前先 `snapshot list`；
- 台账流水键是 `chapter` 不是 `chapter_id`；`id_tracker` 循环变量是 `p_item` 不是 `pc`；
- 脏数据 ≠ 引擎缺陷，但**引擎对脏数据的反应**是一类独立缺陷（CT54 存量幽灵记录即此类）。
