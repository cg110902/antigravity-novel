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

### BUG#25 【P1 已修已验】里程碑零校验：可排产「已过去的章」与第 0 章，且永不告警

- **背景**：延续 BUG#24 的排查模式（职责要求 vs 准跑命令实际能力），
  对 Stage 0B/0E (Architect) 唯一的写命令 `milestone add` 做输入压测。
- **现象**：
  - `--target-ch 0`、`--target-ch 1`（全书已推进至 ch_004）、`--target-ch 99999`、
    以及与现存里程碑完全重复的排产，**全部 exit=0 静默落盘**（仅 `-5` 被 argparse 挡下）；
  - 消费侧同样零设防：`milestones.json` 在 `engine/check.py` 全文**只在坏表清单里出现过一次**，
    无任何内容校验。伏笔有 3.2 节「超期未决」告警，里程碑却没有对称逻辑。
- **后果**：目标章被剧情甩在身后的里程碑，在 cockpit 里**永远显示「⏳ 待达成」**，
  主控据此以为主线仍在轨，实为一张永不兑现的空头支票。
- **修复**：
  ① `engine/ops.py` `milestone_add` 入口校验——`target_ch` 非 `>=1` 整数，
     或 `<=` 当前推进章次，一律 `GuardError` 拦截（exit 1），并指引改用 `milestone achieve`；
  ② `engine/check.py` 新增 **3.3 节「里程碑时钟超期巡检」**，与 3.2 节伏笔时钟对称，
     对未达成且目标章已被超越的里程碑报 warning。
- **验证**：`/tmp/ag2` 中 `--target-ch 20` 通过、`--target-ch 1` 与 `0` 均被拦截（exit 1）；
  `/tmp/ag` 存量脏数据被 check 正确报出 ms_002/ms_003 两条超期告警。

### 第 7 轮第 4 项：其余 Agent 全量扫描结论

按 BUG#24 的模式逐份核对 10 份手册的「职责要求 vs 准跑命令白名单实际能力」：

| Agent | 准跑命令 | 结论 |
|---|---|---|
| director | 全量 16 条（S1–S5 + Scenario E） | ✅ 卷末三连 reconcile/rollup/export 实测均 exit 0 |
| architect | `milestone add`、`check`、`init` | ⚠️ 检出 **BUG#25**（已修） |
| evolution | `simulate impact`/`snapshot`/`check`/`ask` | ✅ 第 6 轮已验；本轮修 **BUG#23** 补全 target_ch 波及面 |
| librarian | `evidence candidates`/`reconcile`/`ask` | ⚠️ 检出 **BUG#24**（已修） |
| screenwriter | 无（零 CLI） | ⚠️ 检出 **BUG#21**（已修） |
| auditor / dehydrator / drafter / tuner / profiler | 无（纯文本工序） | ✅ 无命令即无能力缺口 |

**手稿链路一致性**：drafter(`raw/ch_XXX_v1.md`) ➔ dehydrator(`_v2.md`) ➔ tuner(`_v3.md`)
➔ auditor(读 `_v3.md` + `log/audit/ch_XXX.md`) ➔ finalize(`final/`)，
五份手册声称的路径与引擎 `evidence_candidates` 的回溯查找顺序完全一致，无偏差。

**回归**：`python3 tests/regression_test.py` → **116 项全通过 / 0 失败**。

### BUG#26 【P3 已修】`templates/README.md` 残留不存在的 `style_*` 配置旋钮

- **现象**：README 第 44 行称 `project.json.engine` 存旋钮
  `token_cap`/`cruise_max_chapters`/`default_pool`/`style_*`，但 `style_*` 在
  `engine/` 全文**零命中**——系 style 命令于 v4.2 退役（见 BUG#22）后的文档残留。
  `config guide` 实际输出 6 个旋钮，其中 `cruise_human_gate`/`cruise_wait_timeout`
  反而未被 README 列出。
- **修复**：改为与 `DEFAULT_CONFIG` 一致的真实清单，删除 `style_*` 并注明退役原因。

### BUG#27 【P1 已修已验】文档九处宣称「严格枚举」，引擎零校验

- **现象**：`templates/README.md` 对 `type`/`role`/`status`/`life_status`/`attitude`
  反复标注「**严格枚举**」，其中 attitude 更明令「严禁用 `disposition`」。
  实测把 p_003 四个字段分别改为 `半死不活` / `disposition` / `路人甲` / `摸鱼中`
  后，`check` 依旧 **✅ 0 errors 放行**，`schema.py` 的 dataclass 默认值形同虚设。
- **后果**（不止于文档失信）：`engine/probes.py:376` 的死亡探针按
  `life in ("deceased","dead")` **精确匹配**消费该字段——任何拼写变体
  （`已故` / `Deceased ` / `dead人`）都会让已故角色被判定为在世，
  死亡探针继续对其触发误报；cockpit 与 id_tracker 亦照原样展示非法值。
- **修复**：`engine/check.py` 新增 **3.2.5 节「强类型枚举白名单巡检」**，
  覆盖实体四表（persons/items/factions/places）的五个法定枚举字段。
  - **定级为 warning 而非 error**：存量书可能已有自造值，硬阻断会锁死工程；
    但必须让作者看见并给出法定枚举以便收敛。
  - 对 `life_status` 额外附加死亡探针失效警示，对 `disposition` 附加 README 禁令提示。
- **验证**：`/tmp/tpl` 四处非法值全部精准命中并给出白名单；
  `workspace/testbook` 干净基线**零误报**；`templates/` 下 8 张卡片实测全部使用合法枚举。

### 第 7 轮第 5 项：模板字段全量核对结论

| 核对项 | 结论 |
|---|---|
| `project.json` 8 个顶层键 | ✅ 与引擎消费一致 |
| `scope.target_words` / `target_volumes` / `chapters_per_volume` | ✅ **非缺陷**：引擎零读取，但 README 已明确定性为「写手指引而非硬性代码拦截」，文实相符 |
| `engine.*` 旋钮清单 | ⚠️ **BUG#26**（已修） |
| 实体四表强类型枚举 | ⚠️ **BUG#27**（已修） |
| `templates/` 8 张卡片的枚举取值 | ✅ 全部合法 |
| `beats.md` 细纲字段契约 | ✅ 第 7 轮第 1 项已核（见 BUG#21），模板侧 14 字段与脚手架产出完全一致 |

**回归**：`python3 tests/regression_test.py` → **116 项全通过 / 0 失败**。

### BUG#28 【P0 已修已验】章节已定稿却从未合账，全链路零告警

- **排查路径**：第 6 项源码审查中考察 sync 的**事务性**。单章 sync 依序写 **14 张表**，
  每张各自原子（`_save_json` = `tempfile.mkstemp` + `fsync` + `os.replace`，
  失败会清理 tmp 并 re-raise，实现正确且全引擎唯一），但**整体无事务**。
- **半提交复现**：把 `state/debts.json` 替换为同名目录，令第 4.5 节的 `os.replace`
  单点失败。结果前序的 items/ledger **已落盘**（`charges` 7→6、`灵石` -10→-20），
  而末尾的 `sync_log` 未记录该章 —— 确为半提交，`sync` 正确返回 **exit 4**。
  - ✅ **风险被兜住**：sync 幂等性生效，重跑 `sync ch_003` 未二次扣账（items/ledger 值不变）。
    故半提交本身**不单独立为缺陷**。
- **真正的缺口**：更普遍的一类是章节已定稿（`final/ch_XXX.md` 存在）却从未合账
  （`sync_log` 无该章）。实测 ch_002 定稿落盘后未合账，`check` **完全无感**——
  此前 `sync_log.json` 在 `engine/check.py` 全文**只出现在坏表清单里**，零对账逻辑。
  整章剧情的人物/道具/伏笔/资金/恩怨变更永久遗失，且体检报 0 errors。
- **修复**：`engine/check.py` 新增 **3.2.6 节「定稿 ⇄ 合账对账巡检」**，
  遍历各卷 `final/ch_*.md` 与 `sync_log` 取差集，逐章报 warning 并给出补合账命令，
  同时说明 sync 幂等、重跑安全。
- **验证**：ch_002 被精准命中；补跑 `sync ch_002` 后告警自动消失；
  `workspace/testbook` 干净基线零误报。

### 第 7 轮第 6 项：源码审查其他结论

| 核查项 | 结论 |
|---|---|
| `_save_json` 原子性 | ✅ tmp+fsync+`os.replace`，失败清理并 re-raise；全引擎**唯一实现**，无副本漂移 |
| 24 处 `except: pass` | ✅ 逐处核对均为解析兜底/可选字段容错，**未发现吞掉写盘失败**的情形 |
| sync 多表事务性 | ⚠️ 无跨表事务，但**幂等性兜住重跑**；衍生的对账缺口已由 BUG#28 补齐 |
| 非 JSON 写盘（`write_text` ×15） | ✅ 单文件写入，失败即上抛，无静默截断风险 |
| 异常退出码 | ✅ 写盘失败正确归类 exit 4（未预期异常），与 AGENTS.md 退出码铁律一致 |

**回归**：`python3 tests/regression_test.py` → **116 项全通过 / 0 失败**。

---

## 第 7 轮第 7 项：逻辑覆盖清册 + 全新书实战（《灯下不照》· 古代悬疑）

产出 `COVERAGE.md`：盘点 **26 顶层命令 / 42 个可执行组合、10 处 GuardError 硬阻断、
check 7 节巡检、4 类正文探针、14 表合账顺序**，逐条标注是否已被实战验证，
未验证项即测试死角。据此新建工作区 `workspace/lantern/` 做全流程实战
（刻意选古代悬疑，与 testbook 的都市异能异题材，顺带验证引擎题材中立性）。

### BUG#29 【P1 已修已验】0C 门禁「零槽位」在设计上无法达成

- **现象**：`_scan_unfilled_slots` 用裸正则 `\{\{slot:` 计数，把**反引号代码跨度内**
  的 `{{slot:...}}` 也算作未填槽位。而 `templates/outlines/volume_outline.md` 的
  「卷末判定契约」条款正文里就写着 `` `{{slot:...}}` ``（那是在**描述语法本身**）。
- **后果**：每本新书 `init` 后都凭空背一个**永远消不掉**的槽位，
  Stage 0C「全部填实」门禁在设计上就不可能达成。实战中填完全书设定后
  仍顽固显示「未填占位符 ×1」。
- **修复**：计数前先用 `_INLINE_CODE` 剥离行内代码跨度。
- **验证**：《灯下不照》填完设定后 check **首次真正达成 0 errors 且零槽位**；
  追加真槽位到 bible 后仍被精准捕获，未放水。

### BUG#30 【P0 已修已验】槽位闸门缺位，章节可卡死在「已定稿但合不了账」

- **现象**：细纲残留 `{{slot:}}` 的闸门**只存在于 `sync`**（`ops.py` 第 1066 行），
  `finalize` 完全不读细纲。实测 ch_002 细纲含 **41 处**未填槽位，
  `finalize` 照样 **exit 0** 把正文写进 `final/`，随后 `sync` 永远 **exit 1** 拒绝入账。
- **后果**：章节卡死在「正文已落盘、台账永远缺这一章」的状态。更糟的是
  director 的 S5 短路链 `finalize && proposal auto && sync` 会在**第三步**才炸，
  此时 `final/ch_XXX.md` 已生成，作者必须手工回删才能重来。
  （附带确认：本轮 BUG#28 新增的「定稿⇄合账」巡检**正确抓到了**这个死状态。）
- **修复**：把槽位闸门前移到 `finalize_chapter` 入口，未填细纲在第一步即被拦下，
  **不产生任何脏产物**。
- **验证**：ch_002 现 exit 1 且 `final/` 保持为空；已填实的 ch_001 定稿不受影响。

### 实战进度与已验收的死角

| 覆盖清册待验项 | 结果 |
|---|---|
| **G1** 重复 init 拦截 | ✅ exit 1 |
| **G2** 细纲 SSOT 覆盖防护 | ✅ 有内容拒覆盖 exit 1；`--force` 放行并自动 `.bak` |
| **G3** finalize 未填槽位拦截 | ⚠️ **原本缺失** → BUG#30，已修复验证 |
| **G4** finalize 空正文拦截 | ✅ exit 1 |
| **3.3** 地点残缺巡检 | ✅ 实战中真实触发（`atmosphere` 非法定字段，引擎要 `sensory_anchor`/`environment_rules`） |
| 0C 占位符门禁 | ⚠️ **设计缺陷** → BUG#29，已修复验证 |

**待续**：三大正文探针（认知盲区 / 称谓矩阵 / 物象落地）的人工违规压测、
跨卷换卷、幂等矩阵、低频命令组。细纲已刻意埋入 `blind_spots`（沈拂云不知裴砚身世、
裴砚不知崔敬亭已知其身世）与 `address_matrix`（裴砚→沈仵作、沈拂云→裴评事、
周伯→云丫头）作为探针靶标。

**回归**：`python3 tests/regression_test.py` → **116 项全通过 / 0 失败**。

### 三大正文探针实战压测（覆盖清册核心死角）

以《灯下不照》ch_001 手写 1027 字**合规基线正文**，再逐一注入违规样本对照。

| 探针 | 违规注入 | 结果 |
|---|---|---|
| 认知盲区防透视 | 让 p_003（沈拂云）本人说出自己的 blind_spot「裴砚是灯市案幸存孤儿」 | ✅ **精准命中**：识别说话人 p_003、关键词「幸存孤儿」、判定 error 级「本人对白泄密」 |
| 法定称谓矩阵 | 抹去「沈仵作」「裴评事」等法定称谓，改用「喂」「拂云」 | ✅ **双向命中**：裴砚→沈拂云 应称「沈仵作」；沈拂云→裴砚 应称「裴评事」 |
| 伏笔与道具物象落地 | 删光正文中全部「灯签」「银针」字样 | ⚠️ 道具抓到，**伏笔 GUN-001 漏报** → BUG#31 |

### BUG#31 【P1 已修已验】物象落地探针被通用词污染，伏笔漏写永远抓不到

- **现象**：探针把伏笔的 `name` 与 `desc` 的全部 bigram 混为一池，**命中任意一个即算落地**。
  但 `desc` 是一句自然语言，必然混入角色名与通用词。实测 GUN-001
  「死者右手的半枚灯签」切出 **24 个 token**，其中 `第七`/`七具`/`死者`/`裴砚`
  四个属无区分度通用词 —— 把正文里**全部「灯签」字样删光**后，探针仍因这四个词
  判定「已落地」而静默。
- **后果**：伏笔漏写正是本探针**唯一的职责**，却因这条捷径永远无法触发。
  desc 里只要出现任一在场角色名，该伏笔就此免检。
- **修复**（`engine/probes.py`）：
  ① `name`（伏笔的标志性物象）改为**主判据**，仅当 name 缺失时才用 desc 兜底；
  ② 新增噪音词表，剔除在场角色名及其 bigram（从 `persons_db` 动态构建，含 aliases）
     与 30 个通用词；`run_all_probes` 补传 `persons_db`；
  ③ **按 ID 前缀分流**：`KNO-`（知情差）与 `MIS-`（认知偏差）本质是角色脑内认知状态，
     靠内心戏承载、无字面意象，对其做字面匹配只会制造无法消除的噪音
     （实测合规正文写足了沈拂云的误判内心戏仍被判漏写），故跳过，
     交由 Stage 4A (Auditor) 语义评估；仅 `GUN-`（实体暗线/信物）参与字面核验。
- **验证**：违规样本正确报出 `[伏笔] GUN-001` + `[道具] it_002`；
  合规基线**零误报**；回归 116 项全绿。

**ch_001 实战合账结果**：字数 1027（区间 900~1600 内）；`it_002` 充能 6→5；
`lines` 落地 GUN-001/MIS-001；`relations` 生成 `p_001->p_003`；`timeline` 1 条。

### 实战续写 ch_002~ch_006（含死亡章）与探针二轮压测

写满 6 章共 5961 字，全链路 `beats new` → 填细纲 → 手写正文 → `finalize` → `check` → `sync`。
探针在真实写作中**主动逮到 4 处我自己写漏的疏忽**（ch_002 沈拂云漏称「崔大人」、
ch_004 声明 reveal GUN-002 却没写进正文 + 漏称「沈仵作」、ch_005 漏称「沈仵作」），
证明其在正常创作流程中确有实效，而非摆设。

**幂等矩阵**：同稿重复 `sync` 正确幂等跳过；`--force` 强制重放后比对 state/ 全表 SHA1，
仅 `sync_log` 时间戳变化，**业务表零漂移**（银针 5、关系 2 条、伏笔 4 条均无重复膨胀）。

**死亡登记链路（ch_006 周伯之死）三方一致**：`life_status=deceased`；
`arc_history` 记录 ch_006 弧光 `status_out=deceased`；`LOCK-001` 锁定既定事实。
**G10 死者防复活硬阻断**实测生效：让 p_004 在 ch_007 的 `present_characters` 登场，
sync 报「因果冲突阻断：角色 [周伯] (p_004) 已于第 ch_006 章阵亡」并拒绝入账。

### BUG#32 【P2 已修已验】称谓探针混淆「在场」与「被提及」

- **现象**：探针仅以「名字是否在正文出现」判定在场。ch_005 崔敬亭**全程未出场**，
  只是被裴砚与沈拂云在对话里提到（「崔通判说尸格不成立」），探针却要求
  「崔敬亭→沈拂云 应称沈仵作」落地——两人根本不在同一场景，该称谓无从发生。
- **修复**：以细纲 `present_characters` 为权威在场名单（`run_all_probes` 已算好
  `present_ids`，直接传入），只校验**双方均在场**的称谓对。
- **验证**：ch_005 的 3 条提醒降为 1 条真实疏漏，其余 2 条误报消除。

### BUG#33 【P2 已修已验】称谓探针对无台词角色误报

- **现象**：只要角色在场就要求其法定称谓落地，但重伤濒死、昏迷、被缚者本就说不出话。
  ch_006 周伯全程濒死（`status_in`「重伤·濒死」，只递出半页纸便断气），
  探针仍要求「周伯→裴砚 应称裴大人」「周伯→沈拂云 应称云丫头」。
  这类提醒**无法通过任何合理写法消除**，只会淹没真实疏漏。
- **修复**：仅对本章确有可归属对白的角色校验称谓。

### BUG#34 【P1 已修已验】对白说话人归属大面积错配

- **发现路径**：修 BUG#33 需要「谁有台词」，打印归属结果时发现**错得离谱**。
- **现象**：三个归属函数（`_find_after` 后置式、`_find_before` 前置式、
  `_find_after_loose` 兜底）都只要求姓名附近 **25/30 字窗口内任意位置**
  出现动词表中的字。汉语叙述里「说/道/回/答/笑」等字极常见，窗口一宽必然误命中：
  - `"周老。"`（裴砚在喊周伯）→ 因下一段「周伯的眼睛动了一下。他想**说**话」
    被归给**周伯**；
  - 沈拂云的台词因后续「"念珠。"裴砚**说**」落入窗口而被归给**裴砚**。
- **后果（远大于误报）**：对白归属是**认知泄露探针（error 级）的判定基础**。
  错配会同时制造**漏检**（真泄露归错人而静默放行）与**误报**
  （合法台词被判成本人泄密而阻断流水线）。
- **修复**：抽出 `_speech_verb_adjacent()`，要求言语动词**紧邻**姓名——
  取前 4 字窗口，既容纳「忽然笑了一声」「缓缓说道」这类副词前置的合法后置式，
  又排除跨句误命中；三个归属函数统一复用，归属不确定时宁可返回 None 交疑似级复核。
- **验证**：ch_006 全部误归属消除；**真泄露样本仍被精准捕获**
  （`/tmp/pb` 的「本人对白泄密」判定不变）；回归中 BUG#4「首登场角色泄密须判确认级」
  一度退化为疑似级，据此把邻接窗口从 2 字放宽到 4 字后复绿。

**6 章台账终态**：`check` **0 errors**；总字数 5961；银针 6→3；银两 50→47；
伏笔 5 条（MIS-001 已 resolved）；恩怨 3、关系 3、锁定 1；周伯 deceased。
**回归**：`python3 tests/regression_test.py` → **116 项全通过 / 0 失败**。

---

## BUG#35 【P3 已记录】export 与 sync 字数口径不一致
- **现象**：`workspace/lantern` 第一卷 14 章，`sync_log.json` 累计 12667 字，`export` 报 12570 字，差 97。
- **根因**：`sync` 的 `word_count` 统计整份 final 正文（含 `# 第N章 标题` 行）；`exporter.py:189` 在剥离标题行后重排目录，只统计 `body_lines`。两者共用 `_count_words` 但输入域不同。
- **影响**：不影响数据正确性，但「总字数」在 cockpit / reconcile / export 三处口径不一，对账时易被误判为漂移。
- **建议**：统一以正文体（不含标题）为准，或在 export 输出中标注口径。

## BUG#36 【P0 已修已验】snapshot rollback 接受工作区外任意 zip，导致全书删除 + 任意文件写入
- **现象**：`studio.py snapshot rollback /tmp/evil/payload.zip -w workspace/lantern` 执行成功。该 zip 仅含一个 `state.json`（内容 "PWNED"）。结果：
  1. 工作区 `state.json` 被攻击载荷覆盖；
  2. 解包后的「快照域全量对齐」逻辑把 bible/characters/outlines/state/manuscript/log 下**全部 84 个文件**判为「快照外未来文件」并删除——**整本书被清空**；
  3. 事后 `studio.py check` 仍报「✅ 体检通过 (0 errors)」（空工作区无数据可查），毫无预警。
  4. 相对路径 `../../../../tmp/evil/payload.zip` 同样生效。
- **实测损失**：`workspace/lantern` ch_007~ch_014 共 8 章正文、细纲与台账全部丢失（ch_001~006 靠 git 已提交版本恢复）。自动生成的 `pre_rollback` 快照因在第二次 PoC 后才建立，已无救援价值。
- **根因**（`engine/ops.py::snapshot_rollback`）：分支一 `if Path(name_or_file).exists() and endswith(".zip")` 无条件信任任意路径；分支二/三 `snap_dir / name_or_file` 未做边界归一化，`..` 可逃逸。已有的 zip-slip 防护只校验**解压目标**不越界，不校验**快照来源**，故完全绕过。
- **修复**（v4.3.3，三道安全带）：
  1. `_inside_snapdir()`：`cand.resolve().parent` 必须等于 `snap_dir.resolve()`，三个分支全部套用，越界抛 BusinessError(exit=1)；
  2. 合法性闸门：zip 内必须含 `project.json`，否则判为非工作区快照并抛 GuardError——防止 snapshots/ 内被投放的伪快照触发全量清除；
  3. 回归用例 6 条（绝对路径 / 相对穿越 / 伪快照 / 三次「正文零损失」与「载荷未污染」断言）。
- **验证**：两个 PoC 均被拒 exit=1，正文零损失；合法 `snapshot create/rollback` 行为不变；回归 **122 项全通过 / 0 失败**。
- **教训**：破坏性操作（解包覆盖 + 全量对齐删除）必须以「来源可信 + 内容自证」双校验为前提；`check` 对「工作区被清空」这一状态无感，属二次盲区。
