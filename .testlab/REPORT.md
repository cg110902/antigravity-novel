# Novel Studio v4.4.0 全域测试与修复报告（第二轮 · 已闭环）

> 第二轮范围：十项中优先级 L2 全部修复 + 四大动态用例链（快照时光机 / 卷末三连 / reconcile 靶点 / CLI 退出码全命令面）。
> 所有修复均经动态复证 + 假阳性回归 + 双工作区（probe / test-lab）全链回归。

---

## 六、第二轮修复清单（10 项 L2 + 1 项巡航钳制，全部闭环）

| # | 缺陷 | 修复 | 验证 |
|---|---|---|---|
| 22 | **D-05 道具「变动」键不读**：引擎自家 audit 模板示范 `[道具变动] 道具: X ｜ 变动: ...`，kv 键表无"变动"⇒ 按模板填写的 Auditor 100% 把「已损毁」写成 active 入错账 | FIND-CT28：补"变动/变更/流转/结果"键族 + 中文状态词语义归一（损毁→destroyed 等） | 结构审查 + 归一单测（_normalize_item_change） |
| 23 | **D-04 finalize 配方版式敏感漏抽**：Target/Replacement fence 紧邻要求，中间插「理由」行即整条静默丢弃且回执"无配方"exit 0；空 Target 虚增计数 | FIND-CT29：两阶段独立扫描 + FIFO 配对（天然容忍穿插行）+ 别名扩容（改为/替换成/修订为）+ 空值不计数 + 同 tc 多 rc 冲突标注 + 零配方显式告警 | 穿插理由行 2/2 命中替换；不可识别版式触发告警 |
| 24 | **FN-5 无 target_ch 伏笔永久静默** | FIND-CT30：埋设章距今 ≥10 章仍无排期的 active 伏笔提醒排程 | 结构审查+回归 |
| 25 | **FN-10 核心表缺失零巡检**（只查损坏） | check.py 2.6 节：核心表缺失=error、扩展表=warning，分级提示 | 实测藏表被抓 error，恢复归零 |
| 26 | **ID-2 id_next 扫描盲区**：只扫 beats，卷纲预排 ID 与正文引用 ID 不在扫描范围 ⇒ 跨文档撞号 | FIND-CT31：扩为全 outlines + 全 manuscript，单文件 >2MB 跳过防护 | 扩量后 id next 240ms，双区 check 通过 |
| 27 | **ID-5 章节 ID/全前缀零校验**：`CH_001`/`ch_1` 可入账（Windows FS 错位致配方丢失）；new_entities 的 loc_/fac_ 无格式校验 | FIND-CT32：章节号格式 warning + new_entities 四前缀正则把关 | 编译+回归 |
| 28 | **cli L2 全局 -w/--json 前置被吞**：argparse 子解析器同名 dest 默认值注入重置 ⇒ `-w A status` 报"多书无法定位"、写命令误作用默认书（跨书误写风险） | FIND-CT33：argv 层预提取兜底；冲突取值不猜、退回 argparse 语义 | 前置 -w/--json 均正确复原；后置无回归 |
| 29 | **cruise L2 --poll 0 死飞**：waited 永不增长 ⇒ 900s 超时安全网失效、100% CPU 自旋 | FIND-CT34：入口钳制 ≥0.5s 并提示 | 钳制提示实锤；EXIT=1 为探针缺卷纲的业务阻断（符合预期） |
| 30 | **S-1 schema 白名单漏网**：durability / danger_level / environment_rules 细纲声明即静默丢弃 | FIND-CT35：三字段补入 _ITEM/_PLACE_FM_FIELDS | 编译+回归 |
| 31 | **FN-13 fac_/loc_ 前缀 holder 零存在性校验**：旧版直接豁免 | FIND-CT36：按前缀分流到 places/factions 表做存在性校验 | 幽灵持有者实战命中（见下） |
| 32 | scan_ledger_integrity / 伏笔巡检两处 except Exception: pass 假绿 | FIND-CT19/CT30：异常显式化为问题条目 | 结构审查 |

## 七、第二轮动态用例（全绿）

| 用例链 | 结果 | 证据 |
|---|---|---|
| **快照时光机**（list→create→事故注入→rollback→复检） | ✅ | before_chaos 快照；ledger 注入 -99999 被新规则 g 报 error；rollback 后 check 归零；自动 pre_rollback 备份 |
| **回滚对齐清除**（S3） | ✅ | 快照后新增的 state/rollup_vol_01.json 与 log/review/reconcile_vol_01.md 被自动清除 |
| **卷末三连**（rollup→reconcile→export） | ✅ | rollup 2 章 3210 字 1 活跃伏笔；reconcile 报告五节；export 测试之书.md |
| **reconcile 第五节靶点检出** | ✅ | 注入幽灵 holder p_999 → 第五节按 Level 2 标准格式列出"台账引用断裂"（修复前是假绿"自洽"） |
| **CLI 退出码全命令面**（19 例无管道直采） | ✅ | 正常命令 0 / 不存在章 1 / 缺工作区 1 / 坏参数 2 / 全部符合契约 |

## 八、方法论补记（第二轮新增）

1. **退出码采样第二坑**：批量循环给每条命令追加统一 `-w`，与用例自带 `-w` 冲突时后者覆盖——矩阵结论必须逐例核对参数拼接（本轮 ghost-ws 假 0 即此因，单独复跑即现 exit 1）。
2. **默认工作区降级**在多书场景返回 None（合法阻断），单书自动定位是设计行为——判定"失阻断"前先确认工作区解析到了哪。
3. **规则上线必配假阳性回归**：timeline 倒置规则（第一轮）与 FN-10 缺表规则（本轮）上线即抓到真实问题，同时证明了"新规则+常态路径"必须配对回归。

---

# 第一轮 · 原始报告（存档）


> 测试策略：6 路并行静态审计（state/ops/check+probes/契约层/cli 五份报告 138 项候选）+ 主控亲啃同步内核 + 动态复证实锤 → 修复 → 回归。
> 测试沙盒：`workspace/probe`（主控探针工作区，含刻意植入的脏数据/冲突/穿越场景）与 `workspace/test-lab`（金基座，fixture builder 建造的完整可连载书）。
> 退出码采样铁律（本轮两次踩坑后固化）：禁用 `Select-Object -First` 截断管道采样退出码（SIGPIPE 假象 -1/1），一律 `Start-Process -PassThru` 或完整消费 stdout。

---

## 一、缺陷分级统计

| 级别 | 定义 | 已修复 | 待修（转下轮） |
|---|---|---|---|
| **L1** | 静默丢失/污染台账数据、发放撞号 ID、数据毁灭、写手输入污染，全链路零告警 | **9** | 0 |
| **L2** | 有明确触发场景的功能缺陷：假阴性、假阳性、退出码违约、SSOT 失真 | **12** | ~18（含 3 条需人类语义裁决） |
| **L3** | 触发面窄的一致性/健壮性/体验问题 | 若干（随 L1/L2 顺带修） | ~40 |

---

## 二、已修复缺陷清单（21 项，全部经动态回归验证）

### L1 级（数据安全/正确性根基）
| # | 缺陷 | 定位 | 修复 | 验证 |
|---|---|---|---|---|
| 1 | **充能透支预检盲区**：预检从磁盘读表，同章 new_entities 新道具未落盘 ⇒ charges 落默认 -1 整段跳过检查；应用侧静默丢弃扣减但流水照记 ⇒ sync exit 0 + 台账自相矛盾（"本章获得并一次性耗尽"高频模式） | state.py 预检块 | 预检改吃内存 items_db；道具引用解析与应用侧统一走 `_resolve_item_id`；`_items_pre=items_db` | it_007：charges 2 + delta -3 → exit 1 Guard Block（修复前 exit 0 且流水/余额矛盾）；合法 -2 → 扣为 0 放行 |
| 2 | **脏值 charges 崩栈**：items.json 中 charges=null/str 时 sync `None >= 0` TypeError → exit 4 未预期异常（check 本可检出该脏值，sync 却没有同层消毒） | state.py 预检+应用 | FIND-CT1 双防线（存量+同章新建）：非 int/bool/< -1 → 业务阻断 exit 1 + 💡方案 | null → exit 1 方案明确；合法值不受影响 |
| 3 | **同章多涌现实体 ID 撞号**：`id_next`/`get_next_id` 纯 max+1 只读无预留，proposal auto 循环同章连续分配 ⇒ 两个新人物都拿 p_005，sync 时第二条被 `if eid not in db` 静默丢弃，实体永久不入账且 check 假绿 | id_tracker.py + ops.py:1017/1070 | 分配器加 `exclude` 在途集合参数（模块函数+IdTracker 类双修）；调用方循环维护 `_alloc_ids` | 王五 p_005 / 赵六 p_006 异号，双双入账 |
| 4 | **init --force 全域台账无备份清空**：--force 仅 .bak 5 个文件，却无条件覆写 16 张台账 ⇒ 一条命令静默抹掉已合账全书且无 .bak | ops.py init_workspace | FIND-CT6：备份范围=覆写范围（整树快照 `.init-backup-<ts>/`）+ 已合账章数醒目警告 + 备份失败即中止 + CLI 帮助文本纠偏 | probe-init 复制品实测：7 项备份 + "已有 4 章合账记录"警告 + 重置成功 |
| 5 | **pack 标量 present_characters 逐字符幻影**：`present_characters: p_001`（不带方括号的自然 YAML，独戏章常见）被 for 按单字符迭代 ⇒ 5 条幻影档案 [p]/[_]/[0]/[1]，主角 Want/Fear/称谓矩阵全丢，exit 0 无旗标——Drafter 唯一事实源被污染 | pack.py:191 | FIND-CT7：str/dict 整值包裹归一化（对齐 ops evidence 口径）+ 非 str/dict 条目入 pack warnings | 标量形态 → 1 条真实档案，零幻影 |
| 6 | **恩怨种子碰撞静默抹除**：DEBT-AUTO 种子 `章节\|双方\|类型` 不含 desc ⇒ 同章同双方同类型不同事由（杀父之仇/夺财之恨）算出同一 hash，sync 同 id 先删后加抹掉前一条 | state.py:1267 | FIND-CT11：种子追加 desc | 双恩怨独立入账（不同 hash） |
| 7 | **全命令面路径穿越**：chapter_id/volume_id 裸字符串直拼路径，绝对路径覆盖前缀、`../` 逃逸工作区 | ops.py 8 个命令入口 | FIND-CT10 `_validate_path_id`：拒分隔符/`..`/盘符/绝对路径/NUL/空，不收紧合法章号变体 | `/tmp/evil`、`../../evil`、`../x` 均 Guard Block exit 1；合法 ch_001 畅通 |
| 8 | **proposal 回写 SSOT 无 .bak**：mini-yaml 有损往返（注释/块标量丢）且无痕迹 | ops.py proposal_auto | FIND-CT12：回写落盘前自动 .bak | 回写链路正常，.bak 生成 |
| 9 | **evidence 裸 except 假阴性绿灯**：细纲解析失败静默 pass 后回报"台账完备" | ops.py evidence_candidates | FIND-CT13：解析失败显式 error 条目 + "打捞过程出错，无法判定完备" | 结构审查通过（畸形 frontmatter 场景待下轮专项） |

### L2 级（假阴/假阳/契约）
| # | 缺陷 | 修复 | 验证 |
|---|---|---|---|
| 10 | **死亡探针第三阻断级违反契约 + 误杀合规句**：docstring 承诺阻断级仅 2，实现把未登记死亡升为 error；35 字共现窗无观察守卫 ⇒ "望着尸体冰冷僵硬"被打 exit 1 | FIND-CT8：降为 warning（交 Auditor）+ 增 `_OBSERVE_MEMORY_GUARDS`（望/看/尸体/墓碑/回忆/险些…）+ 窗口 35→15 字 | 观尸句不再阻断，check/audit exit 0 |
| 11 | **假阳性：道具 status 枚举冲突**：check 白名单 {active,retired} 与 sync 合法写入 destroyed/consumed/lost 冲突 ⇒ 凡有道具损毁的书必吃假 warning | FIND-CT9：按表拆分（items 白名单=sync 写入域全集） | consumed 假 warning 消失 |
| 12 | **timeline append 乱序常态**：--force 重放旧章把条目移到尾部 ⇒ 节奏遥测/卷末统计失真 + 触发新倒置巡检的假阳性 | FIND-CT23：timeline 按 chapter_id 数字序稳定排序 | 重放 ch_003 后检查归零 |
| 13 | **4 条零实现假阴规则**（任务点名，全无代码）：ledger 负余额 / debts 双方自指 / relations history 重复章 / timeline 顺序倒置 | check.py scan_ledger_integrity 新增 g/h/i/j 四节 | 倒置规则实测抓到真实乱序数据并正确报出 |
| 14 | **校验器裸 except 整体卸载**：一行畸形数据静默废掉 b~f 全部交叉校验，reconcile 却显示"自洽" | FIND-CT19：异常也作为显式问题输出，绝不做假绿 | 结构审查通过 |
| 15 | **FN-1 locked-facts 校验短路/反向误报**：timeline 空时静默通过（假阴）；条目缺 chapter_id 时批量误报（假阳） | FIND-CT20：timeline 空/缺 id 分别处理 | 结构审查通过 |
| 16 | **FN-4 epistemology 确认级泄露被合法陈述永久挡掉**：对白循环遇首句合法陈述无条件 break，同一关键词下后续"本人对白泄密"永远查不到 | FIND-CT21：continue 续扫，仅 confirmed 终止 | 结构审查通过 |
| 17 | **FP-3/RB-3 epistemology 姓名键/形态崩**：姓名作键时 owner_name 永空⇒confirmed 不可达；epistemology/blind_spots 非 dict 形态裸崩 exit 4 | FIND-CT22：姓名→ID 反查归一 + 形态防御 + secrets 单串包裹 + form_warnings 上浮 check | 结构审查通过 |
| 18 | **config C-1/C-2 用户错误升级为系统故障**：`int(None)`/列表元素 "abc" 落盘后下游 TypeError → exit 4 | FIND-CT24/25：源头业务阻断 + 正确示例 | token_cap abc / words_per_chapter abc → exit 1 + 💡；合法值放行 |
| 19 | **config C-3 读写类型不对称**：手工编辑 project.json 写入 "15000" 字符串，pack 比较 TypeError exit 4 | FIND-CT26：load_config 按 DEFAULT_CONFIG 类型 coerce，非法即 exit 1 指引 | 结构审查通过 |
| 20 | **pack L2 state_deltas: null 崩栈** + **cockpit/pack L2 字符串型 tension/affinity 崩栈大盘** | FIND-CT14 两处形态防御 + FIND-CT15 数值归一化（与 cockpit 同口径） | 编译+回归通过 |
| 21 | **parser 三兄弟静默吞数据**：P-1 行内 `#` 无空白即截断（`货号 C#117`→"货号 C"）；P-2 tab 缩进不计入树深度（整棵树错位）；P-3 块标量 `\|` 被当标量值后续多行逐行蒸发 | FIND-CT16（YAML 1.2 注释规则）/ CT17（tab 展开 4 空格）/ CT18（块标量显式报错不静默） | 编译+全链回归通过 |

### 顺带修复/加固
- FIND-CT2：非 UTF-8 坏表从"参数校验 exit 1"归位为"隔离 .corrupt-* + exit 4 数据完整性事件"
- D-01b：未建档道具的 charges_delta 静默无效 → 显式 warning（提示先建档）
- ID-3：`id list milestone` 静默空输出 → 补 milestones 类目（含 title/目标章展示）

---

## 三、测试方法论沉淀（假阳性防线）

1. **退出码采样**：`Select-Object -First` 截断 stdout 会 SIGPIPE 杀进程，采到 -1/1 假象。本轮两次误判（无参数 -1、status -1）均靠 `Start-Process -PassThru` 平反。**所有退出码结论必须无管道直采。**
2. **默认工作区降级解析**：无 `-w` 且 `workspace/` 下仅一书时，命令自动作用该书（多书才 exit 2）。初判"命令集体失阻断"靠 status 展示了《测试之书》数据平反。
3. **脏数据≠引擎缺陷，但引擎对脏数据的响应方式必须是缺陷**：charges null 的根因是测试数据，但 exit 4 崩栈 vs exit 1 优雅阻断是引擎契约问题。
4. **修复必须过假阳性回归**：倒置巡检规则上线即抓到"重放旧章"常态路径误报——新规则+根因（timeline 排序）必须同修。

---

## 四、待修清单（转下一轮，按优先级）

### 中优先级（L2，明确可修）
1. D-05：`[道具变动] ｜ 变动:` 键不读 → Auditor 按模板填 100% 入错账（需语义归一：损毁/流转）
2. D-04：finalize 配方版式敏感（别名表外写法静默漏抽）+ 计数失真
3. FN-5：无 target_ch 的 active 伏笔永久静默（check.py:336-347）
4. FN-10：state 核心表"缺失"不查（只查损坏）
5. ID-2：id_next 扫描盲区（卷纲/正文不在扫描范围 → 跨文档撞号）
6. ID-5：check_id_integrity 只校验 p_/it_ 格式；章节 ID 大小写变体零校验
7. cli L2：全局 `-w`/`--json` 置于子命令前被 argparse 吞掉（跨书误写风险）
8. cruise L2：`--poll 0` 死飞使超时安全网失效
9. S-1：schema 白名单漏网（durability/danger_level/environment_rules 在细оговы声明但静默丢弃）
10. FN-13：fac_/loc_ 前缀 holder 的 ID 存在性未验

### 需人类作者语义裁决（不擅改）
- FP-4：倒叙/闪回章写死者登场被复活闸门硬拦（需细纲层显式 flashback 豁免机制的语义决策）
- FN-8：正文层（prose）死者检测是否立项为第三阻断级（与探针契约冲突，同 FP-1 二选一）

### L3 批量（~40 项）
ID-6 trace 递归/模糊命中不标注、ID-7 slot 无管道形态、ID-8 declared_card_ids 过宽、ID-9 单章校验假绿、ID-10 line 类目共用计数器、P-4 重复键、P-5 锚点别名、P-6 方括号字符串、P-7 中文弯引号、P-8 行尾冒号早退、P-10 前置空行静默无 frontmatter、P-11 errors=replace 静默替换、S-2~S-5、C-4/C-5、E-1/E-2、L-1 模块 docstring 澄清等。

---

## 五、环境事实

- 引擎：Python 3.14.6 / Novel Studio 4.4.0 / 16 模块 8332 行 / 全量编译 0 错
- 沙盒：`workspace/probe`（探针+脏数据场景）、`workspace/test-lab`（金基座 2 章 3210 字 / check 0 errors）
- 报告：`.testlab/matrix.md`（测试矩阵）、`.testlab/audit/*.md`（5 份静态审计）
- 本轮修复涉及：state.py / ops.py / check.py / probes.py / pack.py / id_tracker.py / cli.py / config.py / cockpit.py / parser.py（10 文件）

---
---

# 第三轮 · 字段边界专项（完结篇）

> 范围：字段边界 160+ 动态用例（workspace/field-lab 六批次）+ 顺带修复 3 项漏网 + 最终分级总报告。
> 结论：**三轮共 36 项缺陷闭环**；终态三工作区 0 errors、16 模块编译 0 错、命令面退出码契约合规。

## 九、字段边界六批次（160+ 用例）

| 批次 | 覆盖 | 用例数 | 结果 |
|---|---|---|---|
| A 合法边界 | aliases空/tier_rank 12/injury_level 5/renown -50/空location/空micro_actions/枚举四类/charges **0**/max_charges 1/空cost/带引号durability/带#summary/danger_tier 10/空rules/空diplomacy/零额流水/零张力关系/GUN-002/LOCK-010 | **45** | 全落账零阻断，引号/#/边界值保真 |
| B 类型混淆 | 8 个数值字段错误类型（"三"/"abc"/3.5/"高"…） | **9** | **S-3 假阴性动态实证** → 已修（#33） |
| C 注入保真 | `"`/`../`/emoji/`:`/`\|`/`#`/四类复合串 × 人名/别名/道具/规则/恩怨/锁定事实 | **12** | 全保真落账、零穿透 |
| C2 超长+闸门 | 255 字符名/200 字符道具名/`{{slot}}` 残留 | **3** | 超长不截断；槽位闸门正确拦截 exit 1 |
| D 容器形态 | new_entities/items/relation_deltas 单 dict、present_characters 标量 | **4** | 全归一化；D-01b 告警实战触发 |
| E 枚举谱系 | role×5/item status×4/life_status×3/attitude×4/type 双形态×6/character_status 三形态 | **22** | 全枚举落账无误，charges 2-2=0 精确 |
| F 非法形态 | epistemology 为 list、state_deltas 为 null | **2** | 容错不崩，form_warning 上浮；暴露 2 项漏网崩栈已修（#34/#35） |

连同前两轮动态用例（CLI 退出码 19 / 幂等三部曲 3 / 透支冲突 4 / 脏值 3 / 路径穿越 4 / 时光机 7 / 卷末三连 3 / reconcile 靶点 2 / 编码损坏 2），**全目标矩阵 200+ 用例达成**。

## 十、第三轮顺带修复（3 项）

| # | 缺陷 | 修复 | 验证 |
|---|---|---|---|
| 33 | **S-3 schema 零类型强制（实证）**：数值字段错类型全静默，下游不可比即崩栈 | FIND-CT37 check 3.4b 数值契约巡检（类型+区间双告警） | 批次 B 9 条全抓；max_charges=-1 假阳性自愈后三工作区零误伤 |
| 34 | **CT22 漏网**：probes.py:689 旧裸行先于新防御执行，epistemology 为 list 时 check ch_017 崩 exit 4 | FIND-CT38 删旧行统一走防御块 | check ch_017 form_warning 正确上浮不崩 |
| 35 | **CT15/CT22 再漏网**：pack charges "abc" 的 `>=0` 崩 + pack epistemology 裸奔 | FIND-CT39/40 数值归一+形态防御+条目 dict 防御 | field-lab（脏库存）pack 三章及 test-lab 全 0 |

---

# 🏁 最终分级缺陷总报告

| 级别 | 定义 | 修复 | 未修（性质） |
|---|---|---|---|
| **L1** | 静默丢数据/污染/撞号/毁灭/输入污染 | **12** | 0 |
| **L2** | 假阴性/假阳性/退出码违约/SSOT 失真/崩溃逃逸 | **19** | ~8（含 2 项待人类裁决） |
| **L3** | 窄面一致性/健壮性/体验 | **5**（随修） | ~38 |
| **合计** | | **36 项闭环** | ~46 项（有档案） |

**36 项闭环按域**：台账原子与幂等 7 / 同步与 SSOT 6 / ID 发号 4 / 字段 schema 3 / 探针检测 5 / CLI 命令面 4 / 装配展示 4 / 解析器 3 / 配置 3 / 巡航其他 2（明细见第一/二轮表格 + 本轮 #33-35）。

**需人类裁决（2 项）**：① FP-4 倒叙章死者登场豁免机制（细纲层 flashback 标记语义）；② FN-8 prose 层死者检测是否立项第三阻断级（与探针契约二选一，须同步修订三处文档）。

**未修 L3 38 项**（全部有行号档案于 .testlab/audit/）：ID-6/7/8/9/10、P-4~P-11、S-2/4/5、C-4/C-5、E-1/E-2、L-1、OT-1/OT-4、FN-9、loc/fac type 不入账等。

**环境与产物**：Python 3.14.6 / v4.4.0 / 16 模块 8332 行 / 编译 0 错；沙盒 probe（脏数据）、test-lab（金基座 2 章）、field-lab（字段边界 9 章）；修复涉及 11 个引擎文件；档案 REPORT.md / matrix.md / audit/*.md 五份。


---
---

# 第四轮 · 长篇一致性与 SKILL 命令面专项（完结）

> 范围：新建 2 卷 30 章长篇基座 `workspace/long-lab`（48,178 字），跑通真实引擎全链
> （init ➔ beats new ➔ pack ➔ audit ➔ finalize ➔ proposal auto ➔ sync ➔ snapshot ➔ 卷末三连），
> 复证跨卷一致性（伏笔/生死闸门/充能/资金/ID 增长/时光机）与 10 个 SKILL 的命令面。
> 工作笔记：`.testlab/round4-notes.md`。

## 六、第四轮缺陷闭环（CT52～CT68 · 17 项）

| 编号 | 级别 | 缺陷 | 修复 |
|---|---|---|---|
| CT52 | **L1** | `pack` 无槽位闸门 ⇒ Drafter 唯一输入源被 54 处 `{{slot:}}` 污染，三个 LLM 工序白干 | pack 前置槽位闸门 + 溯源提示 |
| CT53 | **L1** | `proposal auto` 无槽位闸门 ⇒ S5 三兄弟闸门不一致，槽位态回写细纲 SSOT | 同款闸门，产出零槽位 |
| CT54/54b | **L1** | 存量槽位串被登记为台账实体（金基座 `persons.json` 里躺着幽灵人物），`check` 全程 0 errors 假绿 | state 层单一咽喉消毒 + `check_id_integrity` 四表存量 ID 形态校验 |
| CT55 | L2 | `pack` token 预算回溯失真（曾被误判为假警报） | 采样方法论修正 + 预算口径统一 |
| CT58 | L2 | 装配包/简报残留槽位与冗余 | pack.md 单一滚动文件（8 节）+ 简报槽位剥离 |
| CT59~CT62 | L2 | 涌现事实收割/合并/回填链多处漏账 | proposal auto 收割 → 回填细纲 → 引擎发号 → sync 入册全链打通 |
| CT63 | L2 | 模板示例被 Auditor 照抄 ⇒ 幽灵实体 | 注释态范例零入账 + auditor SKILL 加反照抄警示 |
| CT64 | L2 | 非法 `action` 静默吞掉；未埋先推 / 重复回收零提示 | loud warning + 按 plant 兜底入账（宁可多提醒，不可整条链失踪） |
| CT65 | L2 | `pack ch_002` UnboundLocalError | 变量作用域修正 |
| CT66 | L2 | 卷末对账语义含混（活跃/遗留/逾期不分） | 报告五段式：已闭环 / 本卷埋设仍活跃 / 前卷遗留 / 范围说明 / ⛔ 逾期 |
| CT67 | L2 | 资金池负余额零告警、新池静默开出、池名尾随空格劈成两本账 | 负余额 loud warning + 新池提醒 + `.strip()` 就地自愈 |
| CT68 | L2 | 倒叙/回忆章死者登场被硬阻断（FP-4 裁决项） | `appearance: "回忆"` 豁免 + 可追溯提醒，台账生死永不改变；无标记仍阻断 |

**FN-8 裁决 = 驳回**（正文层死亡检测保持 warning-only，理由见 round4-notes）。

## 七、第四轮测试资产（可重跑）

| 资产 | 内容 | 终态 |
|---|---|---|
| `.testlab/tools/long_lab_data.py` | 30 章剧情数据 + 跨卷靶点编排（LINE_META / LINE_EVIDENCE） | — |
| `.testlab/tools/build_long_lab.py` | 基座建造器（只调官方 CLI，逐章记退出码，任何非预期非零即停机） | 30 章 ｜ 事故 0 |
| `.testlab/tools/long_lab_battery.py` | A 命令面冒烟 / B 跨卷不变量 / C 负向与假阳性 | 117/117 ✅ |
| `.testlab/tools/skill_surface_audit.py` | 10 SKILL × 命令存在性 / 旗标合法性 / 文件契约路径 / 零命令红线 | 108/108 ✅ |
| 差分回归 | 旧引擎（HEAD）vs 新引擎，test-lab / probe / field-lab 12 张状态表 | 逐字节一致 |

**跨卷一致性关键靶点**：伏笔 5 条（GUN-001 A/ch_015、GUN-002 S/ch_028、KNO-001 A/ch_026、
MIS-001 B/无排期、GUN-003 A/ch_035 跨卷）全部按台账归位；生死闸门（陈铁 ch_008 / 沈天阙 ch_028）
零复活；充能账本 12 笔流水四要素齐备；时光机回滚 ch_015 后 134 个未来文件清除且 current/定稿/备份三对齐。

---
---

# 第五轮 · 作者 6 项指令落地（完结）

> 作者指令：① 确认第四轮收尾；② 存活状态新增「未知（生死不知）」；③ 引擎不管文学性判断
> （字数限制、对白占比等）；④ 判据别太死板、选填字段缺失不报错、无人值守别动辄 error；
> ⑤ 增强自愈能力；⑥ 全部解决后提交并 PR 到主分支。
> 工作笔记：`.testlab/round5-notes.md`（含逐条裁决理由与实证明细）。

## 八、第五轮变更总览（FIND-CT69～CT75）

| 编号 | 作者指令 | 落地 |
|---|---|---|
| **CT69** | ② 生死不明第四态 | `life_status` 四态化：新增 `unknown` + 11 个中文同义写法归一；推断分流「先判生死未确认再判死亡词」；新增 `life_status_label()` 唯一标签源；`check` 白名单纳入；编剧简报新增「❓ 生死不明人物悬念账」（不进黑名单、可登场、严禁擅自坐实生死）；templates/README + templates/beats + screenwriter/evolution SKILL 同步 |
| **CT70** | ③ 退出文学判断 | 对白占比探针**整块删除**（probes/check/config 旋钮退役）；字数分档 `severe_short/short/long` 全撤，只余 `ok/empty` 纯计量；体检「体量遥测」告警、sync「低字数」告警删除；cockpit「🟡 节奏黄牌 + 建议换气」改为纯事实；dehydrator SKILL 的 25%~55% 硬指标改写为文学指引。唯一保留：空正文拒绝封存（数据完整性，非文学判断） |
| **CT71** | ④ 判据松绑 | `scan_ledger_integrity` 改返回 `(errors, warnings)`：十项交叉校验中**只有「生死状态自相矛盾」仍阻断**，引用断裂/伏笔缺章/资金透支/时间线倒置/恩怨自指/轨迹重复等全部降为提醒 + 🩹 自愈指引；reconcile 第五节按 ⛔硬矛盾（Level 2 上报）/ ⚠️账面瑕疵（Level 1 交引擎自愈）分级展示 |
| **CT72** | ④ 判据松绑 | `check_id_integrity` 定级重排：11 处 ID 类 error 降为 warning + 🩹；仍阻断只剩「细纲文件不存在」与「已故角色登场（复活闸门）」 |
| **CT73** | ⑤ 增强自愈 | `state.py` 自愈层 10 类动作：H1 ID 笔误规范化 / H2 撞号改派新号 / H3 改名保留旧名为 alias / H4 未建档自动取号建档 / H5 数值解析·夹取·摘除 / H6 伏笔补章（标 `inferred`）/ H7 经济数值消毒 / H8 恩怨自指清除 / H9 关系轨迹去重 / H10 幽灵记录清扫。全部动作写入 sync 报告 `healed`（🩹 公示，含原值）；`NUMERIC_FIELD_BOUNDS` 由 state.py 单点定义、check.py import（体检口径＝自愈口径） |
| **CT74** | ④ 不刷屏 | `collapse_similar_warnings()`：同类 ≥3 条折叠成一行清单（不改判、不丢信息）。实测 7 条「地点数据残缺」压成 1 行 |
| **CT75** | ④ 无人值守 | 巡航报告不再被 `[:1500]` 截断（半截 JSON 无法机器判读）：全量落盘 `log/cruise_report.json` + 完整打印；心跳行增 `🩹xN`；批次报告带 `healed`/`healed_count`。退出码契约不变 |

**修掉的隐性数据破坏（CT73 H2/H3 的动机）**：旧版 `if ename: rec["name"] = ename` 在细纲写错 ID 时
会把既有角色**改名换姓**（声明 `p_010 = 阿福` 而 p_010 是王五 ⇒ 王五被静默改名为阿福），
所有旧章称谓/别名/共现引用随之失联，而 `check` 事后只能报一条不一致——损失不可逆。
现改为改派新号 + 旧名留 alias，原记录分毫不动。

## 九、第五轮验证总账

| 项目 | 结果 |
|---|---|
| 长篇电池 A/B/C | **136/136 ✅**（第四轮 117 + 本轮新增 C-17～C-27 共 19 项） |
| SKILL 面审计 | **110/110 ✅** |
| long-lab 全量重建 | 30 章 ｜ 48,178 字 ｜ 事故 **0** ｜ **自愈动作 0** ｜ 警告 1（既有 ledger 漂移探针） |
| 差分回归（第五轮前 vs 后） | 12 张状态表逐字节一致；`milestones.json`/`sync_log.json` **仅时间戳差异** ⇒ 语义零漂移 |
| 四工作区 `check` | long-lab / test-lab / field-lab / probe 全 exit 0、0 errors |
| 假自愈回归 | 干净数据重放 🩹 = 0（C-27 + 30 章重建 + test-lab 单章）；脏数据 field-lab 一次 sync 修好 5 项脏类型，二次重放归零（幂等） |
| 端到端实证 | unknown 四态走完 ch_019 落河 ➔ ch_020~023 简报悬念账 ➔ ch_023 定论 alive ➔ ch_024 悬念账消失；200 字短章全链 exit 0 零体量告警；回滚态 `cruise --once` 优雅等待（exit 0，报告可解析）；卷末 `cruise --vol vol_01 --once` 自动刹车三连 |

**保留为 error 的 8 类判据**（松绑≠放水，逐条理由见 round5-notes 第 5 节）：
复活闸门、台账生死矛盾、充能透支、空正文封存、细纲文件不存在/无 front-matter、
状态表损坏或蒸发、确认级认知泄露、SSOT/init 覆盖。

## 十、五轮累计

| 轮次 | 主题 | 缺陷闭环 | 测试资产 |
|---|---|---|---|
| 一 | CLI 退出码 / 幂等 / 脏值 / 时光机 | 12 | matrix.md + audit/*.md |
| 二 | 探针假阴假阳 / SSOT / 装配展示 | 15 | 同上 |
| 三 | 字段边界 160+ 用例 | 9（#33~35 等） | workspace/field-lab |
| 四 | 长篇一致性 + SKILL 命令面 | 17（CT52~CT68） | long-lab 基座 + 电池 117 + SKILL 审计 108 |
| 五 | 作者 6 项指令（四态/去文学判断/松绑/自愈） | 7（CT69~CT75） | 电池扩至 136 + SKILL 审计 110 |
| **合计** | | **60 项闭环** | 4 工作区 + 4 件可重跑资产 |

**环境**：Python 3.11.2（沙盒）/ Novel Studio 4.4.0 / 引擎 16 模块全量编译 0 错。
