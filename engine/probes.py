"""Novel Studio 机械质检探针矩阵 (engine/probes.py)。

为 Stage 4A (Auditor) 提供底层物理事实与数据探针（彻底删除文学风格、排版与字数硬约束）：
1. 字数物理遥测 (Word Count Telemetry) —— 纯计算字数，不做阈值拦截，仅空文本判错
2. 认知盲区防透视探针 (Epistemology)     —— 两级判定：确认泄露(error) / 疑似命中(warning)
3. 法定称谓矩阵探针 (Address Matrix)     —— 称谓未落地提醒（warning）
4. 道具与伏笔物象落地探针 (Grounding)    —— 细纲声明的道具/伏笔是否在正文落地（warning）

判定分级契约：
- passed=False 且进入 check errors 的只有：空文本(0字)、确认级认知泄露；
- 其余均为 warning 级提醒（Grounding/Address/疑似泄露），交由 Auditor 终审，
  坚守“引擎是仆人而非监工”公理，严禁卡死流水线。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from engine.config import DEFAULT_CONFIG, load_config


def _count_total(text: str) -> int:
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
    numbers = len(re.findall(r"\b\d+\b", text))
    return chinese_chars + english_words + numbers


def _extract_dialogues_with_speakers(text: str, known_names: List[str]) -> List[Tuple[Optional[str], str]]:
    """提取对白并做说话人归属启发式。

    覆盖中文小说两大句式：
    - 前置式：「赵管事咆哮道："……"」→ 名字在引号前 60 字符内；
    - 后置式：""……"陆沉平静说道。" → 名字在引号后 30 字符内。
    返回 [(说话人名或 None, 对白文本), ...]。归属失败的说话人为 None。
    """
    dialogues: List[Tuple[Optional[str], str]] = []
    known = sorted([n for n in known_names if n], key=len, reverse=True)

    def _find_before(context: str) -> Optional[str]:
        for name in known:
            pos = context.rfind(name)
            if pos >= 0:
                tail = context[pos + len(name):]
                if len(tail) <= 25:  # 名字与引号之间应为同一动作句
                    return name
        return None

    def _find_after(following: str) -> Optional[str]:
        for name in known:
            pos = following.find(name)
            if 0 <= pos <= 30:
                return name
        return None

    for m in re.finditer(r"[“「](.*?)[”」]", text, flags=re.DOTALL):
        start = max(0, m.start() - 60)
        speaker = _find_before(text[start:m.start()]) or _find_after(text[m.end():m.end() + 35])
        dialogues.append((speaker, m.group(1)))
    return dialogues


def _secret_keywords(secret: str) -> Tuple[List[str], List[str]]:
    """从盲区机密文本提取关键词，按置信度分两级（v4.2.1 缺陷#16）。

    - strong：完整汉字串 + 全部 4 字滑窗——足具特异性，可作确认级判据；
    - weak：3 字头/尾碎片（如"十分钟""段记忆"）——通用性太强，只允许触发
      疑似级提醒，防止盲区角色说一句日常台词就被判"确认泄露"阻断流水线。
    """
    runs = re.findall(r"[\u4e00-\u9fff]{2,}", secret)
    strong: List[str] = []
    weak: List[str] = []
    for run in runs:
        strong.append(run)
        if len(run) >= 5:
            for i in range(len(run) - 3):
                strong.append(run[i:i + 4])
        if len(run) > 3:
            weak.append(run[:3])
            weak.append(run[-3:])
    # 保序去重
    strong = list(dict.fromkeys(strong))
    weak = [w for w in dict.fromkeys(weak) if w not in strong]
    strong.sort(key=len, reverse=True)
    return strong, weak


def probe_epistemology_leaks(text: str, blind_spots: Dict[str, List[str]],
                             name_by_id: Optional[Dict[str, str]] = None,
                             present_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """认知盲区防透视探针 v4.1：三级判定（替代旧版全对白盲目匹配的高误报方案）。

    - confirmed（确认泄露，error 级）：盲区角色**本人**开口说出了自己不该知道的机密；
    - suspected（疑似命中，warning 级）：说话人无法归属，或他人当着盲区角色的面说出机密
      ——交由 Auditor 终审，不阻断流水线；
    - 静默通过：机密关键词出现在「盲区角色不在场且说话人可归属」的对白中（知情人的合法陈述）。
    """
    name_by_id = name_by_id or {}
    present_ids = set(present_ids or [])
    known_names = list(name_by_id.values())
    dialogues = _extract_dialogues_with_speakers(text, known_names)

    confirmed: List[Dict[str, Any]] = []
    suspected: List[Dict[str, Any]] = []

    for char_id, secrets in (blind_spots or {}).items():
        if not isinstance(secrets, list):
            continue
        owner_name = name_by_id.get(char_id, "")
        owner_in_scene = char_id in present_ids
        for secret in secrets:
            secret_confirmed = any(c.get("secret") == secret for c in confirmed)
            secret_suspected = any(s.get("secret") == secret for s in suspected)
            strong_kws, weak_kws = _secret_keywords(str(secret))
            for kw, is_strong in [(k, True) for k in strong_kws] + [(k, False) for k in weak_kws]:
                if secret_confirmed:
                    break
                for speaker, content in dialogues:
                    if not kw or kw not in content:
                        continue
                    if owner_name and speaker == owner_name and is_strong:
                        confirmed.append({"char_id": char_id, "secret": secret,
                                          "leaked_keyword": kw, "mode": "本人对白泄密"})
                        secret_confirmed = True
                        break
                    # 说话人无法归属，或盲区角色在场时他人公开说出 → 疑似
                    if speaker is None or owner_in_scene:
                        if len(kw) >= 3 and not secret_suspected:
                            suspected.append({"char_id": char_id, "secret": secret,
                                              "matched_keyword": kw,
                                              "mode": ("说话人无法归属" if speaker is None else "盲区角色在场，他人公开提及")})
                            secret_suspected = True
                    # 说话人可归属且盲区角色不在场 → 知情人合法陈述，静默通过
                    break

    return {
        "name": "认知盲区防透视探针",
        "passed": len(confirmed) == 0,
        "confirmed_count": len(confirmed),
        "suspected_count": len(suspected),
        "leaks": confirmed,
        "suspected": suspected,
        "detail": (f"发现 {len(confirmed)} 处确认级角色透视泄露！"
                   if confirmed else
                   (f"无确认泄露；{len(suspected)} 处疑似命中待人工复核" if suspected
                    else "各角色认知界限清晰，无对白透视穿帮")),
    }


def probe_address_matrix(text: str, persons_db: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """法定称谓落地探针（warning 级）：在场双方同章时，法定称谓从未出现则提醒。"""
    persons_db = persons_db or {}
    ungrounded: List[Dict[str, str]] = []
    for pid, p in persons_db.items():
        speaker = p.get("name", "")
        if not speaker or speaker not in text:
            continue
        for tgt, addr in (p.get("address_matrix") or {}).items():
            if tgt and tgt in text and addr and addr not in text:
                ungrounded.append({"speaker": speaker, "target": tgt, "expected_address": addr})
    return {
        "name": "法定称谓矩阵探针",
        "passed": len(ungrounded) == 0,
        "ungrounded": ungrounded,
        "detail": ("未发现称谓缺位" if not ungrounded else
                   f"{len(ungrounded)} 条法定称谓本章未落地: " +
                   "；".join(f"{u['speaker']}→{u['target']} 应称「{u['expected_address']}」" for u in ungrounded[:4])),
    }


def probe_grounding(text: str, frontmatter: Dict[str, Any]) -> Dict[str, Any]:
    """伏笔与道具物象落地探针（warning 级）：细纲声明 plant/reveal 的伏笔、流转的道具，
    其名称/物象应至少在正文中出现一次，防止「细纲写了正文忘了写」。

    token 粒度：全名 + 描述的二元词组（bigram）——只要物象的任意局部意象出现即算落地，
    规避整句改写导致的合法误报；仅当正文完全无任何相关物象时才提醒。
    """
    misses: List[Dict[str, str]] = []

    def _desc_bigrams(desc: str) -> List[str]:
        runs = re.findall(r"[\u4e00-\u9fff]{2,}", desc)
        grams: List[str] = []
        for run in runs[:4]:
            grams.extend(run[i:i + 2] for i in range(0, max(1, len(run) - 1), 1))
        return grams

    for fd in (frontmatter.get("foreshadowing_deltas") or []):
        if not isinstance(fd, dict):
            continue
        action = str(fd.get("action", "plant")).lower()
        if action not in ("plant", "reveal"):
            continue
        name = str(fd.get("name", "")).strip()
        desc = str(fd.get("desc", "")).strip()
        tokens = [name] if name else []
        tokens += _desc_bigrams(desc)
        if tokens and not any(t and t in text for t in tokens):
            misses.append({"kind": "伏笔", "ref": str(fd.get("id", "")), "hint": name or desc[:20]})

    sd = frontmatter.get("state_deltas") or {}
    for it in (sd.get("items") or []):
        if isinstance(it, dict):
            iname = str(it.get("name", "")).strip()
            iid = str(it.get("id", "")).strip()
            tokens = [t for t in (iname, iid) if t]
            tokens += _desc_bigrams(iname)
            if tokens and not any(t and t in text for t in tokens):
                misses.append({"kind": "道具", "ref": iid, "hint": iname})

    return {
        "name": "伏笔与道具物象落地探针",
        "passed": len(misses) == 0,
        "misses": misses,
        "detail": ("细纲声明的伏笔/道具均已在正文落地" if not misses else
                   "正文疑似漏写: " + "；".join(f"[{m['kind']}] {m['ref']} ({m['hint']})" for m in misses[:4])),
    }


def run_all_probes(text: str, frontmatter: Dict[str, Any],
                   persons_db: Optional[Dict[str, Any]] = None,
                   config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """运行确定性物理事实与数据探针，输出体检与字数遥测结果。"""
    name_by_id = {}
    for pid, p in (persons_db or {}).items():
        if isinstance(p, dict) and p.get("name"):
            name_by_id[pid] = p["name"]
    present_ids = [c.get("id") for c in (frontmatter.get("present_characters") or []) if isinstance(c, dict)]
    blind_spots = (frontmatter.get("epistemology") or {}).get("blind_spots", {})

    total_words = _count_total(text)
    p_epistemology = probe_epistemology_leaks(text, blind_spots, name_by_id=name_by_id, present_ids=present_ids)
    p_address = probe_address_matrix(text, persons_db)
    p_grounding = probe_grounding(text, frontmatter)

    # 阻断级错误唯二：空正文 (0字)、确认级角色认知泄露
    all_passed = (total_words > 0) and p_epistemology["passed"]
    return {
        "all_passed": all_passed,
        "word_count": total_words,
        "summary": {
            "words": {
                "name": "正文字数遥测",
                "word_count": total_words,
                "passed": total_words > 0,
                "detail": f"当前 {total_words} 字" if total_words > 0 else "正文内容为空（0 字）",
            },
            "epistemology": p_epistemology,
            "address": p_address,
            "grounding": p_grounding,
        },
    }
