# Novel Studio v4.4.0 全域测试矩阵（Test Matrix）

> 用途：8 个测试维度子智能体的统一作业依据。每个维度在 `workspace/test-lab/<dim>/` 独立副本中执行，禁止交叉污染。
> 基座（golden fixture）：`workspace/test-lab/`（由 Fixture Builder 建造，含 ch_001 已 sync + ch_002 待收口）。
> 铁律：不读 engine 源码；不写临时脚本；统计只用引擎命令（status/ask/trace/id list/check）；所有结论以 CLI stdout + state JSON 实读为证。
> 判定标准：**假阴性**=应检出/应阻断而未检出；**假阳性**=合规数据被误报/误阻断；幂等=重放后计数零增长。

---

## Dim-1 台账原子性与事务（ledger-atomicity）

| # | 用例 | 预期 | 级别判定 |
|---|---|---|---|
| L1 | sync ch_002 首同步 | exit 0；八表条目按 delta 精确 +N；sync_log 记指纹 | 基础通过性 |
| L2 | 同章无 --force 重放 sync | 跳过 ♻️；co_occurrence/entity_timeline/arc_history/relations.history 计数零增长 | 幂等铁律 |
| L3 | 改细纲量化数据 + `sync --force` | 重新合账生效；旧增量被正确替换而非叠加 | 幂等铁律 |
| L4 | 纯文笔修订后 `sync --refresh` | 仅字数刷新；台账零变化 | 幂等铁律 |
| L5 | 计数型道具 charges 透支（5→7 消耗） | exit 1 硬阻断（六类硬阻断之一） | 假阴性检测 |
| L6 | 非计数型 charges=-1 扣减 | 不报透支错误（-1=无限耐久） | 假阳性检测 |
| L7 | 事务预检：构造冲突 delta（如同章 character_status 声明 deceased 又进 present_characters） | exit 1；**state/*.json 写盘前拦截=零写盘**（前后条目数/哈希比对） | 假阴性+原子性 |
| L8 | chapter_id 一致性 | 章号错配被拒 | 基础通过性 |
| L9 | 空正文（0 字）sync | exit 1 拒绝封存 | 假阴性检测 |
| L10 | ledger pool 增减算术 | 余额精确；多 pool 不串账 | 数据正确性 |
| L11 | sync ch_001（已同步章）不带 --force | 跳过语义明确，不双记 | 幂等铁律 |
| L12 | 快照回滚后重 sync 同章 | 指纹/台账对齐，无幽灵增量 | 逻辑死角 |
| L13 | charges_delta 使余额恰好=0 | 放行（0 合法边界） | 假阳性检测 |
| L14 | 负 delta 使 charges 反向增持 | 精确反映 | 数据正确性 |

## Dim-2 数据变更与同步链（data-sync）

| # | 用例 | 预期 |
|---|---|---|
| D1 | beats new 对已填细纲重跑 | exit 1 拒覆盖；--force 重置且自动 .bak |
| D2 | proposal auto 提取第三节涌现事实 | 反向回填细纲与台账（死亡/新登场/道具变动） |
| D3 | SSOT：只改正文不改细纲 | sync 数据零变化（正文绝不反向提数） |
| D4 | 多章增量：ch_001→ch_002 顺序 sync | 累加正确、sweep 无重复 |
| D5 | state rollup vol_01 | 时间线折叠为副本；timeline 原文保留 |
| D6 | evidence candidates | 打捞 frontmatter 声明未登记实体 |
| D7 | ask 语义检索 | 跨章事实命中 |
| D8 | trace/id trace ID 全生命周期 | 跨表链路完整 |
| D9 | sync 后 history/ch_XXX.json 快照切片 | 与当前台账一致 |
| D10 | indices/ 去重索引 | 按 chapter 去重无重复事件 |
| D11 | synopsis 梗概入账 | 章节梗概登记 |
| D12 | 卷内跨章 foreshadow plant→reveal→resolve 全链路 | 状态机正确迁移 |

## Dim-3 字段与 schema（schema-fields）

| # | 用例 | 预期 |
|---|---|---|
| F1 | 全法定字段合法值 round-trip | 全部入账无阻断 |
| F2 | 未知字段（junk_field: 垃圾值） | 引擎忽略、零告警零阻断 |
| F3 | 非法枚举：type=persona / role=hero / status=zombie / life_status=alivex / attitude=disposition 别名 | 记录实际行为：阻断 or 静默兜底（与 README「弹性兜底」对照定性） |
| F4 | 被禁字段别名：current_location / disposition / current_owner | 记录实际行为（应被忽略或映射） |
| F5 | 非核心字段整体缺失 | 静默兜底不阻断 |
| F6 | 字符串注入：name 含 `"` `\` `'` `../` 换行 emoji 255 超长 | 不崩溃不错乱；JSON 注入不生效 |
| F7 | 数值边界：tier_rank 0/13/-1、injury_level 6、scale_tier 0/11、tension -1/101、max_charges 0、charges 0 | 记录实际行为并对齐文档口径 |
| F8 | 幽灵引用：holder/leader 指向不存在 ID | reconcile 第五节应曝光 |
| F9 | frontmatter 结构变异：delta 块为 null/空串/错误缩进/整块删除 | 静默兜底不阻断（弹性选填） |
| F10 | 同实体同章多次 delta 声明 | 合并语义正确不双记 |

## Dim-4 假阴/假阳检测（probe-integrity）—— 核心维度

### 假阴性（应检出而未检出）
| # | 用例 | 预期 |
|---|---|---|
| FN1 | 正文写「XXX 气绝身亡」但细纲 character_status 未声明 deceased | **审计级责任**：记录引擎是否在 audit/probes 给出提示（无提示=设计级静默假阴性，确认 v4.3.2 同源铁律风险） |
| FN2 | 下一章 present_characters 填入已故角色 | 引擎硬阻断（六类硬阻断之二） |
| FN3 | 计数型道具 charges 连续透支两次 | 两次均阻断 |
| FN4 | 认知泄露（正文角色说出不可能知晓的秘密） | audit 探针检出（确认级=阻断） |
| FN5 | state/persons.json 手工损坏 | check 报 errors + 隔离 .corrupt-*；读命令 exit 4 |
| FN6 | 空正文 finalize | exit 1 |
| FN7 | 已 sync 章在细纲数据变更后重 sync（无 --force） | 拒绝或提示需 --force |
| FN8 | 未登记实体进 present_characters | 自动打捞建档（宽容自愈）或告警——记录实际行为 |
| FN9 | sync 覆盖已封存章节（SSOT 覆盖场景） | 拒覆盖 |

### 假阳性（合规被误判）
| # | 用例 | 预期 |
|---|---|---|
| FP1 | 复姓/少数民族名/音译名/单字名/生僻字名 | 不误报未知实体 |
| FP2 | 合法称谓矩阵内称谓 | 不误报称谓错误 |
| FP3 | 常规章节（2000~5000 字） | 遥测 warning 不误报、不阻断 |
| FP4 | retired/missing 状态角色在场 | 不误报死者复活 |
| FP5 | charges=-1 无限耐久道具正常使用 | 不误报透支 |
| FP6 | new_entities: [] / locked_facts: [] 合法空块 | 不误报未填槽位 |
| FP7 | 同章重放 sync 后 warning 不重复堆积 | 无重复告警 |
| FP8 | 微文笔修订（改 3 个字）后 sync --refresh | 不触发重同步阻断 |

## Dim-5 逻辑死角与边界（edge-cases）

| # | 用例 | 预期 |
|---|---|---|
| E1 | 章号边界：ch_000 / ch_0000 / ch_9999 / ch_1000 / ch_0010 / ch_999999 | 记录实际行为（排序、解析、报错） |
| E2 | 操作不存在章节：sync/pack/audit/finalize/snapshot ch_999 | 优雅报错非崩溃 |
| E3 | 特殊字符：卷名/实体名含引号、反斜杠、`../`、换行、emoji、255 字超长 | 不崩溃、不路径穿越 |
| E4 | 卷末三连顺序错乱（先 reconcile 后 rollup 等） | 记录实际行为 |
| E5 | snapshot 全套：create/list/rollback + 自动 pre_rollback 备份 + 对齐清除快照后新增文件 | 数据一致、无残留 |
| E6 | ID 撞号：手工同号写入两表后 id next / check | 撞号检出 |
| E7 | 派生 ID 体系：GUN/KNO/MIS/DEBT-AUTO/LOCK/ms 连续发号不撞 | 递增正确 |
| E8 | 回滚后继续写新章再 sync | 无幽灵指纹 |
| E9 | calendar 0 / 负数 / 超大 N | 优雅处理 |
| E10 | milestone achieve 不存在/重复 achieve/过去 target-ch | 记录实际行为 |
| E11 | export：无 final 章节 / --vol 不存在分卷 / --no-digest / md+txt 双格式 | 记录实际行为 |
| E12 | config set 未知键 / token_cap 0 / 负数 / 字符串值 | 拒绝或采纳并记录；随后 pack 行为 |
| E13 | 空工作区（init 后零填充）check/status/cockpit | 不崩溃；warning 清单 |
| E14 | 时间线：同日多事件、跨年事件、倒序事件 | 排序与展示正确 |
| E15 | 并发式交错：sync ch_001→sync ch_002→再 sync ch_001(force) | 台账终态正确 |
| E16 | engine token_cap 极小（如 100）时 pack | 🔴 显式旗标、绝不静默截断 |

## Dim-6 CLI 契约层（cli-contract）

| # | 用例 | 预期 |
|---|---|---|
| C1 | 每个命令的参数缺失/多余 | exit 2 |
| C2 | 业务阻断 | exit 1 + ❌阻断 + 💡方案三件套 |
| C3 | 多书工作区未指定 -w | exit 2 |
| C4 | --json 输出可解析性（help/status/check/cockpit） | 合法 JSON |
| C5 | 中文路径/带空格路径 -w | 正常 |
| C6 | status/cockpit 重复调用输出一致 | 确定性 |
| C7 | 未知子命令 | exit 2（已验证✅） |
| C8 | --version / 无参数调用 | exit 0（已验证✅） |

## Dim-7 快照时光机（snapshot-rollback）

| # | 用例 | 预期 |
|---|---|---|
| S1 | 快照含 log/ 与 pack.md 完整性 | 清单完整 |
| S2 | 回滚自动备份 pre_rollback_<ts> | 存在可再回滚 |
| S3 | 回滚后快照后新增文件被对齐清除 | 无残留孤儿文件 |
| S4 | 回滚后台账/sync_log/history 三者一致 | 无幽灵章 |
| S5 | 连续两次回滚（快照A→B→A） | 稳定 |
| S6 | 回滚后重跑 check | 0 errors |
| S7 | 快照名特殊字符/重名 | 记录实际行为 |

## Dim-8 卷末刹车链（volume-chain）

| # | 用例 | 预期 |
|---|---|---|
| V1 | rollup vol_01 生成 JSON 副本 | timeline 原件不动 |
| V2 | reconcile vol_01 --write 五节结构 | 第五节自洽体检；逾期伏笔清单 |
| V3 | reconcile 检出植入的幽灵 ID/未回收伏笔/锁定事实悬空 | 必须曝光（假阴性检测） |
| V4 | export 只读 final/ 不反写台账 | final 内容=导出内容 |
| V5 | export 前情提要 digest 生成 | 存在 |
| V6 | 空卷/无章卷 reconcile+export | 优雅处理 |
| V7 | 卷末后换卷：新 vol_02 outline + milestone + check | 0 errors |

---

## 交付标准（每个维度回执）

每个维度 subagent 回执必须包含：
1. **通过/失败/假阳/假阴四态计数表**（用例号逐项列）
2. **缺陷分级**：Level 1 轻瑕（体验/文案/边界提示）｜ Level 2 深层（数据不一致/静默失败）｜ Level 3 系统级（崩溃/数据损坏/退出码违约）
3. **每个缺陷的证据链**：命令 + 退出码 + 关键 stdout/stderr 片段 + 影响面推断
4. **不确定项标注 [需人工裁决]**，严禁臆断
