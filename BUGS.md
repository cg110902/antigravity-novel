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
