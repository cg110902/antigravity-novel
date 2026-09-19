---
id: "outline-{{slot:vol_id|vol_01}}"
vol: "{{slot:vol_id|vol_01}}"
title: "{{slot:vol_title|第1卷：卷名}}（《{{slot:title|书名}}》）"
schema_version: novel-studio.volume_outline/v3
target_chapters: 40
target_words: 80000
---

# {{slot:vol_title|第1卷：卷名}} · 分卷商业战略大纲（适配全题材）

> 💡 **【架构师导航 · 25~50万字长篇一致性卷纲契约】**
> 本卷纲是全卷（常规商业卷 25~40 章弹性，约 5~10 万字）的宏观航海图与长程因果脊柱。
> - **引擎命令契约**：执行 `python studio.py outline get ch_XXX` 时，引擎将自动定位并解析本文件中的 `### ch_XXX` 章节块，注入生成单章细纲任务卡。
> - **四分位潮汐法则**：执行【起 ➔ 承 ➔ 转 ➔ 合】，消灭平庸流水账。
> - **每章必具**：核心行动推进/本章看点 + 涉及实体 ID + 伏笔/信息差 ID + 章末断章刀口（Cliffhanger）。

---

## 🎯 一、 本卷商业承诺与核心卖点（Volume Hook & Promise）

- **本卷核心商业卖点（一卷一绝活）**：
  {{slot:vol_commercial_hook|自行设定：本卷独特的看点与商业爽点}}
- **本卷读者核心承诺（The Payoff）**：
  {{slot:vol_promise|自行设定：本卷终局将给读者带来的情感/情绪/成就兑现}}
- **核心对立冲突**：
  - **核心博弈方**：{{slot:conflict_parties|主角阵营 vs 外部阻力/竞争对手/核心反派，标明各方核心诉求}}
  - **核心危机倒计时（Stakes）**：{{slot:conflict_stakes|若不能在阶段期限前破局，主角面临的不可逆严重后果}}

---

## 🌊 二、 四分位戏剧潮汐节拍器（Four-Phase Tides）



- **Phase 1（ch_XXX ~ ch_XXX）**：
  - 核心功能：自行设定。
- **Phase 2（ch_XXX ~ ch_XXX）**：
  - 核心功能：自行设定。
- **Phase 3（ch_XXX ~ ch_XXX）**：
  - 核心功能：自行设定。
- **Phase 4（ch_XXX ~ ch_XXX）**：
  - 核心功能：自行设定。

(如果更多请自行补充)

- **Phase N（ch_XXX ~ ch_XXX）**：
  - 核心功能：自行设定。
  
---

### 🧵 本卷主支线交织追踪谱（Active Plot Threads · 贯穿长篇防迷航）

- **主线推进链**：
  - 【阶段一】{{slot:thread_main_p1|自行设定}} ➔ 
  - 【阶段二】{{slot:thread_main_p2|自行设定}} ➔ 
  - 【阶段三】{{slot:thread_main_p3|自行设定}} ➔ 
  - 【阶段四】{{slot:thread_main_p4|自行设定}} ➔ 【阶段N】（如有，请自行补充）
  
- **核心支线 1（关系/情感/羁绊线/分支剧情线）**：
  - 支线名称：{{slot:thread_sub1_name|自行设定}}
  - 交织区间：在 `ch_XXX` 破冰，在 `ch_XXX` 经历误解/共患难，在 `ch_XXX` 达成阶段性信任与背靠背。（自行设定）
- **核心支线 2（悬念/解密/成长线/分支剧情线）**：
  - 支线名称：{{slot:thread_sub2_name|自行设定}}
  - 交织区间：在 `ch_XXX` 获取第一块线索物，在 `ch_XXX` 揭开冰山一角。（自行设定）

---

### 👤 核心人物卷内弧光演变里程碑（Character Arc Milestones）

- **主角（p_001）卷内心理弧光**：
  - 【卷首起点】：{{slot:mc_arc_start|自行设定}}
  - 【卷中受震】：{{slot:mc_arc_mid|自行设定}}
  - 【卷末蜕变】：{{slot:mc_arc_end|自行设定}}
- **关键对手/搭档（p_002）卷内演变**：
  - 【卷首状态】：{{slot:p2_arc_start|自行设定}}
  - 【卷末质变】：{{slot:p2_arc_end|自行设定}}

---

## 📋 三、 本卷分章航标大表（Chapter Breakdown · 引擎精准定位源）

> ⚠️ **【格式规范】**：引擎依靠 `### ch_XXX: [章节名]` 识别章节，请勿更改标题前缀格式。
> ⚠️ **【卷末判定契约】（v4.3）**：巡航/卷末刹车以「最后一个**标题已填实**的 `### ch_XXX` 行」作为本卷终点；
> 标题行仍含 `{{slot:...}}` 的章节会被引擎视为"纯槽位预留行"**忽略**。因此：
> ① 本模板自带的 ch_001~003 示例行在填满前**不会**被误认作卷末；② 0B 必须按实际章节规划
> **续写并填实**直到本卷真正的末章行，否则卷末三连（rollup/reconcile/export）会提前或无法触发。

### 阶段一：自行设定（ch_XXX ~ ch_XXX）

### ch_001: {{slot:ch_001_title|自行设定}}（自行设定）
- **戏剧功能**：自行设定（通用全题材）
- **核心事件与看点**：{{slot:ch_001_event|自行设定}}
- **涉及核心实体**：{{slot:ch_001_entities|p_001(主角), p_002(对手), loc_001(对白地点)}}
- **伏笔与信息差**：{{slot:ch_001_lines|plant GUN-001(示例：关键信物/暗记), plant MIS-001(示例：对手误判主角底细/主角误判对手底细)}}
- **断章刀口**：{{slot:ch_001_cliff|自行设定}}

### ch_002: {{slot:ch_002_title|自行设定}}（自行设定）
- **戏剧功能**：自行设定
- **核心事件与看点**：{{slot:ch_002_event|自行设定}}
- **涉及核心实体**：{{slot:ch_002_entities|p_001, p_003(示例：第三方管事/负责人员), loc_002(深层场景)}}
- **伏笔与信息差**：{{slot:ch_002_lines|reveal MIS-001, plant KNO-001(示例：关键隐秘数额/真相)}}
- **断章刀口**：{{slot:ch_002_cliff|自行设定}}

### ch_003: {{slot:ch_003_title|自行设定}}（自行设定）
- **戏剧功能**：自行设定
- **核心事件与看点**：{{slot:ch_003_event|自行设定}}
- **涉及核心实体**：{{slot:ch_003_entities|p_001, p_003, it_001(核心证物/道具)}}
- **伏笔与信息差**：{{slot:ch_003_lines|plant GUN-002(示例：暗桩血书/加密信息), reveal KNO-001}}
- **断章刀口**：{{slot:ch_003_cliff|自行设定}}

<!-- （后续章节依次按此格式规划推进）（自行设定） -->
{{slot:phase_1_remaining_chapters|### ch_004: ... \n### ch_005: ... 等}}

---

### 阶段二：自行设定（ch_XXX ~ ch_XXX）

{{slot:phase_2_chapters|### ch_XXX: ... 规划至该阶段终点}}

---

### 阶段三：自行设定（ch_XXX ~ ch_XXX）

{{slot:phase_3_chapters|### ch_XXX: ... 规划至该阶段终点}}

---

### 阶段四：自行设定（ch_XXX ~ ch_XXX）

{{slot:phase_4_chapters|### ch_XXX: ... 规划至全卷终章，完成全卷收口与下一卷钩子，如有更多阶段请自行补充}}

---

## 🗝️ 四、 本卷核心长线伏笔与资产池总表（Volume Ledger Blueprint）

### 1. 核心伏笔清单（GUN / KNO / MIS）
- `GUN-001`：{{slot:v_gun_001|名称、埋设章节(ch_XXX)、预计引爆章节(ch_XXX)、核心因果}}
- `GUN-002`：{{slot:v_gun_002|名称、埋设章节(ch_XXX)、预计引爆章节(ch_XXX)、核心因果}}
- `KNO-001`：{{slot:v_kno_001|核心隐瞒秘密/知情差}}
- `MIS-001`：{{slot:v_mis_001|核心认知偏差/外界误解}}

### 2. 本卷核心资源与道具流转预设
- `it_001`：{{slot:v_it_001|核心资产/道具名、初始持有人 -> 最终归属、代价与限制}}
