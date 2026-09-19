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
