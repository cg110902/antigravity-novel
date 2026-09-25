---
# ==============================================================================
# 💡【全题材通用编剧细纲契约 · Universal Beats Frontmatter】
# 🔴 核心必填：chapter_id, volume_id, title, chapter_type, timeline, location,
#             present_characters (id+name+role+want+fear+status_in), 断章刀口。
# 🟢 动态增量【按需填报·无变动保持空列表[]】：foreshadowing_deltas, state_deltas,
#                                         relation_deltas, new_entities, locked_facts。
# 🌐 规范：一句话原则（字段 ≤ 15字），严禁小作文，动态增量按需按实申报。
# ==============================================================================
chapter_id: "{{slot:chapter_id|ch_XXX}}"
volume_id: "{{slot:volume_id|vol_01}}"
title: "{{slot:title|章节名}}"
chapter_type: "{{slot:chapter_type|破局}}" # 节奏遥测: 破局/铺垫/过渡/爆发/回收/余韵
timeline: "{{slot:timeline|时空时间}}"
location: "{{slot:location|核心场景名}}" # 推荐格式：“主场景·微观现场”（如：北灵城·楚宅灵堂）

# 0. 航标锚定：一句话核心目标
narrative_spine:
  thread: "{{slot:thread|主线·核心冲突推进}}"
  volume_phase: "{{slot:volume_phase|阶段一：开局破局}}"
  macro_goal: "{{slot:macro_goal|本阶段跨章核心战役/剧情目标（≤25字）}}"
  active_milestone: "{{slot:active_milestone|无}}"

# 1. 场景微观物理规则与感官锚点（视觉/听觉/温度触感，严禁嗅觉）
scene_environment:
  sensory_focus: "{{slot:env_sensory|核心感官聚焦：视觉、听觉、温度触感（严禁嗅觉，≤30字）}}"
  environment_rules:
    - "{{slot:env_rule_1|空间物理规则或限制（如：灵堂禁武/宵禁封锁/阵法压制，≤20字）}}"

# 2. 在场人物追踪（极简结构 · 严禁死者登场 · 每项 ≤ 15字）
present_characters:
  - id: "{{slot:char_1_id|p_001}}"
    name: "{{slot:char_1_name|主角名}}"
    role: "protagonist"
    want: "{{slot:char_1_want|本章即时利益诉求（≤15字）}}"
    fear: "{{slot:char_1_fear|本章即时忌惮/软肋（≤15字）}}"
    status_in: "{{slot:char_1_status_in|入场状态（≤15字）}}"
  - id: "{{slot:char_2_id|p_002}}"
    name: "{{slot:char_2_name|核心对手或重要配角名}}"
    role: "{{slot:char_2_role|antagonist}}" # antagonist(对手) | deuteragonist(副主) | supporting(重要配角)
    want: "{{slot:char_2_want|本章核心算计/试探目的（≤15字）}}"
    fear: "{{slot:char_2_fear|忌惮之处/死穴（≤15字）}}"
    status_in: "{{slot:char_2_status_in|入场状态（≤15字）}}"

# 3. 信息认知界限（防全知天眼穿帮 · 仅记录核心关键盲区）
epistemology:
  known:
    "{{slot:char_1_id|p_001}}":
      - "{{slot:char_1_knows|知晓的关键事实（≤20字）}}"
    "{{slot:char_2_id|p_002}}":
      - "{{slot:char_2_knows|对方知晓的有限事实（≤20字）}}"
  blind_spots:
    "{{slot:char_2_id|p_002}}":
      - "{{slot:char_2_blind|对方绝对不知晓的秘密（≤20字）}}"

# 4. 动态增量声明（按需填报：本章无变动保持空列表 []，严禁硬编；若有变动参考注释语法填实）
foreshadowing_deltas: []
# 伏笔参考语法:
# - id: "GUN-001"
#   name: "伏笔名"
#   action: "reveal"  # plant(新埋) | reveal(推进) | resolve(回收闭环)
#   desc: "线索特征与因果描述"

state_deltas:
  character_status: {}
  # 状态参考: p_001: "筑基初期·状态更新" ｜ p_005: "deceased" (阵亡)

  items: []
  # 道具流转参考:
  # - id: "it_001"
  #   name: "道具名"
  #   holder_change: "新持有者角色名"

  debts: []
  # 恩怨誓约参考:
  # - source: "p_001"
  #   target: "恩怨对象名"
  #   type: "grudge"  # grudge(仇怨) | favor(人情) | promise(誓约) | blood_feud(血仇)
  #   desc: "具体过节或誓约内容"
  #   action: "record"  # record(新结成) | settle(彻底平账)

relation_deltas: []
# 人际关系参考:
# - source: "p_001"
#   target: "p_002"
#   tension: "80"
#   dynamic: "表面客套·暗中博弈"
#   subtext: "利益争端/未挑明的死结"

new_entities: []
# 新登场实体参考:
# - id: "p_007"
#   type: "person"
#   name: "新有名配角名"
#   summary: "身份背景与战力简介"

locked_facts: []
# 既成法定事实参考:
# - id: "LOCK-004"
#   desc: "本章确立的不可逆既成物理事实"
---

{{slot:engine_briefing_dossier}}

# 第 {{slot:chapter_id|ch_XXX}} 章 《{{slot:title|章节名}}》 编剧细纲

---

## 🎯 一、 戏眼与有效增量（Spine & Delta）

- **本章核心戏眼**：
  {{slot:dramatic_goal|一句话矛盾对抗核心（≤25字）}}
- **局势实质转变（不可逆增量）**：
  - 核心实质动作：{{slot:dramatic_action|主角或对手采取的不可逆外部行动（≤25字）}}
  - 局势实质转变：{{slot:situational_shift|外部环境、人际关系或危机状态的实质变化（≤25字）}}
- **绝对负向写作围栏（写手必须恪守的红线）**：
  1. 【规则/战力围栏】：{{slot:taboo_logic|不可打破的世界法则、战力实物标尺或客观限制}}
  2. 【人设/动机围栏】：{{slot:taboo_persona|在场角色绝不可出现的降智妥协、面瘫无脑或油腻倒贴}}
  3. 【叙事/防注水围栏】：严禁重复前情科普；恪守通用十条红线（禁嗅觉、禁省略号切幕、禁冷笑垄断等）。

---

## 🎬 二、 双幕动作阶梯（Action Ladder · 严禁写死长对白，只定攻防台阶）

### 场景一：{{slot:scene_1_title|场景名}}
- **空间与物理清场**：{{slot:scene_1_space|发生地点}}（全场物理清场，抽走多余道具拐杖，聚焦冲突）
- **核心动作阶梯**：
  - 阶梯一（起势/施压）：{{slot:scene_1_step1|动作与动机交锋第一步}}
  - 阶梯二（对抗/交锋）：{{slot:scene_1_step2|局势升级与阻碍对撞}}
  - 阶梯三（转折/代价）：{{slot:scene_1_step3|阶段性结果与转场承接}}
- **对白核心（仅规划 1 组关键台词潜台词，其余由写手临场发挥）**：
  - {{slot:scene_1_dialogue|关键对白潜台词要点}}

### 场景二：{{slot:scene_2_title|场景名}}
- **空间与物理清场**：{{slot:scene_2_space|发生地点}}
- **核心动作阶梯**：
  - 阶梯一（升级/逼近）：{{slot:scene_2_step1|危机升级与正面交锋}}
  - 阶梯二（破局/反制）：{{slot:scene_2_step2|主角破局手段或反击动作}}
  - 阶梯三（停格定势）：{{slot:scene_2_step3|高潮定格切口}}
- **对白核心（仅规划 1 组关键台词潜台词，其余由写手临场发挥）**：
  - {{slot:scene_2_dialogue|关键对白潜台词要点}}

---

## 🪝 三、 章末定格·断章刀口（Cliffhanger · 拒绝抒情总结，停在动作瞬间）

- **绝杀断章刀型**：
  - [x] **【A: 动作骤停刀】**
  - [ ] **【B: 认知反转刀】**
  - [ ] **【C: 绝境倒计时刀】**

- **物理定格画面**：
  {{slot:cliffhanger|一句话停格画面}}
