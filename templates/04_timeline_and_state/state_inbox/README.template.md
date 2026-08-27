# 状态变更提案投递箱 (State Inbox)

章节定稿后的标准流水线：
1. **0-LLM 骨架预填**：运行 `python studio.py draft ch_xxx` 预填 `ch_xxx.draft.json`（已填在场角色、候选流水、线索句与自动梗概）；
2. **LLM 语义复核**：`novel-state-syncer` 打开草稿逐项复核并补全语义字段，另存为正式 `ch_xxx.json`（删除 `_draft`/`_evidence` 等字段）；
3. **确定性合并**：运行 `python studio.py apply`（或 `python studio.py sync ch_xxx` 自动包含合并）将变更合并进 6 大状态文件并重算余额。

> ⚠️ 注意：`*.draft.json` 与带 `_draft:true` 的提案绝不会被合并，只有复核后的正式 JSON 提案才会生效。
> 💡 格式参考：可查阅同目录下 `ch_sample.proposal.template.json` 获取完整结构范例。

## 提案 JSON 格式说明 (schema: novel-studio.state-mutation/v1)
- `current_state`：时空锚点、在场角色、境界、伤势、资产、局势（按字段差异更新）
- `guns`：伏笔 `plant` / `update` / `resolve`（id 可省略，引擎自动按序编号）
- `misunderstandings`：误会 `plant` / `update` / `resolve`（自动编号）
- `growth_arcs`：角色心智阶段更新
- `timeline`：编年史事件追加（幂等去重）
- `transactions`：复式账本流水（`delta` 正=收入负=支出，余额由流水自动重算）
- `synopsis`：（可选）本章 2~3 句精炼梗概 + `chapter_title`，登记进章节梗概脊柱（`chapter_synopsis.json`）

合并成功的提案自动归档移入 `processed/`，校验失败的移入 `failed/` 并输出错误原因。
