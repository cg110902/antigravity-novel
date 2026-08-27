# -*- coding: utf-8 -*-
"""
Proposal Drafter — 零 LLM 提案骨架生成器（本地能定的先定，本地定不了的留给 LLM）。

在 state-syncer（LLM）动手之前，先用纯 Python 扫一遍定稿章节，把**确定性高、无需语义**
的字段预填成一份「草稿提案」，写到：
    04_timeline_and_state/state_inbox/ch_xxx.draft.json

LLM 同步官只需打开这份草稿：核对/补全被标记的字段 → 另存为正式 `ch_xxx.json`（去掉
`_draft` 标记），即可被 `state_apply` 合并。草稿本身**绝不会被 state_apply 合并**
（文件名 `.draft.json` + 提案内 `_draft:true` 双重保险）。

本地能高置信预填的：
  - chapter / chapter_title（从文件名、章节标题）
  - current_state.present_characters（已登记且本章出现的角色，纯字符串匹配）
  - synopsis（memory_core 启发式梗概，source 标 auto→LLM 应润色）
本地只能给"候选 + 证据句"、必须 LLM 复核的：
  - transactions_draft：从货币/交易句正则抽 (方向, 金额, 资源池, 证据)，逐条 _needs_review
  - candidate_guns / candidate_deals / injury_clues：线索句，供 LLM 判断是否伏笔/协议/伤势
本地完全做不了、留空给 LLM 的：
  - current_state 的 time/location/realm/abilities/injury/assets/equipment/situation
  - guns / misunderstandings / growth_arcs / timeline 的语义内容

所有不确定项都带 `evidence`（原句+行号）与 `confidence`，保证最终准确性由 LLM 兜底。

用法：
    python tools/proposal_draft.py -c ch_012
    python tools/proposal_draft.py -c 12 --json
"""

import sys
import re
import json
import argparse
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import (
    resolve_workspace, reconfigure_utf8, find_manuscript_files,
    load_registered_characters, chapter_number_from_name, chapter_token_to_num,
)

reconfigure_utf8()

# 收入 / 支出方向词（命中即判定正负，越靠前优先级越高）
_INCOME_WORDS = ["收到", "赚", "挣", "分润", "分得", "赏了", "赏赐", "起获", "搜出", "缴获",
                 "卖了", "卖出", "所得", "入账", "进账", "赔偿", "获得", "获了", "得到", "赢",
                 "奖励", "奖了", "赚到"]
_EXPENSE_WORDS = ["花了", "花费", "花钱", "买下", "购得", "买", "付了", "付出",
                  "赔了", "还债", "还了", "交了", "缴纳", "花去", "支出", "掏出"]

# 资源池单位映射（按顺序匹配，越靠前优先级越高；vital 类必须排在货币"点"之前）
_UNIT_POOL = [
    ("属性点", "vital_points"), ("技能点", "vital_points"), ("功勋", "vital_points"),
    ("贡献点", "vital_points"), ("积分", "vital_points"),
    ("灵石", "standard_currency"), ("晶石", "standard_currency"),
    ("金币", "standard_currency"), ("银币", "standard_currency"),
    ("铜板", "standard_currency"), ("铜钱", "standard_currency"), ("文钱", "standard_currency"),
    ("信用点", "standard_currency"), ("星币", "standard_currency"),
]
# 用于金额抓取的多字单位优先（避免"点"把"功勋点/30点"截断）
_AMOUNT_UNIT_RE = (r"灵石|晶石|金币|银币|铜板|铜钱|文钱|信用点|星币|"
                   r"属性点|技能点|功勋点|贡献点|功勋|积分|两|文|金|银|元|点|分")
_CURRENCY_UNITS = ["灵石", "晶石", "金币", "银币", "铜板", "铜钱", "文钱", "信用点",
                   "星币", "属性点", "技能点", "功勋", "贡献点", "积分",
                   "两", "文", "金", "银", "元", "点", "分"]

_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def parse_cn_number(text: str):
    """解析常见中文/阿拉伯金额。支持 '三千二百' '一百五' '500' '三两' 等。返回 int 或 None。"""
    text = (text or "").strip()
    if not text:
        return None
    m = re.search(r"\d+(?:\.\d+)?", text)
    if m:
        v = float(m.group(0))
        return int(v) if v == int(v) else v
    # 中文数字
    total, section, num = 0, 0, 0
    has_cn = False
    for ch in text:
        if ch in _CN_DIGIT:
            num = _CN_DIGIT[ch]
            has_cn = True
        elif ch == "十":
            section += (num or 1) * 10
            num = 0
            has_cn = True
        elif ch == "百":
            section += (num or 1) * 100
            num = 0
            has_cn = True
        elif ch in ("千",):
            section += (num or 1) * 1000
            num = 0
            has_cn = True
        elif ch in ("万", "亿"):
            section += num
            unit = 10000 if ch == "万" else 100000000
            total += section * unit if section else (num or 1) * unit
            section, num = 0, 0
            has_cn = True
    val = total + section + num
    return val if has_cn and val > 0 else None


def _guess_pool(unit: str) -> str:
    for kw, pool in _UNIT_POOL:
        if kw in (unit or ""):
            return pool
    return "standard_currency"


def _detect_direction(sentence: str):
    """返回 (delta_sign, matched_word)。收入=+1，支出=-1，无法判定=None。"""
    for w in _INCOME_WORDS:
        if w in sentence:
            return 1, w
    for w in _EXPENSE_WORDS:
        if w in sentence:
            return -1, w
    return None, None


def _extract_transactions(lines: list):
    """从含货币关键词+数字的句子抽候选流水。"""
    tx = []
    for idx, raw in enumerate(lines, 1):
        s = raw.strip().lstrip("#*-　> ").strip()
        if not s or s.startswith("#"):
            continue
        if not any(u in s for u in _CURRENCY_UNITS):
            continue
        if not re.search(r"[0-9]|[一二两三四五六七八九十百千万]", s):
            continue
        sign, dir_word = _detect_direction(s)
        # 一行可能含多笔流水，逐处抓"数字+单位"
        for m in re.finditer(r"([0-9一二两三四五六七八九十百千]+)\s*(" + _AMOUNT_UNIT_RE + r")", s):
            amount = parse_cn_number(m.group(1))
            unit = m.group(2)
            if amount is None:
                continue
            # 方向：优先取金额紧邻的上下文（前后各 12 字）内的收支词
            local_ctx = s[max(0, m.start() - 12):m.end()]
            local_sign, local_word = _detect_direction(local_ctx)
            used_sign = local_sign or sign
            used_word = local_word or dir_word
            # 向右看：单位是泛字（点/分…）且紧随功勋/属性点/积分等，归 vital 池
            tail = s[m.end():m.end() + 6]
            for kw in ("功勋", "属性点", "技能点", "贡献点", "积分"):
                if tail.startswith(kw) or (len(tail) >= 2 and kw in tail[:3]):
                    unit = unit + kw
                    break
            tx.append({
                "resource": _guess_pool(unit),
                "delta": used_sign * amount if used_sign else None,
                "type": "income" if used_sign == 1 else "expense",
                "subject": "",  # LLM 填事由
                "counterparty": "",
                "_needs_review": True,
                "_direction_word": used_word or "",
                "_unit": unit,
                "evidence": {"line": idx, "sentence": s[max(0, m.start()-10):m.end()+20][:120]},
            })
    return tx


def _collect_clue_lines(lines: list, keywords: list):
    out = []
    for idx, raw in enumerate(lines, 1):
        s = raw.strip().lstrip("#*-　> ").strip()
        if not s or s.startswith("#"):
            continue
        if any(k in s for k in keywords):
            out.append({"line": idx, "sentence": s[:120]})
    return out


INJURY_WORDS = ["伤", "血", "吐血", "骨折", "毒", "反噬", "虚脱", "剧痛", "负荷", "过载",
                "撕裂", "包扎", "止血", "暗疾", "力竭", "脱力", "昏迷", "擦伤"]
DEAL_WORDS = ["协议", "契约", "答应", "承诺", "分账", "做庄", "联手", "结盟",
              "凭据", "凭证", "合同", "发誓", "保证", "担保", "授权"]
# 可能预示新伏笔的信号词
GUN_HINT_WORDS = ["秘密", "身世", "谜团", "古怪", "诡异", "来历不明", "神秘", "暗藏",
                  "隐患", "伏笔", "不简单", "另有", "隐情", "信物", "钥匙", "地图", "账册", "账本"]


def build_draft(workspace: Path, chapter_token: str):
    manuscript_dir = workspace / "05_manuscript"
    files = find_manuscript_files(manuscript_dir, chapter_token, single_latest=True)
    if not files:
        return {"error": f"未找到目标章节定稿: {chapter_token}"}
    target = files[0]
    num = chapter_number_from_name(target.name)
    if num is None:
        num = chapter_token_to_num(chapter_token)
    key = f"ch_{num:03d}"
    content = target.read_text(encoding="utf-8")
    lines = content.splitlines()

    # 标题
    title = ""
    for line in lines[:8]:
        s = line.strip()
        if s.startswith("#"):
            title = re.sub(r"^#+\s*", "", s).strip()
            break

    # 在场角色（已登记 + 本章出现），纯字符串匹配，高置信
    present = []
    try:
        registered = load_registered_characters(workspace)
        present = [c for c in registered if c and c in content]
    except Exception:
        pass

    # 候选流水
    transactions_draft = _extract_transactions(lines)

    # 线索句（供 LLM 判断，不直接进提案正文）
    injury_clues = _collect_clue_lines(lines, INJURY_WORDS)
    deal_clues = _collect_clue_lines(lines, DEAL_WORDS)
    gun_clues = _collect_clue_lines(lines, GUN_HINT_WORDS)

    # 启发式梗概（LLM 应润色为人工版）
    synopsis = ""
    try:
        import memory_core
        synopsis = memory_core.auto_synopsis(content)
    except Exception:
        pass

    draft = {
        "_draft": True,
        "_instructions": (
            "这是 state_apply 不会合并的草稿（请在复核后另存为同名去掉 .draft 的正式 ch_xxx.json，"
            "并删除本 _draft/_instructions/_review_checklist/_evidence 及所有 *_draft/候选字段）。"
            "规则：present_characters 可直接采用；transactions_draft 逐条核对方向/金额/资源池/事由，"
            "确认后移入 transactions（删掉 _needs_review/evidence）；synopsis 请润色为 2~3 句精炼梗概；"
            "current_state 时空/境界/伤势/装备/局势与 guns/misunderstandings/growth_arcs/timeline 需你按正文语义补全。"
        ),
        "schema": "novel-studio.state-mutation/v1",
        "chapter": key,
        "chapter_title": title,
        "current_state": {
            "present_characters": present,
            # 以下留空，LLM 按正文填：
            "time": "",
            "location": "",
            "realm": "",
            "abilities": "",
            "injury": "",
            "assets": "",
            "equipment": "",
            "situation": "",
        },
        "guns": [],
        "misunderstandings": [],
        "growth_arcs": [],
        "timeline": [],
        "synopsis": synopsis,
        "synopsis_source_hint": "auto（请润色；空则请你撰写）",

        # —— 草稿专属：候选与证据，不参与合并 ——
        "transactions_draft": transactions_draft,
        "candidate_gun_clues": gun_clues,
        "deal_clues": deal_clues,
        "injury_clues": injury_clues,
        "_review_checklist": [
            "核对 transactions_draft 每条：金额符号对吗？资源池对吗（玄幻用灵石/点，科幻用信用点）？事由/对手方是谁？",
            "present_characters 是否有遗漏的新角色（未登记的首次出场者应去 02_characters 建档）？",
            "candidate_gun_clues 里有没有本章新埋的伏笔（要写 guns[].plant）？",
            "deal_clues 是否构成误会/信息差（misunderstandings）或新协议？",
            "injury_clues 是否要写入 current_state.injury？",
            "current_state 的 time/location/situation 本章是否变化？",
            "growth_arcs：本章主角心智/阶段是否推进？",
            "timeline：本章是否有值得记进编年史的关键事件？",
        ],
        "_evidence_summary": {
            "present_characters_confidence": "high" if present else "none",
            "transactions_candidate_count": len(transactions_draft),
            "gun_clue_count": len(gun_clues),
            "deal_clue_count": len(deal_clues),
            "injury_clue_count": len(injury_clues),
        },
    }
    return draft


def _main():
    ap = argparse.ArgumentParser(description="零 LLM 提案骨架生成器")
    ap.add_argument("--workspace", "-w", help="工作区路径")
    ap.add_argument("--chapter", "-c", required=True, help="目标章节，如 ch_012 或 12")
    ap.add_argument("--json", action="store_true", help="输出 JSON（不落盘）")
    args = ap.parse_args()

    ws = resolve_workspace(args.workspace)
    draft = build_draft(ws, args.chapter)
    if "error" in draft:
        print(f"❌ {draft['error']}")
        sys.exit(1)

    if args.json:
        print(json.dumps(draft, ensure_ascii=False, indent=2))
        return

    # 落盘到 state_inbox/ch_xxx.draft.json
    inbox = ws / "04_timeline_and_state" / "state_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    out = inbox / f"{draft['chapter']}.draft.json"
    out.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=" * 72)
    print(f" 🧩 [零 LLM 提案骨架已生成] {out.relative_to(ws)}")
    print("=" * 72)
    print(f" 📖 章节：{draft['chapter']}《{draft['chapter_title'] or '?'}》")
    print(f" 👥 在场角色（高置信，已预填）：{', '.join(draft['current_state']['present_characters']) or '（未识别到已登记角色）'}")
    print(f" 💰 候选流水 {len(draft['transactions_draft'])} 条（需逐条复核）：")
    for t in draft["transactions_draft"]:
        sign = "收" if (t.get("delta") or 0) > 0 else "支"
        print(f"    [{sign}] {t.get('delta')} {t.get('_unit','')} → {t['resource']}")
        print(f"        证据 L{t['evidence']['line']}: {t['evidence']['sentence']}")
    print(f" 🕸 伏笔线索 {len(draft['candidate_gun_clues'])} | 📜 协议线索 {len(draft['deal_clues'])} | 🫁 伤势线索 {len(draft['injury_clues'])}")
    print(f" 📚 自动梗概（请润色）：{draft['synopsis'][:60]}{'…' if len(draft['synopsis'])>60 else ''}")
    print("-" * 72)
    print(" 📝 下一步（LLM 同步官）：")
    print("   1) 打开本 .draft.json，按 _review_checklist 逐项核对/补全；")
    print("   2) 确认后的流水移入 transactions，补事由/对手方；补 guns/timeline/growth_arcs；")
    print("   3) 另存为正式 state_inbox/" + draft["chapter"] + ".json（删除 _draft/_instructions/_evidence/*_draft 字段）；")
    print("   4) python studio.py sync " + draft["chapter"] + "  自动合并。")
    print("=" * 72)


if __name__ == "__main__":
    _main()
