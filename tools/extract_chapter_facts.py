# -*- coding: utf-8 -*-
"""
Chapter Fact & Mutation Pre-Extractor (extract_chapter_facts.py)
Pre-scans the finalized chapter in milliseconds (0 Token) to extract:
1. Financial Transactions & Numeric sentences (Currency, spending, loot)
2. Prop & Item mentions (Chekhov guns, loot, weapons)
3. Physical Conditions & Injuries (Damage, stamina, medical status)
4. Active Characters (Characters with dialogue or actions in this chapter)
5. Crucial Commitments & Deals (Agreements, contracts, pledges)

Provides high-signal fact candidates to LLM State Syncer to prevent fact hallucinations and dropped entries.

Usage:
    python tools/extract_chapter_facts.py -c ch_012
    python tools/extract_chapter_facts.py -c ch_012 --json
"""

import sys
import re
import json
import argparse
from pathlib import Path
from collections import defaultdict

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, find_manuscript_files, load_registered_characters, reconfigure_utf8

reconfigure_utf8()

CURRENCY_KEYWORDS = [
    "铜钱", "铜板", "文钱", "白银", "雪花银", "银两", "碎银", "两银", "黄金", "金币", "金条", "赤金",
    "灵石", "碎灵石", "极品灵石", "晶石", "信用点", "星币", "银子", "金子",
    "花了", "花费", "买下", "购得", "付了", "赏了", "收到", "起获", "搜出", "分润", "结余", "入账", "进账", "缴获", "充能"
]

NON_FINANCIAL_MEASURE_WORDS = r"(?:两人|两名|两柄|两队|两把|两次|两息|两步|两丈|两三|两截|两颗|两袋|两道|两倍|两侧|两旁|两边|两世|金铁|银丝|两尊|两重|两端|两手|双膝|双手)"

INJURY_KEYWORDS = [
    "伤", "血", "吐血", "骨折", "毒", "反噬", "虚脱", "剧痛", "负荷", "过载",
    "撕裂", "包扎", "止血", "痊愈", "暗疾", "消耗", "力竭", "脱力", "昏迷", "擦伤"
]

DEAL_KEYWORDS = [
    "协议", "契约", "答应", "承诺", "分账", "做庄", "联手", "结盟", "凭据", "凭证",
    "合同", "发誓", "保证", "担保", "授权"
]

def extract_facts(target_chapter_str: str, workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    manuscript_dir = workspace_dir / "05_manuscript"
    
    files = find_manuscript_files(manuscript_dir, target_chapter_str, single_latest=True)
    if not files:
        err = {"error": f"未找到目标章节: {target_chapter_str}"}
        if as_json:
            print(json.dumps(err, ensure_ascii=False, indent=2))
        else:
            print(f"❌ {err['error']}")
        return err

    target_file = files[0]
    content = target_file.read_text(encoding="utf-8")
    lines = content.splitlines()

    registered_chars = load_registered_characters(workspace_dir)
    
    # 1. Active Characters
    active_characters = []
    for c in registered_chars:
        if c in content:
            count = len(re.findall(re.escape(c), content))
            active_characters.append({"name": c, "mentions": count})
    active_characters.sort(key=lambda x: x["mentions"], reverse=True)

    # 2. Economy & Financial Clues
    financial_clues = []
    for idx, line in enumerate(lines, 1):
        clean_l = line.strip()
        if not clean_l or clean_l.startswith("#"):
            continue
        has_kw = any(k in clean_l for k in CURRENCY_KEYWORDS)
        has_amount = bool(re.search(r"[\d一二三四五六七八九十百千万]+\s*(?:两白银|两银子|两碎银|两黄金|两金|两银|两|文|贯|吊|枚金币|枚铜钱|块灵石|点模拟|点数)", clean_l))
        if has_kw or has_amount:
            if not has_kw and re.search(NON_FINANCIAL_MEASURE_WORDS, clean_l):
                continue
            financial_clues.append({
                "line": idx,
                "text": clean_l
            })

    # 3. Injury & Medical Clues
    injury_clues = []
    for idx, line in enumerate(lines, 1):
        clean_l = line.strip()
        if not clean_l or clean_l.startswith("#"):
            continue
        if any(k in clean_l for k in INJURY_KEYWORDS):
            injury_clues.append({
                "line": idx,
                "text": clean_l
            })

    # 4. Deals, Pledges & Key Objects
    deal_clues = []
    for idx, line in enumerate(lines, 1):
        clean_l = line.strip()
        if not clean_l or clean_l.startswith("#"):
            continue
        if any(k in clean_l for k in DEAL_KEYWORDS):
            deal_clues.append({
                "line": idx,
                "text": clean_l
            })

    # 5. Extract Quoted Items (Special objects in brackets or quotes)
    bracket_items = set()
    for m in re.findall(r"【(.*?)】|《(.*?)》", content):
        item = (m[0] or m[1]).strip()
        if len(item) >= 2 and len(item) <= 12 and not any(k in item for k in ["第", "章", "卷", "节", "岁", "年"]):
            bracket_items.add(item)

    report = {
        "chapter_file": target_file.name,
        "active_characters": active_characters,
        "bracket_items": list(bracket_items),
        "financial_clues": financial_clues,
        "injury_clues": injury_clues,
        "deal_clues": deal_clues
    }

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    print("═" * 72)
    print(f" 📑 [章节事实突变预扫描提取报告] 目标: {target_file.name}")
    print("═" * 72)

    print(f"\n👤 【本章活跃登场角色 ({len(active_characters)} 位)】:")
    for c in active_characters:
        print(f"   - {c['name']} (正文中提及 {c['mentions']} 次)")

    if bracket_items:
        print(f"\n📦 【本章重点道具与专有词汇】:")
        print("   " + "、".join(list(bracket_items)))

    print(f"\n💰 【资金、流水与交易线索 ({len(financial_clues)} 条)】:")
    if financial_clues:
        for f in financial_clues[:8]:
            print(f"   [L{f['line']}] {f['text']}")
        if len(financial_clues) > 8:
            print(f"   ... (其余 {len(financial_clues) - 8} 处略)")
    else:
        print("   (本章未检测到明显货币/交易数字变动)")

    print(f"\n🫁 【生理状况、伤势与负荷线索 ({len(injury_clues)} 条)】:")
    if injury_clues:
        for inj in injury_clues[:5]:
            print(f"   [L{inj['line']}] {inj['text']}")
    else:
        print("   (本章角色身体状态平稳，无明显伤势剧变)")

    print(f"\n📜 【重大承诺、地契契约与联盟线索 ({len(deal_clues)} 条)】:")
    if deal_clues:
        for d in deal_clues[:5]:
            print(f"   [L{d['line']}] {d['text']}")
    else:
        print("   (本章无重大书面契约或联盟协议)")

    print("\n═" * 72)
    print(" 💡 [同步官指引] 请结合上述高敏线索，精准回写 6 大状态机并保持双台账严格自洽！")
    print("═" * 72 + "\n")
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="章节事实突变快速预提取器")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, required=True, help="目标章节编号，例如: ch_012")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    extract_facts(target_chapter_str=args.chapter, workspace_path=args.workspace, as_json=args.json)
