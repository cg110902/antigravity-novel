# Novel Studio 引擎测试问题清册（第 1 轮）

测试方式：新建 `workspace/testbook`（《灰烬纪元》，4 章实战）+ `/tmp/tb2` 边界书，
跑通 init → beats → pack → 起草 → audit → finalize → proposal → sync → reconcile/rollup/export → cruise → snapshot 全链路。

---

## P0 · 数据正确性

### BUG#1 `sync --force` 重放导致道具充能重复扣减（违反文档「按章幂等增量·重放安全」）
- 复现：ch_001 声明 `charges_delta: -1`，初始 3 → sync 后 2；`sync --force` 三次后变 0，第四次误报「充能已耗尽」守卫阻断。
- 位置：`engine/state.py` 第 2 节道具同步（约 665~690 行）。`transfer_history` 已按章去重，但 `charges` 是裸累加，没有「回滚本章旧 delta 再应用」。
- 影响：卷末对账道具充能池失真；作者按文档做 `--force` 重同步反而被引擎自身阻断。

### BUG#6 无 `id` 的 debts 在 `--force` 重放时重复膨胀
- 复现：细纲 debts 不写 id（templates/beats.md 默认就不带 id），sync 一次 + force 两次 → debts.json 出现 DEBT-001/002/003 三条完全相同的恩怨。
- 位置：`engine/state.py` 约 840 行 `d_id = dd.get("id", f"DEBT-{len(debts_db)+1:03d}")` —— 缺省 id 随表长漂移，同章幂等键失效。
- 影响：恩怨账虚增，cockpit / pack 的「未清算恩怨」全部污染。

### BUG#5 `audit --write` 无条件覆盖已有审计报告，抹掉 Auditor 的修补配方与涌现事实
- 复现：在 log/audit/ch_002.md 写入 2 条修补配方 + 2 条涌现事实后，再跑一次 `audit ch_002 --write`，配方与涌现事实全部消失。
- 位置：`engine/ops.py::audit_chapter`，`target_audit.write_text(...)` 无存在性守卫。
- 严重性：`cruise.supervise_once` **每章开头就调用 audit_chapter(write_file=True)**，所以无人值守巡航会先把 Auditor 的成果清空再 finalize/proposal —— 双向闭环（AGENTS.md 公理一）在 cruise 路径上实际失效。
- 对比：`beats new --write` 有拒覆盖 + `.bak` 守卫，audit 没有，规格不一致。

### BUG#2 伏笔 type 不按 ID 前缀推断，KNO/MIS 全被记成 GUN
- 复现：`MIS-001`、`KNO-001` 在 lines.json 中 `type` 均为 `"GUN"`；`trace MIS-001` 显示「伏笔分类：[GUN]」。
- 位置：`engine/state.py` 第 3 节伏笔同步，`LineRecord(id=fid, name=...)` 用了 dataclass 默认 `type="GUN"`，且细纲 `type` 字段不被读取。
- 影响：schema 中 GUN/KNO/MIS 三分类形同虚设；id_tracker 已有 `detect_id_category` 能正确判定，state 没用。

---

## P1 · 探针与校验漏判

### BUG#4 认知泄露探针只认台账里的人名，首次登场角色的「本人泄密」被降级为疑似
- 复现：ch_001 正文里 p_002 裴照本人说出自己的盲区机密。`audit ch_001` 当时台账尚无 p_002 → 报「无确认泄露；1 处疑似」。ch_004 之后台账有了名字，`check ch_001` 立刻升级为确认级 error。
- 位置：`engine/probes.py::run_all_probes` 的 `name_by_id` 只从 `persons_db` 构建，未合并细纲 `present_characters` 的 id→name。
- 影响：同一份正文在流水线不同时点给出不同结论；首章（最常见的新人物入场章）恰好是漏判高发区。

### BUG#3 `proposal auto` 把审计模板里的占位示例行「待填写道具名」当成真道具建档
- 复现：ch_002 台账出现 `it_002 / 待填写道具名 / holder: 主角` 幽灵道具。
- 位置：`engine/ops.py::proposal_auto`，death/entity 分支都过滤了 `待填写角色名` 等占位值，唯独 item 分支的黑名单 `("待填写","示例","无")` 精确匹配不到「待填写道具名」。
- 影响：每跑一次带默认模板的 proposal，就往 items.json 塞一件幽灵道具。

---

## P2 · 一致性与体验

### BUG#7 `reconcile` 的「仍活跃待跨卷回收伏笔」统计的是全书而非本卷
- 位置：`engine/ops.py::reconcile_volume`，`active_in_vol = [l for l in lines.values() if status=="active"]` 完全没按卷过滤（变量名却叫 `_in_vol`），与紧邻的 `resolved_in_vol`（已正确按 `vol_ch_set` 过滤）口径不一致。
- 影响：多卷之后，每卷对账报告都会把全书所有活跃伏笔重复列一遍。

### BUG#10 死者登场阻断错误被重复报告两次
- 复现：`check ch_XXX`，某章 present_characters 含已阵亡角色（且 id 与 name 都填了）→ 同一条阻断错误打印两遍。
- 位置：`engine/id_tracker.py` 死者登场守卫，「按 ID 检查」命中后未短路，紧接着的「按 Name 检查」再命中一次。
- 影响：体检报告噪声，错误计数虚高。

### BUG#8 `cockpit` 恩怨行只打印 target_char，丢失发起方
- 位置：`engine/cockpit.py` 第 173 行。实测显示「涉及: `p_001`」，而这笔恩怨其实是 p_002 → p_001。`pack.py` 与 `ops.py` 的 dossier 都是双向打印，只有 cockpit 缺。

### BUG#9 地点层级匹配过宽，不同地点被合并进同一个 loc
- 复现：`/tmp/tb2` 中 location 依次为「站台」「站台·地下三层」「北环站台」，places.json 始终只有 `loc_001 站台`，visited_chapters 吃掉全部 5 章。
- 位置：`engine/state.py` 2.5 节 `pname in location_str or location_str in pname` 双向包含判定。
- 说明：这是「防空壳地点暴增」的有意设计，但双向包含会把「北环站台」这种真·不同地点误并。属于设计权衡，记录为待确认项而非必改。

### 观察项（非 bug，供记录）
- `check` 对 `未知人甲` 这类中文名当作人物 ID 写入 persons.json 不报错（`id list` 显示 `未知人甲 : （空名）`）。state 侧有「名→ID 二次解析」，但解析不到时会按原值自注册，check 的 ID 格式校验只拦 `p_` 开头的非法格式，中文 ID 直接放行。
- `ledger.delta` 非整数（如 `+一千`）已正确降级为 warning 并忽略，行为符合「宽容自愈」。
- 空正文阻断、死者登场阻断、充能透支事务预检（零写盘）、槽位闸门、sync 幂等跳过、snapshot 回滚对齐清除、export 只导已封存章 —— 均实测通过。


---

## 第 2 轮：修复与回归结果（v4.3.2）

| 编号 | 级别 | 状态 | 修复位置 |
|---|---|---|---|
| BUG#1 充能重放重复扣减 | P0 | ✅ 已修 | `engine/state.py` 应用侧 + 事务预检侧改为「本章历史 delta 冲销」的净额口径 |
| BUG#6 无 id debts 重放膨胀 | P0 | ✅ 已修 | `engine/state.py` 缺省 id 由序号改为 `章+源+标+类型` 的 sha1 稳定派生键 `DEBT-AUTO-xxxxxxxx` |
| BUG#2 伏笔 type 恒为 GUN | P0 | ✅ 已修 | `engine/state.py` 优先取细纲显式 `type`，否则按 ID 前缀推断 GUN/KNO/MIS |
| BUG#5 audit 覆盖 Auditor 成果 | P0 | ✅ 已修 | `engine/ops.py` 新增 `_audit_has_author_content` 守卫；默认拒覆盖并回执，`audit --force` 才重置且留 `.bak` |
| BUG#4 首登场角色泄密漏判 | P1 | ✅ 已修 | `engine/probes.py` 的 `name_by_id` 合并细纲 `present_characters` 的 id→name |
| BUG#3 占位道具被建档 | P1 | ✅ 已修 | `engine/ops.py` 三处黑名单统一为 `_is_placeholder_value`（前缀/关键词判定） |
| BUG#7 reconcile 活跃伏笔未按卷过滤 | P2 | ✅ 已修 | `engine/ops.py` 拆为「本卷埋设活跃」+「前卷遗留跨卷」两段，逾期判定仍覆盖全量 |
| BUG#8 cockpit 恩怨丢失发起方 | P2 | ✅ 已修 | `engine/cockpit.py` 改为 `源 ➔ 标` 双向展示 |
| BUG#10 死者登场错误重复报告 | P2 | ✅ 已修 | `engine/id_tracker.py` ID 命中后短路，不再走姓名二次命中 |
| BUG#9 地点包含匹配吞并子地点 | P2 | ⏸️ 记录不改 | 属「防空壳地点暴增」的有意权衡 |

### 回归测试
新增 `tests/regression_test.py`：在临时目录从 `init` 起重建一本 4 章测试书，跑通
beats → pack → audit → finalize → proposal → sync → reconcile/rollup/export → cockpit → snapshot 全链路，
并对上述每个缺陷做定点断言。

```
$ python3 tests/regression_test.py
通过 53 项 ｜ 失败 0 项
```

覆盖范围：全链路产物、幂等与 `--force` 重放安全（充能/恩怨/资金池/共现矩阵）、
Auditor 成果保护与配方闭环、四类硬阻断（空正文 / 未填槽位 / chapter_id 不一致 / 死者登场+充能透支零写盘）、
卷末对账与导出过滤、检索与大盘、快照回滚对齐。

### 存量数据自愈验证
在真实测试书 `workspace/testbook`（4 章成稿）上复测：`check` 0 error；
`sync --force` 重放 ch_003 两次后 `it_001.charges` 稳定在 0、debts 稳定 3 条；
历史上被错记为 GUN 的 `KNO-001` 在重新 sync 后自动纠正为 KNO。


---

# 第 3 轮：`--refresh`、损坏隔离、死亡章判定（v4.3.2 续）

延续第 1 轮遗留的三项待验证面（`sync --refresh`、JSON 损坏隔离 exit 4），又挖出 5 个缺陷，其中 1 个 P0。

### BUG#13（P0）损坏隔离后，下一条命令静默以空表放行 —— 台账无声蒸发
- 复现：`echo '{"it_001": {broken' > state/items.json`；`id list item` → exit 4（正确）；**再跑同一条命令 → exit 0，台账显示为空**；`id next item` 从 it_003 退回 it_001。
- 根因：`engine/state.py::_load_json` 隔离时把坏表 rename 成 `*.corrupt-<ts>`，原路径随之消失；下次调用只看到「文件不存在」，走合法首跑分支返回空表。
- 影响：与该函数 docstring 明文承诺的「绝不静默以空表继续」**正相反**。发号器会重发已占 ID，随后任一次 `_save_json` 会把空表落盘，真实台账被永久覆盖。AGENTS.md「遇 4 必须停机」的铁律也被绕过——重试一次就"好了"，恰恰是最危险的假象。
- 修复：`_load_json` 在「文件缺失」分支增加隔离残骸探测，只要同目录存在该表的 `.corrupt-*` 且正主未恢复，持续 RuntimeError（exit 4）直到人工处置。

### BUG#14（P1）`check` 把「正主缺席的隔离残骸」当历史遗迹，仅报 warning
- 根因：`engine/check.py` 对所有 `.corrupt-*` 一律 warning。
- 影响：台账正处蒸发态时体检仍可能打出 ✅。
- 修复：按正主是否已恢复二分——缺席 → error 阻断；已恢复 → 保留 warning。

### BUG#15（P1）死亡章判定漏识中文常用表述 + 取错 arc_history 条目
- 复现：《灰烬纪元》齐鸣(p_005) 于 ch_004 牺牲，`check` 常驻报错「已于第 ch_003 章阵亡，禁止在后续章节登场」，把他真正的牺牲章反诬为死者复活。
- 根因：`engine/state.py::get_death_chapter` 两处——① 关键词表只有「阵亡/身死/被斩杀…」，漏掉「死于」「牺牲」等最常见写法，整条 `为掩护沈决死于档案室火场` 不命中，回落到 `last_seen_ch`（ch_003）；② 命中后取首个条目，而 arc_history 实际为倒序，章号会取错。
- 影响：任何用自然中文描述死亡的书都会在牺牲当章被误判阻断，且错误信息指向错误章号，极难自查。
- 修复：扩充死亡语义词表至 17 个；改取命中项中**章号最大**者；未命中语义但已 deceased 时取 `last_seen_ch` 与 arc_history 最晚章的较晚者。
- 效果：`workspace/testbook` 体检由「1 条常驻阻断错误」变为 ✅ 0 error。

### BUG#11（P1）`--refresh` 不更新任何字数统计
- 复现：ch_002 正文从 418 字润色扩写到 976 字后 `sync --refresh` → `sync_log`/`timeline`/`synopsis`/`project.total_published_words` 全部仍是 418；cockpit 字数曲线、配额与导出统计集体失真。
- 根因：`engine/ops.py::sync_chapter` 的 refresh 分支只改 `final_sha1`。
- 说明：字数是正文派生事实而非细纲增量，刷新它不违反「不重复入账」语义；而字数恰恰是文笔修订最常变动的量。
- 修复：refresh 分支同步刷新四处字数统计，台账增量仍不重放。

### BUG#12（P2）对从未同步过的章使用 `--refresh` 会静默穿透成完整入账
- 根因：refresh 分支条件为 `if refresh and prev`，`prev` 为空时直接落到正常入账主流程。
- 影响：与「只刷新指纹、不入账」的承诺相反，而这通常是用户误加参数。
- 修复：`refresh and not prev` 时 GuardError 阻断，提示改用不带 `--refresh` 的首次入账。

### 回归
`tests/regression_test.py` 扩充至 **72 项断言全通过**，新增「--refresh 语义」与「损坏隔离与死亡章判定」两个测试段。


---

# 第 4 轮：文档与代码契约一致性（v4.3.2 定版）

逐条执行文档（AGENTS.md / README.md / engine/README.md / templates/README.md / 10 份 `.agents/skills/*/SKILL.md`）中出现的全部 37 条命令行示例，并核验手册对引擎行为的事实性承诺。

### 命令契约核验结果
除下述两项外，文档承诺的命令、参数与退出码均与实现一致；`finalize` 的配方解析对多行三反引号与行内紧凑两种格式（含 `原句/原文/修改后/替换为` 中英文别名、加粗、中文冒号）均可正确识别，与 auditor 手册规范吻合。

### BUG#16（P2）`milestone add --target-ch` 只收裸数字，与全系统章号形态冲突
- 复现：`milestone add --title X --target-ch ch_010` → exit 2「invalid int value」。
- 根因：`engine/cli.py` 该参数 `type=int`。而全系统（细纲 `chapter_id`、`check`、`cruise --until`、`trace`）统一使用 `ch_XXX`，architect 手册示例又写作 `--target-ch 5`，两种形态混用。
- 修复：新增 `_chapter_num_arg` 解析钩子，`ch_010` / `ch010` / `10` 均接受并归一为整数存储；非法值仍报 exit 2 且给出可读提示。

### BUG#17（P1）同章「首次登场 + 当场损毁」的道具丢失 destroyed 状态
- 复现：按 auditor 手册规范分行登记 `- [新登场] 类型: item ｜ 名称: 铜哨` 与 `- [道具变动] 名称: 铜哨 ｜ 状态: destroyed`，`proposal auto` 后铜哨以 `active` 入账。
- 根因：`engine/ops.py::proposal_auto` 处理 `emergent_items` 时，若 `new_entities` 已存在同名条目便整条跳过，后续的状态/持有人变动被静默丢弃。
- 影响：直接违背手册「道具损毁必抓」的承诺，且这恰是最常见的组合（战斗中掉落又当场碎裂）。
- 修复：改为补写而非跳过——已存在同名道具时合并 status / holder / summary。

### 其它一致性核查（通过）
- 版本号唯一真值源：`engine/__init__.__version__` 已随本轮变更升至 **4.3.2**，`--version` 与 cockpit 横幅均动态引用，符合 engine/README 不变量 7。
- 八表口径：README 的「人物/道具/势力/地点/伏笔/恩怨/资金池/时间线」与 engine/README 的 `persons/items/factions/places/lines/locked/ledger/current` 表述角度不同但均可自洽，实际落盘 15 张表 + 2 索引，无缺失。
- 退出码铁律 0/1/2/3/4 与实现一致（本轮 BUG#13 修复后，exit 4 不再可被「重试一次」绕过）。

### 最终回归
```
$ python3 tests/regression_test.py
通过 78 项 ｜ 失败 0 项
```
`workspace/testbook`（《灰烬纪元》4 章成稿）全书体检 ✅ 0 error。


---

# 第 5 轮：长程无人值守巡航与跨卷压测（v4.3.2）

构造 16 章连续测试书（每章：1 新人物 + 1 新地点 + 1 埋伏笔 + 隔 2 章回收 + 1 恩怨 + 1 锁定事实 + 1 充能消耗 + 1 笔资金流水），跨 vol_01/vol_02 两卷，压测 `cruise` 全部路径。

### BUG#18（P0）刹车章仍污染台账 —— 事务预检被 new_entities 抢跑
- 复现：`cruise` 连巡至 ch_016 因「长明灯充能耗尽」正确刹车，但事后 `persons.json` 里多出 **p_017「守关人16」**、`places.json` 多出 **loc_016** —— 一个从未出现在任何已封存章的幽灵人物，且占掉了 ID 水位。
- 根因：`engine/state.py::apply_fine_outline_delta` 第 0 节「同步本章新登场实体」在函数开头就 `_save_json` 落盘四张表，而死者登场/充能透支的**事务预检在第 2 节才执行**。预检 raise 后无人回滚已落盘的新实体。
- 影响：直接违背 engine/README 设计不变量「`apply_state_deltas` 事务预检先于任何写盘」。无人值守巡航每刹车一次就留下一批幽灵实体，且因为 `check` 不校验"实体是否出现在已封存章"，这些脏数据可以长期潜伏；后续 ID 发号水位也被顶高。这是继 BUG#13 之后第二个"看起来正确刹车、实际已写脏"的隐蔽缺陷。
- 修复：新实体改为只在内存态构建，推迟到预检通过后统一落盘；预检失败时随内存一并丢弃，实现真正的零污染。

### 长程台账零漂移验证（10 章连巡，16 项指标逐一核对）
| 指标 | 期望 | 实际 |
|---|---|---|
| 道具充能（初始 15，每章 -1） | 5 | ✅ 5 |
| 资金池（每章 -10） | -100 | ✅ -100 |
| 人物 / 地点 / 恩怨 / 锁定事实 | 11 / 10 / 10 / 10 | ✅ 全中 |
| 伏笔（10 埋，隔 2 章回收） | 10 条，8 resolved，active=GUN-009/010 | ✅ 全中 |
| 共现矩阵 | 10 对，各 1 次（无虚增） | ✅ |
| 主角 arc_history | 10 条，按章去重无重复 | ✅ |
| timeline / sync_log / 总字数 | 10 / 10 / 1830 | ✅ |

**重复巡航幂等性**：第二次 `cruise --once` 后，除 `rollup_vol_01.json` 的 `archived_at` 时间戳外，**37 张状态表逐字节完全不变**。

### 巡航控制面验证（全部通过）
- `cruise_max_chapters` 批次上限与 `--max-chapters` 命令行覆盖均正确钳制；
- `--until ch_008` 终点钳制正确；
- `cruise_human_gate=2` 阻塞模式：连巡 2 章后真实挂起等待 `.cruise_gate` 哨兵，投放后自动续航并**消费（删除）哨兵**，卷末刹车链完整执行，exit 0；
- 等待作者产出超时：6s 后刹车，批次报告标记 `status: timeout`，**exit 1**（留痕，非静默成功）；
- 跨卷续航：`cruise ch_011` 在 project.json 仍指向 vol_01 时，正确按 outlines 实际归属定位到 vol_02，未误触发旧卷卷末刹车；
- 刹车章遗留的孤儿 `final/ch_016.md` 未进 sync_log，`export` 正确跳过，成书含跨卷 15 章。

### 回归
`tests/regression_test.py` 扩充至 **99 项断言全通过**（新增巡航段 21 项），并将测试书生成器固化为 `tests/_cruise_fixture.py`。


---

# 第 6 轮：Stage 4C 演进平账路径（novel-evolution）专项审查

用户提出的关键疑问：作者中途提复杂改动/新想法、与既有逻辑冲突时，evolution 平账涉及大量数据库操作，它到底跑什么命令、靠不靠得住。

## 首要结论：evolution 没有任何"平账命令"

通读 `.agents/skills/evolution/SKILL.md` 后确认，它的全部机器能力只有 **4 条只读/备份命令**：
`simulate impact`（风险测算）、`snapshot create/rollback`（备份回滚）、`check`（验收）、`ask`（检索，≤3 次）。

**真正的台账改动全靠手工编辑 `state/*.json`**（手册明示用 `replace_file_content`/`write_to_file`）。也就是说整条演进路径上只有两道机械防线：**事前靠 `simulate impact` 估风险，事后靠 `check` 验收**。这两者一旦失准，作者的复杂改动就是在无保护状态下动刀。实测发现：**两道防线当时都是漏的**。

### BUG#19（P0）`simulate impact` 用物理 ID 测算几乎全盲，且漏扫六张表
- 复现（同一个角色，两种写法结论相反）：
  - `simulate impact --entity 齐鸣` → **HIGH**，命中 LOCK-002；
  - `simulate impact --entity p_005` → **LOW（低风险·局部微创修改）**，零波及。
- 根因：旧实现只做**字面子串匹配**，扫 timeline/synopsis/lines/locked 四张表。而 `timeline.present_characters` 存的是人名、`locked.fact` 里写的也是人名，于是 ID 形态全部落空。
- 致命性：evolution 手册的命令示例恰恰写作 `--entity p_001`。**照着手册跑，会对一个触碰法定事实的高危改动拿到"低风险"的假绿灯**，然后直接动刀。这是 Stage 4C 唯一的事前闸门。
- 附带漏报：完全未扫 `debts`/`relations`/`items`/`places`/`entity_timeline`/`milestones` 六张表——而恩怨链与关系网正是改人设、改生死时最先崩的地方；手册还明文要求核对"是否颠覆既定里程碑"，旧版从未读过该表。
- 修复：先用既有的 `_resolve_person_id`/`_resolve_item_id` 把实体归一到物理 ID，再以「ID+名称+别名」别名集合扫描**全部十个维度**；报告回显归一后的 `姓名 (ID ｜ 类型)`；支持 person/item/line/place 四类 ID 直查；解析不到时显式告警「此结论仅供参考」，不再静默给 LOW。
- 修复后同一案例：`p_005` 与 `齐鸣` 输出完全一致，且新揭示出旧版看不见的 **2 条恩怨链 + 1 条关系网**（`DEBT-003 齐鸣之死的血债` 等）——这正是改写齐鸣生死时最会崩的部分。

### BUG#20（P0）`check` 对台账内部交叉引用零设防，evolution 验收形同虚设
- 复现：向一本健康的书注入 5 类典型手改破绽，`check` **全部 0 error 放行**：
  1. 改 `life_status: alive` 复活角色，但 `arc_history` 仍留着死亡记录；
  2. 删掉角色 `p_003`，但 `relations`/`debts` 里仍引用它；
  3. 伏笔改 `status: resolved` 却没填 `resolved_ch`；
  4. 道具 `holder` 指向不存在的 `p_999`；
  5. 恩怨双方指向幽灵 ID。
- 根因：`check` 只校验「细纲 ➔ 台账」单向引用，从不校验台账**内部**自洽。
- 影响：evolution 唯一的验收闸门失效，手改平账没有任何机械兜底；上述脏数据会长期潜伏，直到某次 pack/sync 才以诡异形式爆发。
- 修复：新增 **3.4 节「台账内部交叉引用完整性巡检」**，覆盖 6 类校验（生死自洽 / 道具持有者 / 恩怨双方 / 关系网双方 / 伏笔闭环字段 / 锁定事实指向章）。人物引用解析接受 ID、姓名、别名及引擎内置泛指（`主角`），避免误报。
- 配套：坏表导致巡检不可用时降级为 warning 而非上抛 exit 4，保证作者能看到完整体检报告（坏表本身已在 2.5 节以 error 报告）。

### BUG#15 补遗：死亡语义词表漏「病故」等非暴力死亡写法
回归测试用「病故于旧货店」做样本时暴露：原词表偏战斗向（阵亡/被斩杀/战死…），日常与都市题材常见的**病故/病逝/猝死/离世/去世/咽了气/殉职**等整条漏判。已补入 17 个词。

同时修正一处**架构隐患**：新增的 3.4 节我最初内联复制了一份死亡词表，这正是 BUG#15 的成因（两处词表漂移）。已改为统一引用 `state.py::_DEATH_KEYWORDS` 单一真值源。

### 完整演进工作流实测（齐鸣改假死）
| 步骤 | 结果 |
|---|---|
| 1. `simulate impact --entity p_005` | ✅ HIGH，列出锁定事实 + 2 恩怨链 + 1 关系网 |
| 2. `snapshot create pre_evolution_齐鸣假死` | ✅ 快照建立 |
| 3. 半吊子手术（只改 `life_status`） | — |
| 4. `check` 验收 | ✅ **准确拦截**，指出弧光矛盾并给出补救路径 |
| 5. 按指引补全（改写 arc_history + 同步 LOCK-002） | ✅ `check` 0 errors 放行 |
| 6. `snapshot rollback` | ✅ `life_status`、`LOCK-002` 全部完整复原 |

### 手册同步
已更新 `.agents/skills/evolution/SKILL.md`：补充**测算报告读法**（ID 与姓名等价、十维波及面、未解析告警不可信）与**台账平账自检清单 v4.3.2**（五类必须成对修改的漏项），使手册与新的引擎能力对齐。

### 回归
`tests/regression_test.py` 扩至 **116 项断言全通过**（新增演进段 17 项）。

---

## 第 7 轮：细纲字段契约 / 空壳命令 / 测算深度 / Librarian 探测盲区

### BUG#21 【P0 已修已验】细纲 state_deltas 字段契约三方不一致，台账静默漏账

- **现象**：引擎 `engine/state.py` 实际消费 `state_deltas` 的 5 个子块
  （character_status / debts / items / ledger / relation_deltas），但
  ① `beats` 脚手架把 `items` 与 `ledger` 两整块**默认注释掉**；
  ② screenwriter 手册**只点名 5 个顶层字段**，对 `items` / `ledger` /
  `relation_deltas` / `narrative_spine` 提及次数为 **0**。
- **后果**：编剧在细纲与正文里写足「消耗 1 次充能、花光 500 灵石」，
  Frontmatter 却未声明 → `charges` 仍为 3、`ledger.pools` 仍为 `{}`，
  而 `sync` 成功、`check` **0 errors**，全链路零告警（`/tmp/sw2` 复现）。
- **修复**：① 手册补全四个子块说明（标注 items/ledger 默认注释需手动启用）、
  补 `relation_deltas` 条目、新增「🔴 正文与台账同源铁律 v4.3.2」7 行对照表；
  ② `engine/state.py` 新增 **10.5 节「细纲正文 ⇄ state_deltas 声明漂移探针」**，
  剥离 HTML 注释后按关键词比对 items/ledger/relations 三类，命中且未声明则 warning
  （只提醒，绝不猜数改账）。
- **验证**：`/tmp/sw3` 正确报出 items 与 ledger 两条告警；已正确声明的
  testbook ch_003 重跑 sync 零误报。

### BUG#22 【P2 已修】`style` 空壳命令暴露谎称有效的 `--last` 参数

- **现象**：`style` 自 v4.2 起退役为说明性命令（语义评估交由 Stage 3A/4A），
  `engine/cli.py` 分支只 print 三行后 return 0，**不读任何文件**；
  但 CLI 仍定义 `--last N`（默认 10）且**完全忽略**——传 `--last 3` 与不传输出逐字节相同。
- **定性**：退役本身是设计决策，非缺陷；缺陷在于保留了一个按参数语义会让调用方
  误以为「已分析最近 N 章」的无效开关。
- **修复**：help 文本标注 `[已失效]`，命令首行显式声明「不读取任何章节、不产出统计数据」，
  显式传入非默认 `--last` 时打印忽略告警，并给出应改派 Stage 3A/4A 的指引。

### BUG#23 【P1 已修已验】`simulate impact` 漏计活跃伏笔的预定兑现章 `target_ch`

- **现象**：波及面只计 `planted_ch` 与 `resolved_ch`。实测 GUN-002 预定兑现于 **ch_012**，
  测算却只报埋设章 ch_003。
- **后果**：活跃伏笔的 target_ch 是**未来已排产的剧情承诺**，改动该伏笔必然波及那一章。
  Stage 4C (Evolution) 据此低估改动半径，漏改 ch_012 的规划。
- **修复**：`engine/ops.py` 对 `status == "active"` 且有 `target_ch` 的伏笔计入波及章节，
  并在清单中标注 `⏳预定兑现于 ch_XXX`。
- **验证**：GUN-002 波及面 1 → 2（ch_003, ch_012）；p_001 波及面正确扩展至 5 章。

### BUG#24 【P0 已修已验】Librarian 对自己职责范围内的冲突全盲

- **现象**：Stage 4D (novel-librarian) 手册明列「生死矛盾」「法宝归属」「因果断裂」
  属 Level 2 必须上报，但给它的准跑命令只有 `evidence candidates` 与 `reconcile`，
  且**明令禁止运行 `check`**（"体检由主控统一执行"）。
- **复现**（`/tmp/lib`）：注入「齐鸣 life_status 改回 alive（与 ch_004 死亡弧光互斥）」
  与「it_001.holder 指向幽灵 p_999」两处冲突后——
  `evidence candidates` 报 **"✅ 台账完备"**，`reconcile` 报告**只字未提**；
  而被禁用的 `check` 两条都抓得一清二楚。
- **后果**：librarian 根本无从发现它被要求上报的问题，**Level 2 → Stage 4C 的派发链在源头就断了**。
  每 10 章与卷末的长程巡检成为走过场。
- **修复**：
  ① `engine/check.py` 将 3.4 节巡检抽取为可复用的 `scan_ledger_integrity(workspace)`，
     `check` 与 `reconcile` 共用同一实现（遵循"语义词表/阈值单一真值源"铁律，禁止复制）；
  ② `engine/ops.py` 的卷末对账报告新增 **第五节「🩺 台账自洽体检（Level 2 靶点预筛）」**；
  ③ librarian 手册步骤 1 新增必读提示，说明该节是它唯一的机械冲突探测器，
     列出条目须逐条按 Level 2 靶点卡片上报，并放开回读自产 reconcile 报告的权限。
- **验证**：`/tmp/lib` 的 reconcile 报告现正确列出 2 项并标注 Level 2 处置路径；
  干净的 `workspace/testbook` 显示 `✅ 台账内部交叉引用自洽`；`check` 行为不变（仍报 2 项）。
- **注意**：`scan_ledger_integrity` 对坏表**上抛 RuntimeError**，由两个调用方各自降级
  （check 记 warning 避免 exit 4 截断报告；reconcile 记一行说明），不得在函数内自行吞掉。

**回归**：`python3 tests/regression_test.py` → **116 项全通过 / 0 失败**。
