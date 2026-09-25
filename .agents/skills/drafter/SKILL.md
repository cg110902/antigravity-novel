---
name: novel-drafter
description: Universal plot drafting and creative narrative generator for Novel Studio (Stage 2). Unchains full creative compute to produce high-tension raw story drafts (raw/ch_XXX_v1.md) across any genre, strictly inheriting beat facts and character matrices.
---

# SKILL — novel-drafter（起草先锋 · Stage 2）

## 📇 本卡速览

| 项 | 内容 |
|---|---|
| **角色职责** | 初稿起草写手。依照细纲动作阶梯创作高沉浸商业网文初稿 |
| **输入工件** | `workspace/<书名>/pack.md`（自完备装配包，**单次全量读取**） |
| **输出工件** | `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v1.md` |
| **核心任务** | 依照细纲动作阶梯展开攻防回合 ➔ 鲜活生动的叙事与代入感 ➔ 篇幅锁定 2000~3000 字 ➔ 物理落盘 |
| **约束红线** | 细纲法定事实不可篡改 ｜ 限知视角不透视 ｜ 绝对零命令 ｜ 禁传 `ArtifactMetadata` |
| **完工动作** | 输出 3 行标准回执，**立即停机** |

> ⚡ **【执行流程】**：调用 `view_file` **单次全量读取** `workspace/<书名>/pack.md`（严禁切片翻读） ➔ 展开起草（篇幅锁定 2000~3000 字，按商业网文节奏写足戏眼与冲突） ➔ `write_to_file`（`Overwrite: true`）写入 `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v1.md` ➔ 交卷停机。

---

## 🎯 一、 创作执行规范

### 1. 核心叙事与视角沉浸
- **主角视角沉浸**：镜头贴近主角第一感官与主观认知。保留主角鲜活的**内心算盘、动机权衡、即时反应与心理博弈**，赋予角色鲜活的生命力与代入感；
- **进戏明快，切入冲突**：开篇直接进入当前核心矛盾或情境现场，情节推进利落；
- **语言自然生动**：通畅顺口，自由发挥符合题材的世界观氛围与文风色彩。

### 2. 戏眼铺开与情节写实（该快就快，该慢就慢）
- **核心戏眼写足过程**：严格按细纲规划的【动作阶梯】推进核心对抗、关键交锋或重要博弈，写出攻防拉扯与局势变化；
- **过渡利落**：转场、赶路等过渡环节简洁明快带过，不拖泥带水；
- **章末利落断章**：在悬念或阶段高潮处干脆定格。

### 3. 人物塑造与互动张力
- **符合性格与利益立场**：对白与行动紧扣角色真实诉求与性格特质；
- **金手指/系统即时反馈**：若有系统或特殊能力机制，清晰呈现其触发效果与收益；
- **群像生动**：在场人物有各自的动机与立场，避免单薄背景板。

### 4. 细纲法定事实 100% 继承
- **事实基石**：剧情走向、胜负结果、在场人物严格继承 `pack.md`；
- **禁止机械编号**：正文中严禁出现 `p_001`、`GUN-003` 等系统 ID，一律使用自然姓名与称谓。

---

## ⚡ 二、 工序流程

1. **【单次全读】**：调用 `view_file` 一次性读完 `workspace/<书名>/pack.md`；
2. **【起草正文】**：依照细纲动作阶梯起草正文（2000~3000字）；
3. **【物理落盘】**：调用 `write_to_file`（`Overwrite: true`）直接写入 `workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v1.md`（**严禁传递 `ArtifactMetadata`**）；
4. **【交卷即走】**：输出 3 行标准回执，**立即停机**。

---

## 🛑 三、 完工回执

```text
【章节工序完工回执】
- 完工阶段：Stage 2 初稿起草 (Drafter)
- 产出路径：workspace/<书名>/manuscript/vol_XX/raw/ch_XXX_v1.md
- 核心指标：字数 [N] 字 ｜ 细纲事实100%继承 ｜ 戏眼攻防已打满 ｜ 工具物理落盘交付
```
