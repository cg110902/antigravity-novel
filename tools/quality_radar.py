# -*- coding: utf-8 -*-
"""
Quality Radar — P2 高级质检雷达（纯本地确定性统计，零 Token）。

三项能力：
  A. 塌中段 / 注水检测 (Stall Detector)：连续 N 章没有任何状态变更
     （state_inbox 已处理提案、账本流水、timeline/伏笔台账无新行）= 中段塌陷/注水；
     借鉴 Novel-OS stall_detector（连续 3 章无状态字段变化）。
  B. 黄金配比量化门 (Golden Ratio Gate)：逐章统计 对白/推进动作/静态描写 三维占比，
     对照黄金配比基线（对白 30~40%+、推进 40~50%、描写 15~30%）打分；
     只出 WARNING/评分，不硬阻断（配比对白章可自然上浮）。
  C. 文风蒸馏 (Style Distillation)：以全部定稿为正样本，统计句长分布、对白密度、
     段落长度、口癖词频，建立"本书文风指纹"；可对单章对比打分（偏离全书风格则提示），
     借鉴 inkflow 风格蒸馏。

用法：
    python tools/quality_radar.py --stall          # 塌中段检测
    python tools/quality_radar.py --ratio          # 黄金配比门
    python tools/quality_radar.py --distill        # 蒸馏全书文风指纹
    python tools/quality_radar.py --distill -c ch_005   # 对比单章与全书风格
    python tools/quality_radar.py --all --json
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
    natural_chapter_sort_key, chapter_number_from_name,
)

reconfigure_utf8()

STYLE_FINGERPRINT_FILE = "04_timeline_and_state/style_fingerprint.json"
STYLE_SCHEMA = "novel-studio.style-fingerprint/v1"


def _genre_profile(workspace: Path) -> dict:
    """加载题材档案（P3-4）；任何失败都回退到内置通用值，保证工具永不停摆。"""
    try:
        import genre_profile as gp
        return gp.resolve_genre_profile(workspace)
    except Exception:
        return {}


def _baseline(profile: dict) -> dict:
    """从题材档案取配比基线；缺省回退通用基线。"""
    rb = (profile or {}).get("ratio_baseline") or {}
    def _rng(key, lo, hi):
        v = rb.get(key)
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return (v[0], v[1])
        return (lo, hi)
    return {
        "dialogue": _rng("dialogue", 30, 45),
        "action": _rng("action", 35, 55),
        "describe": _rng("describe", 10, 30),
    }
# 静态描写信号词（环境/景物/外貌）
_DESC_HINTS = ("天空", "阳光", "月光", "夜色", "街道", "建筑", "墙壁", "地面", "风", "雨",
               "云", "树", "花", "草", "山", "河", "海", "光", "影", "颜色", "穿着", "面容",
               "身材", "房间", "陈设", "空气", "温度", "声音", "气味", "灰尘", "锈迹", "废墟")
# 推进/动作信号词
_ACTION_HINTS = ("冲", "抓", "夺", "砍", "刺", "踢", "打", "躲", "闪", "跑", "追", "逃",
                 "转身", "推开", "抓住", "出手", "击中", "倒下", "站起", "掏出", "塞",
                 "决定", "交易", "谈", "问", "说", "道", "喊", "答", "发现", "得知", "突破")
# 常见 AI/口癖词（去 AI 味规范里点名的）
_TICKS = ("笑了笑", "似笑非笑", "嘴角微勾", "嘴角上扬", "勾起一抹", "微微一笑", "淡淡地说",
          "缓缓开口", "深吸一口气", "瞳孔骤缩", "眸", "勾起唇角", "戏谑", "玩味", "不动声色",
          "意味深长", "不约而同", "空气仿佛凝固", "时间仿佛静止")


# ---------------------------------------------------------------------------
# 文本切分
# ---------------------------------------------------------------------------
def _cjk_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fa5]", text))


def _strip_body(text: str) -> str:
    """去掉标题行、工程标记，只留正文。"""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if re.search(r"GUN-|MIS-|Stage\s*\d|beats|Beats", s):
            continue
        out.append(s)
    return "\n".join(out)


def _dialogue_chars(text: str) -> int:
    return sum(len(q) for q in re.findall(r"“([^”]*)”", text))


def _sentences(text: str) -> list:
    return [s for s in re.split(r"(?<=[。！？…])", text) if _cjk_count(s) >= 2]


# ---------------------------------------------------------------------------
# A. 塌中段 / 注水检测
# ---------------------------------------------------------------------------
def _chapter_had_state_change(workspace: Path, num: int) -> bool:
    """该章定稿后是否在任何状态真值里留下痕迹（提案/流水/台账新行）。"""
    key = f"ch_{num:03d}"
    state_dir = workspace / "04_timeline_and_state"

    # 1) 处理过的提案（processed）按章节
    proc = state_dir / "state_inbox" / "processed"
    if proc.exists():
        for pf in proc.glob("*.json"):
            try:
                p = json.loads(pf.read_text(encoding="utf-8"))
                if p.get("chapter") == key:
                    # 提案里只要有实质变更字段即算
                    if any(p.get(k) for k in ("current_state", "guns", "misunderstandings",
                                              "growth_arcs", "timeline", "transactions", "synopsis")):
                        return True
            except Exception:
                continue

    # 2) 账本流水引用该章（跳过"初始余额/开户"型占位流水）
    ledger = state_dir / "economy_ledger.json"
    if ledger.exists():
        try:
            d = json.loads(ledger.read_text(encoding="utf-8"))
            for t in d.get("transactions", []):
                if t.get("chapter") != key:
                    continue
                subj = str(t.get("subject", "")) + str(t.get("note", "")) + str(t.get("type", ""))
                if re.search(r"初始|开户|opening|init", subj, re.IGNORECASE):
                    continue  # 模板开户流水不算章节事件
                return True
        except Exception:
            pass

    # 3) timeline.md 里出现该章号的编年史事件（跳过模板示例占位行）
    tl = state_dir / "timeline.md"
    if tl.exists():
        from novel_utils import has_placeholder
        for line in tl.read_text(encoding="utf-8").splitlines():
            if has_placeholder(line):
                continue  # 模板 [示例] 行不算真实事件
            if line.strip().startswith("-") and re.search(rf"第\s*{num}\s*章", line):
                return True
    # 注：guns/misunderstandings 台账里的"第 N 章"多为模板目标章占位，
    # 不作为状态变更依据（真实变更已由 processed 提案/流水覆盖）。
    return False


def detect_stall(workspace: Path, stall_window: int = None) -> dict:
    """连续 stall_window 章定稿但无任何状态变更 → 塌中段/注水。
    stall_window 缺省时从题材档案取（悬疑/规则怪谈更紧=2，其余=3）。"""
    if stall_window is None:
        stall_window = int((_genre_profile(workspace) or {}).get("stall_window", 3) or 3)
    ms_dir = workspace / "05_manuscript"
    files = sorted(find_manuscript_files(ms_dir) if ms_dir.exists() else [],
                   key=natural_chapter_sort_key)
    chapters = []
    for f in files:
        num = chapter_number_from_name(f.name)
        if num is not None:
            chapters.append((num, f))

    result = {"stalled": False, "stall_runs": [], "per_chapter": [], "window": stall_window}
    if len(chapters) < stall_window:
        result["note"] = f"定稿章节不足 {stall_window} 章，暂不判定塌中段"
        return result

    flags = []
    for num, f in chapters:
        changed = _chapter_had_state_change(workspace, num)
        flags.append((num, changed))
        result["per_chapter"].append({"chapter": f"ch_{num:03d}", "state_changed": changed})

    # 找连续无变更的运行段
    run = []
    for num, changed in flags:
        if not changed:
            run.append(num)
        else:
            if len(run) >= stall_window:
                result["stall_runs"].append({"from": run[0], "to": run[-1], "count": len(run)})
            run = []
    if len(run) >= stall_window:
        result["stall_runs"].append({"from": run[0], "to": run[-1], "count": len(run)})

    result["stalled"] = bool(result["stall_runs"])
    return result


# ---------------------------------------------------------------------------
# B. 黄金配比量化门
# ---------------------------------------------------------------------------
def classify_ratio(text: str) -> dict:
    """粗略把正文分成 对白 / 推进动作 / 静态描写 三类（按句归类，占比为中文字数比）。

    口径：引号内 = 对白；引号外句子按信号词投票，描写信号多→描写，动作信号多→推进，
    都不明显→推进（默认叙事在推进剧情）。
    """
    body = _strip_body(text)
    total = _cjk_count(body)
    if total == 0:
        return {"dialogue": 0, "action": 0, "describe": 0, "total_cjk": 0}

    dialogue = _dialogue_chars(body)
    # 去引号内容后，按句分非对白部分
    non_dialogue = re.sub(r"“[^”]*”", "", body)
    desc_chars = 0
    action_chars = 0
    for sent in _sentences(non_dialogue):
        n = _cjk_count(sent)
        if n == 0:
            continue
        d_score = sum(1 for w in _DESC_HINTS if w in sent)
        a_score = sum(1 for w in _ACTION_HINTS if w in sent)
        if d_score > a_score and d_score >= 1:
            desc_chars += n
        else:
            action_chars += n

    # 对白与非对白（动作+描写）互斥，合计归一化到 100
    dialogue_pct = dialogue / total * 100
    non_dialogue_share = 100 - dialogue_pct
    nd_chars = max(1, action_chars + desc_chars)
    action_pct = non_dialogue_share * action_chars / nd_chars
    describe_pct = non_dialogue_share * desc_chars / nd_chars
    return {
        "dialogue": round(dialogue_pct, 1),
        "action": round(action_pct, 1),
        "describe": round(describe_pct, 1),
        "total_cjk": total,
    }


def ratio_verdict(r: dict, profile: dict = None) -> dict:
    """对照题材基线给三维评分与 WARNING（不硬阻断）。"""
    profile = profile or {}
    baseline = _baseline(profile)
    dialogue_floor = profile.get("dialogue_floor", 20)
    describe_ceiling = profile.get("describe_ceiling", 40)
    warnings = []
    score = 100
    for dim, (lo, hi) in baseline.items():
        v = r.get(dim, 0)
        if v < lo:
            if dim == "dialogue" and v < dialogue_floor:
                warnings.append(f"对白占比 {v}% 偏低（{profile.get('label','通用')} 地板 {dialogue_floor}%），可能通篇旁白、缺乏人物交锋")
                score -= 12
            if dim == "action" and v < lo:
                warnings.append(f"推进/动作占比 {v}% 偏低（基线 {lo}~{hi}%），疑似剧情停滞")
                score -= 15
        elif v > hi + 10:
            if dim == "describe" and v > describe_ceiling:
                warnings.append(f"静态描写占比 {v}% 过高（{profile.get('label','通用')} 天花板 {describe_ceiling}%），疑似注水/风景慢放")
                score -= 15
            elif dim == "dialogue" and v > hi + 15:
                warnings.append(f"对白占比 {v}% 偏高（基线 {lo}~{hi}%），注意是否空谈不推进")
                score -= 6
    return {"score": max(0, score), "warnings": warnings}


def golden_ratio_gate(workspace: Path, chapter: str = None) -> dict:
    profile = _genre_profile(workspace)
    ms_dir = workspace / "05_manuscript"
    files = find_manuscript_files(ms_dir, target_chapter=chapter) if chapter else \
        sorted(find_manuscript_files(ms_dir), key=natural_chapter_sort_key)
    chapters = []
    agg = {"dialogue": 0, "action": 0, "describe": 0, "total_cjk": 0}
    for f in sorted(files, key=natural_chapter_sort_key):
        num = chapter_number_from_name(f.name)
        if num is None:
            continue
        r = classify_ratio(f.read_text(encoding="utf-8"))
        v = ratio_verdict(r, profile)
        chapters.append({
            "chapter": f"ch_{num:03d}", "ratio": r, "score": v["score"], "warnings": v["warnings"],
        })
        for k in ("dialogue", "action", "describe"):
            agg[k] += r[k] * r["total_cjk"] / 100
        agg["total_cjk"] += r["total_cjk"]

    overall = None
    if agg["total_cjk"]:
        overall = {
            "dialogue": round(agg["dialogue"] / agg["total_cjk"] * 100, 1),
            "action": round(agg["action"] / agg["total_cjk"] * 100, 1),
            "describe": round(agg["describe"] / agg["total_cjk"] * 100, 1),
        }
    return {"chapters": chapters, "overall": overall}


# ---------------------------------------------------------------------------
# C. 文风蒸馏
# ---------------------------------------------------------------------------
def _style_features(text: str, workspace: Path = None) -> dict:
    body = _strip_body(text)
    sents = _sentences(body)
    sent_lens = [_cjk_count(s) for s in sents]
    paras = [p for p in body.split("\n") if _cjk_count(p) >= 2]
    para_lens = [_cjk_count(p) for p in paras]
    total = _cjk_count(body) or 1
    dialogue = _dialogue_chars(body)

    # 口癖词表 = 通用雷词 + 题材专属雷词（P3-4）
    ticks = list(_TICKS)
    prof = _genre_profile(workspace) if workspace else {}
    for t in (prof or {}).get("extra_ticks", []):
        if t not in ticks:
            ticks.append(t)
    tick_freq = {t: body.count(t) for t in ticks if body.count(t) > 0}
    # 每千字口癖出现次数
    tick_per_1k = {t: round(c / total * 1000, 2) for t, c in tick_freq.items()}

    def _stats(vals):
        if not vals:
            return {"mean": 0, "median": 0, "p90": 0, "min": 0, "max": 0}
        s = sorted(vals)
        n = len(s)
        return {
            "mean": round(sum(s) / n, 1),
            "median": s[n // 2],
            "p90": s[min(n - 1, int(n * 0.9))],
            "min": s[0], "max": s[-1],
        }

    return {
        "total_cjk": total,
        "sentence_count": len(sents),
        "sentence_len": _stats(sent_lens),
        "paragraph_len": _stats(para_lens),
        "dialogue_density": round(dialogue / total * 100, 1),
        "short_sentence_ratio": round(
            sum(1 for x in sent_lens if x <= 12) / max(1, len(sent_lens)) * 100, 1),
        "tick_per_1k": tick_per_1k,
    }


def distill_style(workspace: Path, chapter: str = None) -> dict:
    """蒸馏全书文风指纹；chapter 给定时额外返回该章与指纹的偏离度。"""
    ms_dir = workspace / "05_manuscript"
    if chapter:
        target = find_manuscript_files(ms_dir, target_chapter=chapter)
        if not target:
            return {"error": f"未找到章节 {chapter} 的定稿"}
        feat = _style_features(target[0].read_text(encoding="utf-8"), workspace)
        fp = _load_or_build_fingerprint(workspace)
        comparison = _compare_to_fingerprint(feat, fp)
        return {"chapter": chapter, "features": feat, "fingerprint": fp.get("features"),
                "comparison": comparison}

    # 全书蒸馏
    files = sorted(find_manuscript_files(ms_dir), key=natural_chapter_sort_key)
    corpus = "\n".join(f.read_text(encoding="utf-8") for f in files)
    feat = _style_features(corpus, workspace)
    fp = {
        "schema": STYLE_SCHEMA,
        "chapter_count": len(files),
        "features": feat,
    }
    _save_fingerprint(workspace, fp)
    return fp


def _load_or_build_fingerprint(workspace: Path) -> dict:
    p = workspace / STYLE_FINGERPRINT_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return distill_style(workspace)


def _save_fingerprint(workspace: Path, fp: dict):
    p = workspace / STYLE_FINGERPRINT_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")


def _compare_to_fingerprint(feat: dict, fp: dict) -> dict:
    base = (fp or {}).get("features") or {}
    deviations = []
    score = 100

    def _dev(label, cur, ref, tol_pct=25, weight=10):
        nonlocal score
        if not ref:
            return
        diff = abs(cur - ref) / ref if ref else 0
        if diff > tol_pct / 100:
            deviations.append(f"{label}: 本章 {cur} vs 全书均值 {ref}（偏离 {diff:.0%}）")
            score -= weight

    _dev("平均句长", feat["sentence_len"]["mean"], base.get("sentence_len", {}).get("mean"), 30, 12)
    _dev("对白密度", feat["dialogue_density"], base.get("dialogue_density"), 40, 8)
    _dev("短句占比", feat["short_sentence_ratio"], base.get("short_sentence_ratio"), 35, 8)
    _dev("平均段长", feat["paragraph_len"]["mean"], base.get("paragraph_len", {}).get("mean"), 40, 6)

    # 口癖：本章每千字次数显著高于全书
    base_ticks = (base.get("tick_per_1k") or {})
    for t, v in feat["tick_per_1k"].items():
        bv = base_ticks.get(t, 0)
        if v >= 1.0 and v > bv * 1.5 + 0.5:
            deviations.append(f"口癖「{t}」本章 {v}/千字，高于全书 {bv}/千字，注意去 AI 味")
            score -= 6

    return {"style_score": max(0, score), "deviations": deviations}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main():
    ap = argparse.ArgumentParser(description="P2 高级质检雷达：塌中段 / 黄金配比 / 文风蒸馏")
    ap.add_argument("--workspace", "-w", help="工作区路径")
    ap.add_argument("--stall", action="store_true", help="塌中段/注水检测")
    ap.add_argument("--ratio", action="store_true", help="黄金配比量化门")
    ap.add_argument("--distill", action="store_true", help="文风蒸馏（全书指纹或单章对比）")
    ap.add_argument("--all", action="store_true", help="全部三项")
    ap.add_argument("-c", "--chapter", help="指定章节（配比/文风对比用）")
    ap.add_argument("--window", type=int, default=3, help="塌中段判定窗口（连续无变更章数）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    ws = resolve_workspace(args.workspace)
    do_all = args.all or not (args.stall or args.ratio or args.distill)
    out = {}

    if args.stall or do_all:
        out["stall"] = detect_stall(ws, stall_window=args.window)
    if args.ratio or do_all:
        out["golden_ratio"] = golden_ratio_gate(ws, chapter=args.chapter)
    if args.distill or do_all:
        out["style"] = distill_style(ws, chapter=args.chapter)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        # 塌中段属硬问题，非零退出
        if out.get("stall", {}).get("stalled"):
            sys.exit(1)
        return

    # 文本输出
    if "stall" in out:
        s = out["stall"]
        print("=" * 70)
        print(" 🪤 塌中段 / 注水检测 (Stall Detector)")
        print("=" * 70)
        if s.get("note"):
            print(" ℹ️ " + s["note"])
        elif s["stalled"]:
            for run in s["stall_runs"]:
                print(f" ⚠️ 第 {run['from']}~{run['to']} 章连续 {run['count']} 章无任何状态变更，疑似塌中段/注水！")
        else:
            print(" ✅ 未发现连续无状态变更的塌陷段落")
        for pc in s.get("per_chapter", []):
            mark = "✅有变更" if pc["state_changed"] else "⚪无变更"
            print(f"    {pc['chapter']}: {mark}")

    if "golden_ratio" in out:
        g = out["golden_ratio"]
        print("\n" + "=" * 70)
        print(" ⚖️ 黄金配比量化门 (对白 / 推进 / 描写)")
        print("=" * 70)
        if g.get("overall"):
            o = g["overall"]
            print(f" 📊 全书均值：对白 {o['dialogue']}% | 推进 {o['action']}% | 描写 {o['describe']}%")
        for c in g.get("chapters", []):
            r = c["ratio"]
            flag = "✅" if c["score"] >= 85 else ("⚠️" if c["warnings"] else "✅")
            print(f" {flag} {c['chapter']}: 对白 {r['dialogue']}% | 推进 {r['action']}% | 描写 {r['describe']}% | 配比分 {c['score']}")
            for w in c["warnings"]:
                print(f"     ⚠️ {w}")

    if "style" in out:
        st = out["style"]
        print("\n" + "=" * 70)
        print(" 🎨 文风蒸馏 (Style Fingerprint)")
        print("=" * 70)
        if "comparison" in st and st.get("comparison"):
            f = st["features"]
            print(f" 📖 章节 {st.get('chapter')} 风格对比（风格分 {st['comparison']['style_score']}）")
            print(f"    平均句长 {f['sentence_len']['mean']} 字 | 对白密度 {f['dialogue_density']}% | 短句占比 {f['short_sentence_ratio']}%")
            for d in st["comparison"]["deviations"]:
                print(f"     ⚠️ {d}")
            if not st["comparison"]["deviations"]:
                print("    ✅ 本章文风与全书指纹基本一致")
        else:
            f = st.get("features", {})
            print(f" ✅ 已蒸馏 {st.get('chapter_count')} 章文风指纹 → {STYLE_FINGERPRINT_FILE}")
            print(f"    平均句长 {f.get('sentence_len',{}).get('mean')} 字 | 中位数 {f.get('sentence_len',{}).get('median')}")
            print(f"    对白密度 {f.get('dialogue_density')}% | 短句占比 {f.get('short_sentence_ratio')}% | 平均段长 {f.get('paragraph_len',{}).get('mean')} 字")
            ticks = f.get("tick_per_1k", {})
            if ticks:
                top = sorted(ticks.items(), key=lambda kv: -kv[1])[:5]
                print("    高频口癖(次/千字): " + ", ".join(f"{t}={v}" for t, v in top))

    if out.get("stall", {}).get("stalled"):
        sys.exit(1)


if __name__ == "__main__":
    _main()
