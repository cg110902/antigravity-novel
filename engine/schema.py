"""Novel Studio 核心数据契约与数据模型定义 (engine/schema.py)。

建立面向 30~50 万字长篇小说一致性的完整强类型数据模型：
1. 人物表 (persons.json)：ID、姓名、别名、Want/Fear、位阶、伤势、处境、互称矩阵、微动作库
2. 道具表 (items.json)：ID、名称、持有者(holder)、品阶、充能次数(charges)、消耗代价
3. 势力表 (factions.json)：ID、名称、规模、领袖、总部、外交网络(diplomacy)
4. 地点表 (places.json)：ID、名称、危险等级、空间法则、环境氛围
5. 伏笔线索表 (lines.json)：GUN(暗线)、KNO(知情差)、MIS(认知偏差) 的完整生命周期
6. 既定锁定事实表 (locked.json)：LOCK 历史不可逆事实
7. 经济流水账本 (ledger.json)：货币池余额与收支流水
8. 即时现场快照 (current.json)：当前时空、在场人、主角随身状态
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CharacterRecord:
    id: str
    name: str
    type: str = "person"
    role: str = "supporting"  # protagonist, deuteragonist, antagonist, ally, supporting（引擎缺省；v4.3 R2 对齐 templates/README 白名单，旧默认 other 不在合法枚举内）
    aliases: List[str] = field(default_factory=list)
    card: str = ""  # characters/<name>.md
    summary: str = ""
    # 位阶战力
    tier_rank: int = 1
    tier_name: str = ""
    realm: str = ""
    power_benchmark: str = ""
    # 生死与伤势
    status: str = "active"  # active, retired
    life_status: str = "alive"  # alive, deceased, missing
    condition: str = "完好"
    injury_level: int = 0  # 0~5
    injury_desc: str = "无伤"
    renown: int = 0
    # 地缘归属
    location: str = ""
    faction: str = ""
    attitude: str = "neutral"  # hostile, neutral, friendly, allied
    # 感官物象与称谓
    sensory_anchor: str = ""
    micro_actions: List[str] = field(default_factory=list)
    address_matrix: Dict[str, str] = field(default_factory=dict)  # {"目标人名": "我称呼对方"}
    relations: List[Dict[str, str]] = field(default_factory=list)
    dossier: str = ""
    # 心理四维与鲜活人格标签 (SSOT 核心)
    want: str = ""
    fear: str = ""
    need: str = ""
    lie: str = ""
    quirk: str = ""  # 反常怪癖/有毒特征（如：算死草强迫症、挑食、护短极度护短）
    taboo: str = ""  # 神经雷区/绝不可触碰之禁忌
    # 动态隐性情绪与情感底色
    latent_mood: str = ""  # 入场隐性情绪底色 (如: 被拒后的自尊刺痛/寄人篱下的隐忍戒备/爱恨交织的患得患失)
    physiological_leak: str = ""  # 生理应激微动作 (如: 喉结微滚/掐紧掌心/避开对视/敬称拉开距离)
    emotional_temp: int = 50  # 情绪压力/燃点 (0~100)
    vulnerability: str = ""  # 心理软肋/破防触发开关
    last_seen_ch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RelationRecord:
    source_id: str  # 发起方角色 ID (如 p_001)
    target_id: str  # 接收方角色 ID (如 p_002)
    affinity: int = 0  # 好恶温标 (-100 ~ +100，负为仇恨，正为倾心)
    trust: int = 50  # 信任度 (0 ~ 100)
    tension: int = 20  # 心理拉扯/张力指数 (0 ~ 100，越高代表暗流涌动、修罗场、话里有话)
    dynamic_label: str = "初识"  # 动态关系标签 (如: 单向暗恋·爱而不得 / 利益盟友·互留后手 / 宿命血仇·惺惺相惜)
    unspoken_subtext: str = ""  # 未挑明的潜台词/情感死结 (如: "她以为我嫌弃她累赘，其实我是怕她死在我前面")
    last_updated_ch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ItemRecord:
    id: str
    name: str
    type: str = "item"
    card: str = ""  # entities/items/<name>.md
    summary: str = ""
    tier_rank: int = 1
    tier_name: str = ""
    status: str = "active"
    condition: str = "完好"
    holder: str = ""  # 当前实际支配者角色名或ID
    charges: int = -1  # -1 表示非计数型，>=0 为剩余充能次数
    max_charges: int = -1
    cost_per_use: str = ""
    durability: str = "100%"
    location: str = ""
    faction: str = ""
    last_seen_ch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FactionRecord:
    id: str
    name: str
    type: str = "faction"
    card: str = ""  # entities/factions/<name>.md
    summary: str = ""
    scale_tier: int = 1
    leader: str = ""
    headquarters: str = ""
    core_assets: List[str] = field(default_factory=list)
    diplomacy: Dict[str, str] = field(default_factory=dict)  # {"其他势力名": "hostile"|"allied"|...}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlaceRecord:
    id: str
    name: str
    type: str = "place"
    card: str = ""  # entities/locations/<name>.md
    summary: str = ""
    danger_tier: int = 1
    danger_level: str = "安全腹地"
    environment_rules: List[str] = field(default_factory=list)
    sensory_anchor: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LineRecord:
    id: str  # GUN-001, KNO-001, MIS-001
    name: str
    type: str = "GUN"  # GUN(伏笔暗线), KNO(机密知情差), MIS(认知误会)
    tier: str = "A"  # S(全书天坑), A(分卷暗线), B(战术小扣子)
    status: str = "active"  # active, resolved, abandoned
    planted_ch: str = ""
    target_ch: str = ""  # 预期收束章节 (如 ch_048)
    revealed_chs: List[str] = field(default_factory=list)  # 中途露出一角的章节
    resolved_ch: str = ""
    desc: str = ""
    evidence: str = ""  # 原文对应证据切片

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DebtRecord:
    id: str  # DEBT-001
    source_char: str  # 债权人 ID 或姓名
    target_char: str  # 债务人 ID 或姓名
    type: str = "grudge"  # grudge(仇怨/血债), favor(恩情/人情), promise(誓言/契约)
    desc: str = ""
    status: str = "unpaid"  # unpaid(未了结), settled(已清算/已报偿)
    created_ch: str = ""
    settled_ch: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LockedFactRecord:
    id: str  # LOCK-001
    fact: str
    established_ch: str
    domain: str = "general"  # world, character, plot, rule

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LedgerRecord:
    pools: Dict[str, int] = field(default_factory=dict)  # 币种池按书声明（灵石/银两/人民币/积分…），引擎不预置题材币种
    transactions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimelineEntry:
    chapter_id: str
    volume_id: str
    title: str
    timeline: str
    location: str
    word_count: int = 0
    present_characters: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 向后兼容别名
CharacterState = CharacterRecord
ItemState = ItemRecord
ForeshadowingState = LineRecord
