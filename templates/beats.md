---
# ==============================================================================
# 💡【细纲编制契约 · 轻量化 Frontmatter】
# 🔴 核心必填：chapter_id, volume_id, title, present_characters (id+name+role), 断章刀口。
# 🟢 状态增量与伏笔全为【按需声明】：有则声明入账，无则留空或缺省！
# ==============================================================================
chapter_id: "{{slot:chapter_id|ch_XXX}}"
volume_id: "{{slot:volume_id|vol_01}}"
title: "{{slot:title|章节名}}"
chapter_type: "{{slot:chapter_type|破局}}" # 节奏遥测: 破局/铺垫/过渡/爆发/回收/余韵
timeline: "{{slot:timeline|小说历纪年·时空时间}}"
location: "{{slot:location|核心场景名}}"

# 0. 航标锚定：本章在全书与本卷宏观版图中的定位
narrative_spine:
  thread: "{{slot:thread|主线·核心冲突推进}}"
  volume_phase: "{{slot:volume_phase|阶段一：开局破局}}"
  macro_goal: "{{slot:macro_goal|本阶段跨章核心战役目标}}"

# 1. 在场人物追踪（极简结构）
present_characters:
  - id: "{{slot:char_1_id|p_001}}"
    name: "{{slot:char_1_name|主角名}}"
    role: "protagonist"
    want: "{{slot:char_1_want|本章核心利益诉求}}"
    fear: "{{slot:char_1_fear|本章最忌惮暴露的底牌或软肋}}"
    status_in: "{{slot:char_1_status_in|入场状态：如 完好/微伤/隐忍戒备}}"
  - id: "{{slot:char_2_id|p_002}}"
    name: "{{slot:char_2_name|核心对手/反派名}}"
    role: "{{slot:char_2_role|antagonist}}"
    want: "{{slot:char_2_want|本章核心算计/施压目的}}"
    fear: "{{slot:char_2_fear|忌惮之处/死穴}}"
    status_in: "{{slot:char_2_status_in|入场状态：如 盛气凌人/暗中试探}}"

# 2. 信息认知界限（谁知道什么，谁绝对不知道什么 · 严防角色全知天眼穿帮）
epistemology:
  known:
    "{{slot:char_1_id|p_001}}":
      - "{{slot:char_1_knows|明确知晓的事实}}"
    "{{slot:char_2_id|p_002}}":
      - "{{slot:char_2_knows|对方知晓的有限事实}}"
  blind_spots:
    "{{slot:char_2_id|p_002}}":
      - "{{slot:char_2_blind|对方绝对不知道的秘密（严禁正文脱口而出）}}"

# 3. 伏笔与暗线生命周期（按需声明：plant 新埋 / reveal 推进 / resolve 闭环）
foreshadowing_deltas:
  - id: "{{slot:line_1_id|GUN-001}}"
    name: "{{slot:line_1_name|伏笔名}}"
    action: "{{slot:line_1_action|reveal}}" # plant(埋设) | reveal(推进) | resolve(回收)
    desc: "{{slot:line_1_desc|线索特征与因果描述}}"

# 4. 状态增量声明（出场状态变动、道具流转、资金流水、恩怨结成；由 Stage 5 sync 自动化确定性入账）
state_deltas:
  character_status:
    "{{slot:char_1_id|p_001}}": "{{slot:char_1_status_out|出场状态：如 位阶突破 / 身体受创 / 心境升华}}"
  # 选填：道具流转与充能扣减（无变动可省略或保留空）
  # items:
  #   - id: "it_001"
  #     name: "道具名"
  #     holder_change: "p_001 -> p_002"  # 持有者流转
  #     charges_delta: -1                 # 充能消耗（负数为扣减，正数为充能）
  # 选填：经济流水增减（无变动可省略）
  # ledger:
  #   pool: "通用资金池"
  #   delta: "+500"                       # 增减数值（+收入 / -支出）
  #   reason: "押运赏金入账"               # 选填：本笔事由（供资金池遥测与卷末对账溯源）
  debts:
    - source: "{{slot:debt_source|p_001}}"   # 结怨发起方（缺省自动按 p_001 主角记账）
      target: "{{slot:debt_target|恩怨对象名}}"
      type: "{{slot:debt_type|grudge}}" # grudge(仇怨) | favor(人情) | promise(誓约)
      desc: "{{slot:debt_desc|具体过节或恩义内容}}"
      action: "{{slot:debt_action|record}}" # record(新结成) | settle(彻底平账)

# 5. 双向动态心理状态（张力指数 0~100）
relation_deltas:
  - source: "{{slot:char_1_id|p_001}}"
    target: "{{slot:char_2_id|p_002}}"
    tension: "{{slot:rel_tension|75}}"
    dynamic: "{{slot:rel_dynamic|表面客套·暗中博弈}}"
    subtext: "{{slot:rel_subtext|利益争端/未挑明的死结}}"

# 6. 新登场实体与不可逆事实锁定（选填）
new_entities: []
locked_facts: []
---

{{slot:engine_briefing_dossier}}

# 第 {{slot:chapter_id|ch_XXX}} 章 《{{slot:title|章节名}}》 编剧细纲

---

## 🎯 一、 核心戏剧目标与爽点

- **本章核心戏剧目标**：
  {{slot:dramatic_goal|一句话写明当章核心事件与破局关键}}
- **独家看点**：
  {{slot:anti_cliche_twist|拒绝平铺直叙流水账}}
- **绝对负向红线（Scene Taboos）**：
  1. 【规则/战力禁忌】：{{slot:taboo_logic|不可打破的世界法则、战力实物标尺或客观限制}}
  2. 【人设/动机禁忌】：{{slot:taboo_persona|在场角色绝不可出现的降智妥协、面瘫无脑或性格崩坏}}
  3. 【叙事/套路禁忌】：{{slot:taboo_plot|绝不可落入的俗套陈词或生硬机械降神}}

---

## 🎬 二、 核心场景脉络（建议 1~2 个核心大场景，拒绝碎片化流水账）

### 场景一（[视点人] 地点/事件 ）
- 🎯 核心冲突与阻碍：自行设定
- ⚔️ 对抗博弈与对白：自行设定
- 💓 情绪流向与心理台阶：自行设定
- 🌊 承上启下气口（如何自然引向下一场景或章末）：自行设定

### 场景二（可选 ｜ [视点人] 地点/事件 ）
- 🎯 矛盾升级与破局代价：自行设定
- ⚔️ 高光展现或意外变故：自行设定
- 💓 情绪流向与心理台阶：自行设定
- 🌊 承上启下气口（收束引向章末绝杀定格）：自行设定

---

## 🪝 三、 章末定格·断章刀口（Cliffhanger · 拒绝抒情总结，停在动作瞬间）

- **绝杀断章刀型（3 选 1）**：
  - [ ] **【A: 动作骤停刀】**：关键动作、异响或危机悬在半空，答案就在下一秒；
  - [ ] **【B: 认知反转刀】**：既定事实瞬间颠覆，撕开反常真相或致命底牌；
  - [ ] **【C: 绝境倒计时刀】**：危机比预估提前降临，退路被瞬间切断；

- **物理定格画面**：
  {{slot:cliffhanger|定格在何处具体悬念瞬间，让读者产生必点下一章的生理冲动}}
