# 测试发现清册 — 《反重力小说引擎》全面测试

> 本文件记录本轮测试自基线（152 项回归全通过 / 两书 check 0 errors）之后，
> 新发现的疑似缺陷与遗留问题。每项含：现象 / 复现 / 根因 / 严重度 / 处置建议。
> 规则：**不修源码让测试通过**；只记录、复现、评估、建议，最终是否修交由项目方决策。

---

## 阶段一：基线审查（源码通读 + 方法论扫描）

### 基线事实
- 回归 `python3 tests/regression_test.py` → **152 项 / 0 失败**。
- `workspace/lantern`（古代悬疑 16 章）与 `workspace/testbook`（都市异能 2 章）check 均 **0 errors**。
- 实测 `python studio.py --version` → `4.3.2`，而 `engine/config.py` 注释与 BUG#36 修复均标注 `v4.3.3`。
  版本常量与修复注记不同步（NEXT_TESTING.md 事项 3 已预判），**确认属实**。

---

## FIND-A【P0 · 已确认】提及他人名仍不触发「疑议级同场泄密」——认知盲区探针漏判

- **现象**：盲区角色 B 在场，角色 A（知情人）当众对 B 说出 B 本人的机密关键词，
  探针**静默通过**（既非 error 也非 warning）。契约注释声称这属于 `suspected`。
- **根因**：`engine/probes.py::probe_epistemology_leaks` 内层循环：
  - `if speaker is None or owner_in_scene:` 命中后 `break`（正确）；
  - 但 `speaker is not None and not owner_in_scene` 时**直接落空**（退出内层 for）——
    没有任何分支处理「说话人归属明确、但盲区角色在场」这一最危险的第三人称场景。
  - 更糟：命中该空路径时 `break` 的是**内层 for**，但代码顺序上是先 `continue` 命中后
    才到 `break`……实测确认：只要 owner 在场，无论谁说都不再产生任何提醒。
- **复现**：
  ```python
  from engine.probes import probe_epistemology_leaks
  txt = '“你的秘密就是：灯市案那晚你也在场。”裴砚对沈拂云说。'
  blind = {"p_003": ["灯市案幸存孤儿"]}   # 沈拂云 = p_003
  r = probe_epistemology_leaks(txt, blind, name_by_id={"p_001":"裴砚","p_003":"沈拂云"},
                               present_ids=["p_001","p_003"])
  # 期望 suspected=1（他人当众提及），实际 suspected=0
  ```
- **严重度**：P0。认知盲区防透视是**阻断级探针**（error），漏此分支意味着探针既放跑了
  真泄露，也放跑了应提醒的场面——这是它唯一的职责。
- **处置**：在 `probe_epistemology_leaks` 补「speaker 归属明确但 owner 在场」→ suspected 分支。
  注意与 BUG#4/#32/#33/#34 的历史修复口径对齐（在场名单 → present_ids 权威）。

---

## FIND-B【P0 · 已确认】dump_mini_yaml 转义 → parse 不反转义，proposal 回写污染锁定事实

- **现象**：`proposal auto` 用 `dump_mini_yaml(fm)` 重写细纲，凡是含**半角双引号 / 反斜杠 /
  换行**的字符串（如伏笔 desc、locked_facts、want/fear、对白引用），回写后会被 `\` 污染——`
  半枚"灯签"` 变成 `半枚\"灯签\"`。sync 入账后，**锁定事实/伏笔 desc/称谓**全部带字面反斜杠，
  并沿 pack / simulate impact / export 前情提要一路扩散。
- **根因**：`dump_mini_yaml` 的 `_yaml_str` 做了 `\"`、`\\`、`\n→\\n` 转义（严格转义契约），
  但 `parse_mini_yaml` 的 `_parse_scalar` 只 `strip` 引号**不做反转义**。
  序列化器与解析器不是互逆对——给出带转义的输出，却读不回原串。
- **往返不一致清单**（fuzz 实锤，`/tmp/fuzz_parser.py`）：
  1. `["a", "b"]` 顶层 int 列表 → dump 出 `- 1\n- 2`，parse 返回 `{}`（结构丢失）。
  2. 字符串含 `\n`、`\\`、`"` 时往返不一致（转义污染）。
  3. `True/False/None` 在列表中被 dump 成 `True/False/-`，parse 侧 `_parse_scalar` 不认大写
     `True`（只认小写）。
- **严重度**：P0。锁定事实是 AGENTS 公理五「法定事实不可篡改」的载体，污染即事实失真。
- **处置**（三选一，按成本）：
  1. `parse_mini_yaml` 在 `_parse_scalar`/`_split_key_value` 引号剥离后做反转义
     （`\\"`→`"`、`\\\\`→`\\`、`\\n`→`\n`），与 `_yaml_str` 成为互逆。
  2. `proposal_auto` 回写细纲时改用「只改 new_entities/state_deltas 两节」的定点写回，
     避免整份 frontmatter dump（但 dump/parse 不互逆是更底层问题，建议同时修）。
  3. 尽快补回归锁：`parse_mini_yaml(dump_mini_yaml(x)) == x` 往返断言（含转义字符样本）。

---

## FIND-C【P2 · 已确认】is_deceased 的 L1 兜底词表只有 5 词，旧档「病故/牺牲」死者判活

- **现象**：旧档案（无 `life_status` 契约）角色 `condition="病故于旧货店"`：
  - `is_deceased()` → **False**（判活）
  - `get_death_chapter()` → `ch_004`（判死）
  - `_infer_life_status()` → `deceased`（判死）
  同一段文字三个入口三种结论。
- **根因**：`engine/state.py::is_deceased` 的 L1 兼容兜底只枚举
  `("阵亡","永久湮灭","身死","气绝身亡","被斩杀")`，nwhile `_DEATH_KEYWORDS` 有 40+ 词。
  BUG#47 分层重构的注释明确说「旧档无契约时才走 condition 兼容兜底」，
  但这条兜底与 L2 词表再次分裂（正是 BUG#15 两处词表漂移的旧病）。
- **严重度**：P2（依赖「无 life_status 契约的历史脏档」这一前置；新数据走升格通道无此问题，
  且当前两本正本书都无此脏档）。
- **处置**：让 `is_deceased` 的无契约兜底复用 `_infer_life_status(condition) == "deceased"`
  单一真值函数（与 BUG#47 的「消除词表分裂」同一方法论），并加反事实守卫。

---

## FIND-D【P2 · 已确认】milestone achieve 的 `-c/--chapter` 参数被静默丢弃

- **现象**：CLI 定义了 `p_ms_ach.add_argument("-c","--chapter")`，但调用
  `milestone_achieve(ws, args.milestone_id)` 从未传 `args.chapter`。
  写入 milestones.json 的 `achieved_ch` 字段永远缺失；`trace ms_XXX` 中
  「达成记录：已于第 X 章兑现」永远不显示。
- **根因**：`engine/ops.py::milestone_achieve` 签名只有 `(workspace, milestone_id)`，
  实现中 `achieved_at` 用 `datetime.now()` 而没有 `achieved_ch`。CLI 与 ops 契约脱节。
- **严重度**：P2（纯展示性字段，不影响裁决）。
- **处置**：给 `milestone_achieve` 加 `chapter` 参数、落盘 `achieved_ch`，
  并让 `id_tracker.trace_id` 的 `achieved_ch` 展示读取一致（它读的是 `achieved_ch`，
  bug 恰在此：写入字段与读取字段对不上）。

---

## FIND-E【P3 · 已修复】版本常量与修复注记不同步（本轮升级 4.4.0）

- **现象**：`engine/__init__.py:__version__` 曾停留在 `4.3.2`，而 BUG#36 及 config.py 等
  多处注记 `v4.3.3`，`check` 的版本一致性巡检长期失效。
- **处置**：v4.3.3 已由前序会话对齐；本轮 FIND-L/I/J/K/SYNC/parser 系列修复合计升版
  `__version__ = "4.4.0"`，并保持修复注记与版本号同源（后续修复需同步升版，避免复发）。

---

## FIND-F【P3 · 已在回归中验证通过，存档】sync 中断安全（NEXT_TESTING 方案 A 的实测状态）

- 单文件原子写（tmp+fsync+os.replace）真实有效；中断后补跑 sync 逐字节一致（幂等兜底）。
- 已知缺口：14 次独立 `_save_json` 非跨表事务，需「sync_log 最后落盘」的契约 + 哨兵文件。
  本次**未做 20 中断点全覆盖**（见计划），仅记录为待补项。

---

## 阶段二：parser fuzz（`/tmp/fuzz_parser.py`）摘要

- 深嵌套 x300（字典）、10 万字符单行：**无栈溢出、无卡死**，解析正常。
- `007`→7、`+86`→86（前导 0/正号被吃掉）、`1e5` 保持字符串：与标准 YAML 差异，**写进已知差异**。
- 「灯#签」→「灯」（值内 `#` 被当注释）：对「人名/物名含 `#`」是隐患，属 parser 已知简化。
- tab 缩进 → `{'a': []}`（列表被吞）：tab 不再受支持，应文档化。
- 全角冒号 `键： 值` → `{}`（不支持全角键值分隔，静默返回空 dict，**静默部分成功**，需警惕）。
- 顶层列表 dump 往返丢失结构（见 FIND-B）。

---

## FIND-G【P2 · 实战确证】mini-YAML 不支持 flow mapping（inline dict）

- **现象**：细纲 `state_deltas.character_status` 写 `"p_005": {"life_status": "deceased", "condition": "溺毙"}`，
  sync 后 `condition` 字段被原样存成 JSON 字面量字符串
  `{"life_status": "deceased", "condition": "溺毙"}`，污染 state 数据。
- **根因**：`parse_mini_yaml._parse_scalar` 把花括号整串当标量；而 state.py 的「显式契约」
  分支（`if isinstance(s_val, dict)`）对这类字符串永远不可达，显式 death/missing 契约实际从未生效。
  本例 life_status 最终能正确落为 `deceased`，纯属 `_infer_life_status` 撞上了串里的英文 `deceased` 关键词，
  属**歪打正着**；若作者写的是 `{"life_status": "死亡"}`（无英文关键词），推断分支也不可达，反而会漏判。
- **严重度**：P2（显式生死契约通道失效，有漏判风险；数据字段污染）。已手工修正 p_005.condition。
- **处置建议**：① 文档化「character_status 不支持 inline dict，请用独立 key/文本值」；
  ② 或让 parser 识别 `{...}` flow mapping；③ 至少在 check 里对 condition 含 `{` 的值告警。
- **附带实测（同源）**：debts 的 `target_char` 若写势力名「灯火司」，check 3.7 报「恩怨承受方
  不存在」（`_known_person` 只认人物，不认势力/据点）。已改为写势力首脑「萧烜」。
  此为合理设计还是缺口待定，先记录。

---

## 实战流水线附加确认（workspace/guixu · 前 4 章）

- Stage 0 全链路：六表 + 双角色卡 + 两配角卡 + 双大纲填实 → **八表通电**（persons/items/
  factions/places/current/ledger+locked 经细纲）+ 里程碑 → check 0 errors 0 槽位。
- 关键验证点：细纲 `new_entities` + `locked_facts` + `state_deltas.character_status` 死亡登记链路
  全通，接口三观：已故黑名单正确拦截 p_005，恩怨账正确展示 p_001→萧烜，弧光/关系/伏笔/道具
  逐章入账无漂移。
- 探针实战：认知盲区、称谓缺位（顾伯→阿离 / 陆离→萧大人）、伏笔落地（GUN-001 落地不足）
  均被正确捕获并修正后转绿；probe 的红绿灯可信度高。
- `id_tracker` 发号器扫描范围：state 各表 + `outlines/**/beats/*.md` + characters/entities/bible/
  worldview/docs，**不扫描 `outlines/vol_XX/outline.md`**——main_plot/vol_outline 里预埋的
  GUN/KNO/MIS/it_XXX 编号不在水位视野（简报 ID 速查因此可能与既有大纲撞号，需留意）。

---

## 本轮（第二阶段）执行与修复记录

> 上轮纪律为「只记录不改源码，修否交项目方决策」。本轮经用户明确授权
> 「有问题（包括历史问题）直接改」，故对 FIND-A~G 逐一实测复核并落地修复，
> **全部改动必须回归 152 项全过 + 三本书（guixu/lantern/testbook）check 0 errors**。

### 复核结论（逐项定论）

| 编号 | 复核结果 | 处置 |
|---|---|---|
| FIND-A | **已被修**（实测 `suspected_count=1` 正确触发） | 无需再动 |
| FIND-B | 仍属实，且 fuzz 扩挖出 **3 个深层同族 bug**（见 FIND-H/I/J/K） | 已修 |
| FIND-C | 仍属实 | 已修（复用 `_infer_life_status` 单一真值） |
| FIND-D | 仍属实 | 已修（`achieved_ch` 落盘 + CLI 传参） |
| FIND-E | 仍属实 | 已修（`__version__` 4.3.2 → 4.3.3） |
| FIND-F | 上轮只记录方案 | 本轮**补齐并实修**（见 FIND-SYNC） |
| FIND-G | 仍属实（flow mapping 不支持） | 已修（parser 支持 `{...}` inline dict） |

### 修复详情

**FIND-C 修复**（`engine/state.py::is_deceased`）：无契约兜底改为
`return _infer_life_status(condition) == "deceased"`，与 L2 升格通道共用单一真值函数，
消除「同一段文字三入口三结论」。回归测试 BUG#47 六项裁决语义 + L2 升格全过。

**FIND-D 修复**（`engine/ops.py::milestone_achieve` + `engine/cli.py`）：
签名加 `chapter` 参数，落盘 `achieved_ch`（兼容 `ch_010` 与裸数字两种形态，归一为
`ch_XXX`）；CLI 由 `getattr(args, "chapter", "")` 传入。`trace ms_XXX` 从此能显示
「已于第 X 章兑现」。

**FIND-E 修复**（`engine/__init__.py`）：`__version__ = "4.3.3"`。

**FIND-G 修复**（`engine/parser.py`）：新增 `parse_flow_mapping` 与 `_split_flow_items`
（尊重引号内逗号与嵌套括号；兼容全角/半角冒号），`_parse_scalar` 在 dict 推断前优先
识别 `{...}`。实测 `character_status: {"p_005": {life_status: 死亡, condition: "病故"}}`
正确解析为 dict，显式生死契约通道从此真正生效（不再靠英文 `deceased` 关键词歪打正着）。
`tension: "30"` 等既有模板引号数值**保持字符串**，向后兼容不受影响。

---

## FIND-H【P1 · fuzz·已修】parse_mini_yaml 不识别 dump 输出的裸 `-` 复合列表项

- **现象**：`parse_mini_yaml(dump_mini_yaml({"a": [1, {"k": "v"}]}))` 丢结构。
  dump 对「list 内嵌套 dict/list」输出裸 `-` 标记行（`{prefix}-`），但 cleaned_lines
  已 `strip()`，单字符 `-` 不匹配 `startswith("- ")`——该复合项被静默跳过（结构错位）。
- **根因**：`parse_mini_yaml` 的 list 分支 `is_list = curr_line.startswith("- ")` +
  循环内 `line.startswith("- ")` 两处都遗漏「裸 `-`」。
- **修复**：`is_list` 与 list-item 判断均接受 `line == "-"`，命中即递归解析下一层
  （`ind + 2`）并 `continue`，不动后续 `- k: v` 分支。

---

## FIND-I【P1 · fuzz·已修】`_strip_comment` 不识转义引号，`"a\"b#c"` 被当注释截断

- **现象**：dump 出的 `"语头\"b#照"`，parse 时 `#` 被误当行外注释，串被截成 `"语头\"b`。
- **根因**：`_strip_comment` 的引号跟踪把序列化器转义出的 `\"` 误当真正的边界引号，
  导致引号状态提前翻转，其后的 `#` 落在「引号外」。
- **修复**：`_strip_comment` 增加「反斜杠 + 下一字符」一并原样保留的转义感知，
  转义引号不再切换引号状态。

---

## FIND-J【P1 · fuzz·已修】dump 顶层 list 漏处理 None → 值丢失成空行

- **现象**：`dump_mini_yaml([[True, None, "x"]])`，`None` 落进 else 分支被 dump 成裸 `-`，
  parse 后变空结构（`None` → `[]`/`{}` 静默变形）。
- **根因**：`dump_mini_yaml` 的顶层 list 分支对 `item is None` 无专门 case。
- **修复**：显式 `- null`（与 dict 值分支一致）。

---

## FIND-K【P1 · fuzz·已修】引号边界扫描不识转义引号，`"尸瘸'\\":"` 被误判 dict-item

- **现象**：list item 形如 `"尸瘸'\\":"`（内容含转义双引号），parse 用 `find(q, 1)`
  找闭合引号，把转义出的 `\"` 误当结尾，尾随的空值 `":"` 使整串被误判为 `key: value` 的
  dict-item，原字符串变成 `{key: ""}`。
- **根因**：`_split_key_value` 与 list 分支 dict-item 检测都用 `str.find(q)`，
  不感知「转义引号前面有奇数个反斜杠」这一边界规则。
- **修复**：新增 `_find_unescaped(s, ch, start)`（数反斜杠奇偶），替换两处 `find(q, ...)`。

**fuzz 证据**：修复后 `parse_mini_yaml(dump_mini_yaml(x)) == x` 对**随机嵌套 dict/list/
中文字符串（含 `" \ \n \t # : ， { } [ ] '` 全字符集）15 万轮顶层 dict 往返 0 失败**。

---

## FIND-SYNC【P0 · 实测+已修】sync 跨表非事务写：哨兵 + 落盘顺序回归锁

- **现状实锤**（对齐 NEXT_TESTING.md 修订版方案 A）：
  - `_save_json` 单文件原子写（tmp + fsync + os.replace）真实有效。
  - 但 sync 一次入账是 **16~17 次独立落盘**，非跨表事务；中断在任何两次写盘之间，
    台账处于跨表不一致状态。
  - 实测**落盘顺序**：`.sync_pending → persons → items → places → factions → persons →
    items → places → lines → ledger → debts → relations → synopsis → timeline →
    current → co_occurrence → entity_timeline → history/ch_XXX →（回 ops）sync_log →
    project.json。**注意 project.json 才是真正的最后写**（sync_log 倒数第二）——
    NEXT_TESTING 断言「sync_log 恰好在最后写」与实际代码不符；哨兵机制恰好补上了
    这个窗口（中断会被 check 抓到，而非静默错账）。
- **修复**（A4 方案 1 + 实测）：
  1. `engine/state.py`：新增 `.sync_pending` 哨兵三函数 `write/clear/read_sync_sentinel`；
     `_save_json` 累计「事务写盘计数」（哨兵自身不计）。
  2. `engine/ops.py::sync_chapter`：入账前立哨兵；`except BaseException` 统一按
     `_save_count() == 0` 决定是否清哨兵——**零写盘阻断（预检业务阻断 / 坏表隔离故障）
     清哨兵；已有写盘后中断保留哨兵**；正常收尾清哨兵。
  3. `engine/check.py`：新增 1.5 节「sync 事务哨兵巡检」，哨兵残留报阻断 error +
     补跑补救命令。
- **20 中断点全覆盖实测**（同进程 monkeypatch `_save_json` 逐个注入 KeyboardInterrupt）：
  16 个业务写盘点全部通过——每一中断点后：(a) 哨兵正确残留；(b) `check` 正确报
  「上次同步未完成」；(c) 补跑 `sync --force` 后台账数据与干净基线**逐字节一致**
  （剔除 `timestamp/forced/synced_at` 等纯元数据场）；(d) 哨兵正确清除。
- **结论**：中断安全从「顺序巧合」变成「显式可检测 + 幂等重放复原」的机制保证。

---

## 阶段三：其它高优先级验证（本轮完成）

**长程 60 章压测**（`/tmp/longrun`，`_cruise_fixture.py` 生成 60 章 → `cruise --once`）：
- 台账体积随章数**线性**增长（timeline 60 条 / co_occurrence 60 键 / persons 62），
  **无平方级膨胀**；`history/` 60 个快照文件 ~4.4MB（可预期，靠 rollup 折叠）。
- `state rollup` 正确折叠为 `rollup_vol_01.json`（chapters_count=60, total_words=10980），
  卷末自动刹车 + reconcile + export 全链路触发成功。
- 全书 `check` 0 errors（221 处槽位 warning 来自 fixture 生成物，非引擎缺陷）。

**config set → 探针联动实测**：`config set dialogue_ratio "[10,95]"` 后高对白正文由
`passed=False` 变 `passed=True`，`words_per_chapter` 亦真实生效并落盘 `project.json.engine`。
（补充验证了 NEXT_TESTING P1-5；未发现「声明但未消费」的配置项。）

**evolution 全链路**：`simulate impact`（事前因果监门）十维度扫描已由 BUG#19 覆盖；
「真正执行反转」= snapshot → 手改台账 → check 平账 → 补回归，回归 11 节已实测
（复活角色遗留死亡弧光被拦 / 假死放行 / 快照可完整复原）。

**CLI 参数「收而不用」AST 扫描**：`--no-digest` 等具名参数均已消费（scanner 的 dest 名
转换产生误报，经逐项核对无真实遗漏）。

---

## 阶段四：字段「录入→存储→查询→同步」全链路审计（本轮完成 · FIND-L~M）

用户续订指令要求：实测长篇一致性的核心链路——各实体字段（字段值/状态变化）的
**录入→存储→查询→同步**一致性，并验证本地命令是否真生效、有无假阳性。

### 架构确证（用户「双台账」疑问的答案）
- **无 SQL、无双台账**。全项目 grep `sqlite|sqlalchemy|.db|database|cursor|CREATE TABLE|INSERT INTO|SELECT..FROM`
  零命中；`engine/ledger.py` 仅 `StateLedger = StateManager` 别名。
- 单一台账三层架构：SSOT = 细纲 `beats/*.md` frontmatter → 派生 `state/*.json` 16 张表 →
  查询侧 `ask/trace/id list/cockpit/export`。SQL 二台账不存在。

### FIND-L【P0 · 实测+已修】schema 承诺字段在 sync 落账时被**静默丢弃**，check 全程假阳性

- **现象**：在细纲 frontmatter 显式声明的字段，sync 落账后大面积丢失或被默认值覆盖：
  - 人物 `life_status: deceased` → 恒存 `alive`（开篇死者静默复活）；
    `faction/realm/tier_rank/aliases/need/lie/attitude/summary…` → `None`。
  - 道具 `max_charges/tier_name/condition/cost_per_use/tier_rank` → `None`。
  - 地点 `danger_tier: 9` → `None`；势力 `leader/headquarters/scale_tier` → `None`。
  - 恩怨 `status: settled` → 恒 `unpaid`；情感 `affinity/trust` 显式值 → `0/50` 被覆盖；
    伏笔 `evidence`（schema/synopsis 承诺的原文证据切片）→ 永为 `""`。
  - **全部丢失场景下 `check` 一律 passed=True（假阳性确凿）**——长篇一致性在「录入→存储」
    第一跳就静默断裂，且无任何告警。
- **根因**：`engine/state.py::apply_chapter_delta` 对新实体/在场人只硬编码 ~14 个字段的
  白名单并 `get(默认)`，白名单外的 schema 契约字段（`engine/schema.py` 逐一承诺）被整段
  丢弃；`life_status` 被硬编码 `"alive"`，`debts.status` 被硬编码 `"unpaid"`。
- **修复（v4.4.0 FIND-L）**：新增 `_PERSON/_ITEM/_PLACE/_FACTION_FM_FIELDS` 白名单与
  `_paste_declared()`（`in` 判断：仅细纲**显式声明过**的键透传，未声明仍走产品默认）。
  覆盖 new_entities 四表 + present_characters 更新路径 + life_status L1 归一化落账 +
  debts.status 归一化透传 + relations affinity/trust 显式覆盖 + 伏笔 evidence 落账。
- **实证**：27 项字段声明→落账全部一致（0 失败）；`trace`/`ask` 能读到新落账字段；
  死亡契约跨章生效（死后登场被正确阻断）；`--force` 幂等重放逐字段不变。

### FIND-M【P2 · 已处置】「记录但无人查」字段全链路补齐 + rollup 措辞钉正

**处置结论（v4.4.0 FIND-M 落地）**：不做 schema 删字段（会破坏「契约可演进、旧档可迁移」的
前瞻设计），改为「**存储已有 → 查询补齐**」，把 true 死字段收敛为 0：

- `engine/id_tracker.py` trace 补齐 person（tier_name/tier_rank/power_benchmark/injury_level/
  injury_desc/renown/faction/attitude/aliases/micro_actions/dossier/need/lie）、
  item（max_charges/cost_per_use/tier_rank/tier_name）、faction（scale_tier/core_assets/diplomacy）、
  place（danger_level/danger_tier/sensory_anchor）——均有值才显、不造噪音。
- **顺手修一个显示 bug**：trace person 旧版 `"realm": p_data.get("tier_name") or p_data.get("realm")`
  让 realm 被 tier_name 抢占，FIND-L 已让 realm 真正落账却永远查不到；现 realm 优先、tier 独立成列。
- **`sensory_anchor`** 已在 pack / check / probe_grounding 消费，此前误判为死字段，修正名录。

**rollup 折叠语义钉正（v4.4.0）**：实测确认 rollup 是**只读归档副本，从不删减 timeline.json**
（timeline 是 ask/trace/cockpit/export 的活动数据源）。已把 `cli.py` 命令描述与 `ops.py`
docstring 的「防长篇膨胀」措辞更正为「跨卷总览与封存的追加式归档」，避免名不副实。
**字数口径（BUG#35）**：本轮收口——新增 `count_prose_words` 单一口径（剥 front-matter/标题行），
export 改为引用 sync_log 入账字数（单真值派生）。三书 project == timeline == export 完全一致
（guixu 17282 / lantern 14000 / testbook 1583 各自三处全等）。

### FIND-N【P0 · 实测+已修】check 把合法「死里逃生」误判为「台账生死自相矛盾」（假阳性）

- **现象**：角色状态写「重伤，几乎死了，被救回」，life_status=alive 正常落账，
  但 check 报 error「arc_history 记录死亡事实而 life_status 在世」——一本完全正常的书被阻断。
- **根因**：`get_death_chapter` 用**裸 `_DEATH_KEYWORDS`**匹配 arc_history.status_out，
  与 `_infer_life_status` 的反事实守卫（「几乎死了/装死/假死」优先排除）不同源——两套词表漂移，词表反而命中「死了」。
- **修复（v4.4.0 FIND-N）**：`get_death_chapter` 统一走 `_infer_life_status`；「deceased 兜底取最晚露面章」补
  is_deceased 前置（活人不再返回 last_seen_ch）；check 的裸词表预筛一并移除。

### FIND-O【P1 · 实测+已修】短机密 4 字滑窗过度泛化，无关对白被判「确认级泄密」（假阳性）

- **现象**：盲区机密写成短句「他其实不是人」，4 字滑窗切出「他其实不/其实不是/实不是人」等
  公共短语；盲区角色说一句「他其实不是故意的」就被判**确认级泄露（error 阻断）**。
- **根因**：`_secret_keywords` 对 ≥5 字机密一律切 4 字窗当 strong——短句没有足够特异度。
- **修复（v4.4.0 FIND-O）**：4 字滑窗只在 **≥8 字**长机密上启用；短机密仅全串为 strong，
  同义改写降级 suspected 交 Auditor。真泄密不受影响（原文直说仍确认级）。

### FIND-P【P0 · 实测+已修】实体建档后中期演化被静默丢弃（长篇一致性「状态变化」命门）

- **现象**：势力「灯火司」首章建档 leader=萧烜，后续章节 new_entities 声明同 ID leader=裴照
  （易主、义军易帜、道具易主等核心剧情变化）——**整条被静默丢弃**，台账永远停在旧值，
  且 check 全程放行（假阳性）。这是长篇一致性的最致命断裂：状态变化无法存储。
- **根因**：`apply_chapter_delta` 对 new_entities 用 `if eid not in xxx_db` 一票否决，
  已建档实体直接 `continue`，无任何更新通道；同义的新实体声明被 BUG#40 的 check 前置拦截，
  但「对既有实体的字段更新」本不属于「新实体」语义，属于设计缺位。
- **修复（v4.4.0 FIND-P）**：四类实体（person/item/place/faction）已建档时，对**显式声明**的
  档案字段做原地更新+章序单调守卫（见 FIND-Q）。`holder/charges/status/durability` 等
  有独立 delta 通道的字段不在此覆盖（避免破坏 BUG#1 幂等）。

### FIND-Q【P0 · 实测+已修】--force 重放旧章把 last_seen_ch 与字段演化回退（时间线污染）

- **现象**：ch_002 已入账角色 last_seen_ch=ch_002，`sync ch_001 --force` 后回退成 ch_001；
  势力易主后的 leader 也会被旧章 new_entities 携带的旧值覆盖回退。
- **根因**：`last_seen_ch` 无单调守卫；new_entities 更新（FIND-P 修复引入后）无「演化水位」。
- **修复（v4.4.0 FIND-Q）**：persons/items/co_occurrence 的 last_seen_ch 一律单调不倒退；
  新增 `_entity_update_guard`/`_mark_updated`，实体字段演化记录 `updated_ch` 水位，
  旧章重放不覆盖比水位更晚的演化值。

### FIND-L3【P2 · 实测+已修】生死灰区「判不出来」的静默缺口已闭环（死板词表治理最终件）

- **背景**：用户点名「死板问题」，上轮已论证「凡硬裁决结构化、词表只留提醒层」。
  本轮审计出该架构的**最后一处静默缺口**：sync 落账时 `state_deltas.character_status`
  的自由文本，`_infer_life_status` 判不出来（命中词表但被反事实守卫拦截，或隐喻死活）
  时**完全无反馈**——作者以为引擎替他做了生死判定。
- **修复（v4.4.0 FIND-L3）**：
  1. `state.py` 落账路径——显式 `life_status` 非法包 + 描述命中死亡词表被守卫拦截 → warning；
     纯自由文本命中词表被守卫拦截（几乎死了）→ warning「判定为未死亡，若非此意请显式 declared」。
  2. `check.py` 枚举巡检——识别「显式生死契约的中文写法落库但未归一化」并给精确收敛提示。
- **三路径口径（回归锁第 21 节）**：灰区隐喻落账不判死（静默=交 Auditor）✅；
  反事实「几乎死了」不判死且提示 ✅；明确「气绝身亡」固化 deceased 无语噪 ✅。

### 【架构答卷】汉语词表「死板判断」如何彻底解决（用户问题 2 的结论）

审计全部 17 处汉语词表点位后，结论：**凡做硬裁决的判定点均已结构化，词表只留在提醒层**，这正是「词表不可能穷举」的根本解法：

1. **生死（硬裁决）**：`is_deceased` 只信 `life_status` 结构化枚举（L1 唯一真值）；自由文本推断
   （`_infer_life_status`）只在 sync 落账时**一次**执行、且含反事实守卫（几乎/装死/假死优先排除），
   推断不了就**提醒作者补契约**、绝不代替作者裁决。「倒在雪地里再没起来」这类不可穷举写法漏了，
   后果只是一句可忽略的 warning，不会造成死者复活事故。
2. **身份/引用（硬裁决）**：check 的未定义 ID / 撞号阻断走结构化 ID 校验，不做文本匹配。
3. **认知泄露（硬裁决 confirmed）**：keywords 靠 n-gram 而非词表；本轮 FIND-O 已把短句滑窗过度泛化收窄。
4. **讲话人归属、称谓落地、物象落地、死亡提醒、泛称停用**（提醒层）：全是 warning 级，漏判只多/少一句提示。
5. **立场**：语义等价（孤儿≈遗孤）本质是**语义判断**，确定性地做会双输（误报+漏报），正确边界是
   引擎判定降级 suspected 交 Auditor 终审——契合「引擎是仆人而非监工」公理。

### FIND-R【P2 · 实测+已修】提醒层词表两处假阴性（单字机密静默 + 修辞『死』吞真死亡）

- **现象一**：盲区机密为**单字**（如「灯」）时，`regex {2,}` 连 weak 词都切不出，
  盲区角色亲口说出该字**完全静默**（confirmed=0/suspected=0）——假阴性。
- **现象二**：`probe_unregistered_fatalities` 收集「已登记死亡」时对 locked_facts 用
  `'死' in text` 单字匹配，「沈决发誓死不承认那笔旧账」的修辞义命中，把活人吞进
  acknowledged_deaths，之后他的**真正死亡描写**被判「已登记」而永久不漏提醒。
- **修复（v4.4.0 FIND-R）**：机密切词降到 `{1,}`（单字只作弱提示、不升级 confirmed）；
  locked_facts 的死亡判据去掉宽泛单字「死」，改明确的死亡措辞（阵亡/死亡/身亡/击杀/被杀/已死/毙命/殒命）。
- **求边界**：这是提醒层的最后一类假阴性——不会阻断也不会篡改台账，后果只是少一句提醒；
  修掉后提醒层的「可穷举性缺口」全部收敛到「明确措辞才判定」的确定性边界。

### 【查漏结果】本轮补测过、确认自洽的项（P0-2 / P1-4 / P1-7 / FIND-B 死路径）

- **P0-2 多卷 rollup**：vol_01+vol_02 各 5 章实测，两卷 rollup 之和 == timeline（1830 字 / 10 章）✅。
  但发现两个口径观察：export 1790 vs timeline 1830 是 BUG#35（标题行口径差，不影响正确性；**已于本轮收口**，见 FIND-M 节）；
  **rollup 从不削减 timeline**（只多写 rollup 文件），NEXT_TESTING「折叠防膨胀」名不副实——需项目方定口径。
- **P1-4 evolution 砍角色**：手工删 persons 后，check 正确报「关系对 p_001->p_002 引用断裂」error，
  验收闸门有效；trace 对已删实体正确返回「未检索到」。
- **FIND-B 顶层 list**：确认是**死路径**（全项目 `dump_mini_yaml(fm)` 唯一调用在 ops.py:1057，
  fm 恒为 dict；值位置嵌套 list 往返已 0 失败）——无需 top-level list 反转义，建议结案。

---

## 处置纪律（对齐 NEXT_TESTING.md 第四节方法 4）

- 影响硬裁决（阻断/入账/删除）→ 必须确定性：FIND-A（探针漏报）与 FIND-B（事实污染）属此列。
- 只影响提醒/展示 → FIND-C/D/E 缓修即可。
- 破坏性测试一律在 `/tmp` 隔离副本进行，未污染 workspace/{guixu,lantern,testbook} 正本。
- 每处源码修复必须过：`python3 tests/regression_test.py`（152 项）+ 三本书 check 0 errors。
