# Antigravity Novel · Novel Studio

**多智能体 + 确定性引擎混合驱动的中文长篇连载小说生产系统（v4.3+）**
LLM 子智能体负责创意与文笔，Python 引擎坐镇真理裁决：状态台账对账、伏笔追踪、资金池流水、卷末结算、快照时光机——创意自由放飞，事实滴水不漏。

---

## 🚀 一分钟上手

```bash
# 1. 开新书（实例化全部模板到工作区）
python studio.py init -w workspace/我的书 -t "我的书" -g "玄幻脑洞" -p "主角名"

# 2. 把脑洞/碎片材料写进 workspace/user_input.txt，按 .agents/ 角色手册依次执行：
#    Stage 0-Prep 解构卷宗 ➔ 0A 世界观筑基 ➔ 0B 大纲与八表通电 ➔ 0C 门禁验收

# 3. 单章工业化流水线（由 Director 主控调度）
python studio.py beats new ch_001 --write -w workspace/我的书   # 生成细纲任务书
python studio.py pack ch_001 --write -w workspace/我的书        # 装配自完备创作包
#    …（起草/重塑/顺滑/质检 四道文字工序由智能体完成落盘）…
python studio.py audit ch_001 --write -w workspace/我的书       # 引擎初审
python studio.py finalize ch_001 -w workspace/我的书            # 确定性定稿
python studio.py sync ch_001 -w workspace/我的书                # 八表合账封存
```

## 🧭 文档地图

| 文档 | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | 系统宪法：角色分工、钟声调度契约与铁律红线 |
| [`.agents/skills/`](.agents/skills/) | 10 份子智能体专属手册（Director / Architect / Screenwriter / Drafter / Dehydrator / Tuner / Auditor / Librarian / Evolution / Profiler） |
| [`templates/README.md`](templates/README.md) | 模板总目录、实体 ID 矩阵与强类型字段白名单（法定字段口径） |
| [`engine/README.md`](engine/README.md) | 引擎命令手册与 v4.3 修订注记 |


## ⚙️ 引擎关键能力（确定性 · 零幻觉）

- **巡航与卷末刹车链**：`cruise` 自动推进连载，触达卷末自动执行 `rollup ➔ reconcile ➔ export` 三连封存；
- **八表全息台账**：人物/道具/势力/地点/伏笔/恩怨/资金池/时间线逐章确定性入账，支持 `ask` 语义检索与 `trace` 章节回源；
- **快照时光机**：`snapshot create/rollback` 一键回退（含对齐清除与自动备份）；
- **因果推演**：`simulate impact` 测算改设定对全书的影响面，`evidence candidates` 打捞漏登记实体。

## 🧪 冒烟自检

```bash
python -m py_compile engine/*.py && python studio.py --version
python studio.py check -w <你的书工作区>   # 0 errors 即健康
```

---

