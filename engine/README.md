# Novel Studio 确定性引擎内部文档（engine/）

> 面向引擎维护者。智能体与用户请通过官方 CLI 交互（`python studio.py help --json`），
> 遵守 AGENTS.md 的「引擎源码绝对黑盒」契约，不读改本目录源码。

## 模块地图

| 模块 | 职责 | 关键不变量 |
|---|---|---|
| `cli.py` | 子命令入口与退出码映射 | 业务阻断=1；参数错误=2；环境=3；系统故障=4 |
| `errors.py` | `BusinessError`/`GuardError` 错误契约 | 守卫类阻断必须抛 GuardError |
| `ops.py` | init/beats/audit/finalize/proposal/sync/snapshot/reconcile/rollup/simulate/evidence/milestone/trace 等 | `beats new` 拒覆盖已填细纲（--force + .bak）；`init` 已有书籍拒覆盖（--force）；`sync` 空正文拒绝封存 + chapter_id 一致性 + 事务预检（写盘前拦截全部冲突）+ 按章幂等增量（--force 重同步 / --refresh 刷字数） |
| `cruise.py` | 无人值守巡航批次编排 | 计划钳制 min(N+K,M) 且单批 ≤`cruise_max_chapters`；每章 sync 后打印单行心跳；卷末自动刹车链 rollup→reconcile→export（exit 0；check errors>0 或等待超时 exit 1）；`cruise_human_gate=K` 每 K 章暂停等 `.cruise_gate` 哨兵文件（作者确认后创建，引擎消费即删，0＝关闭）；`check` errors>0 立即停机 |
| `state.py` | 八表持久化与细纲增量合账 | **原子写盘**（tempfile+os.replace）；损坏 JSON 隔离+硬报错（退出码 4）；sync 幂等（co_occurrence/entity_timeline/arc_history/relations 按 chapter 去重）；显式生死契约（零关键词猜谜，显式 life_status 优先）；`apply_state_deltas` 事务预检先于任何写盘 |
| `pack.py` | 装配包构建与预算裁剪 | P0（细纲/禁令/法定事实）永不裁剪；四级修剪后仍超限输出 🔴 显式旗标（绝不静默截断）；token_cap 来自配置中心；紧凑 present_characters（字符串/单字典）自动归一化 |
| `probes.py` | 确定性物理事实探针 | 纯确定性物理/数据探针；阻断级仅 2：空正文(0字)/确认级认知泄露；其余 warning（彻底去除主观文学、排版与字数硬约束，文学归LLM） |
| `check.py` | 全书体检（16 表巡检） | 未填槽位闸门（warning 清单，Stage 0C 验收依据）；state/ 全表可解析性巡检（损坏即 errors）；ID 完整性/台账一致性深度校验 |
| `config.py` | 配置中心 | 优先级：project.json.engine > project.json.scope > DEFAULT_CONFIG |
| `parser.py` | 内置 YAML 解析 | **永不 import PyYAML**（确定性契约） |
| `exporter.py` | 成书导出 md/txt + 前情提要 | 只读 final/，绝不反向写台账 |
| `id_tracker.py` | ID 发号/清册/追踪/完整性 | 全表 + beats 双扫描防撞号 |
| `schema.py` | dataclass 数据契约 | 兼容别名：CharacterState 等 |

## 数据表（state/）

`persons / items / factions / places / lines / locked / ledger / current` 八表 + `timeline / synopsis / relations / debts / milestones` 扩展表 + `sync_log.json`（章节同步指纹，幂等判定依据）+ `history/ch_XXX.json`（每章全息快照切片）+ `indices/`（co_occurrence、entity_timeline）+ `log/review/reconcile_vol_XX.md`（卷末对账存档）。

写入路径全部经 `_save_json` 原子替换；读取损坏时隔离为 `*.corrupt-<时间戳>` 并抛 RuntimeError（CLI 退出码 4）。

## 设计不变量（改动前必读）

1. **SSOT**：状态只从细纲（beats front-matter）流入台账，正文绝不反向提数；
2. **四层数据完整性模型**：事务预检（`apply_state_deltas` 先校验全部冲突，任一冲突=零写盘）→ 按章幂等增量（重放安全）→ 原子写盘（tempfile+os.replace）→ 损坏硬失败（隔离 `*.corrupt-*` 并抛 RuntimeError，退出码 4）；
3. **sync 幂等**：同一章重复 sync 不得虚增任何计数（co_occurrence.total_co_occurrences、entity_timeline.events、arc_history、relations.history 均按 chapter 去重，判定依据 `state/sync_log.json` 指纹）；同章同稿重放跳过 ♻️；细纲量化数据变更须 `--force` 重同步；纯文笔修订用 `--refresh` 仅刷新字数；
4. **宽容自愈边界**：非核心字段缺省静默兜底，但 **JSON 损坏、死亡角色登场、充能透支、空正文封存、SSOT 覆盖、init 覆盖已有书籍** 六类必须硬阻断；
5. **探针强弱分级**：纯物理事实与数据探针（认知盲区、称谓矩阵、物象落地 + 字数遥测），绝不越权检测文学文风与排版节奏；阻断级仅 2（空正文/确认级认知泄露），其余一律 warning 交由 Auditor 审阅；
6. **配置唯一真值源**：新旋钮必须进 `config.py DEFAULT_CONFIG` + `CONFIG_GUIDE`，禁止在业务模块硬编码；
7. **版本一致性**：`engine/__init__.__version__` 是唯一版本号，cli/cockpit 均动态引用。

