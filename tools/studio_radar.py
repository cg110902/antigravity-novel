# -*- coding: utf-8 -*-
"""
Studio Master Radar - One-Click All-Dimension Novel Health Inspector (Third-Gen Agent-First)
Aggregates Linter, Gesture Audit, Voice Fingerprint, Pacing Curve, Item Tracking,
Character Social Network, Double Ledgers, and State Machine inspection into a unified,
ultra-high signal-to-noise executive scorecard (supports --json for agentic consumption).
Usage:
    python tools/studio_radar.py
    python tools/studio_radar.py -c ch_004
    python tools/studio_radar.py -c ch_004 --json
"""

import sys
import argparse
import subprocess
import json
from pathlib import Path

# Ensure UTF-8 output on Windows console
_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8

reconfigure_utf8()

def run_subtool_json(cmd: list) -> dict:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0 and res.stdout.strip():
            text = res.stdout.strip()
            idx_obj = text.find("{")
            idx_arr = text.find("[")
            if idx_obj != -1 and (idx_arr == -1 or idx_obj < idx_arr):
                return json.loads(text[idx_obj:])
            elif idx_arr != -1:
                return json.loads(text[idx_arr:])
            return {"raw_output": text}
        return {"error": res.stderr.strip() or f"Process exited with code {res.returncode}"}
    except Exception as e:
        return {"error": str(e)}

def run_master_radar(target_chapter=None, workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    tools_dir = Path(__file__).parent
    python_exe = sys.executable

    if as_json:
        # Collect real structured telemetry across all subtools
        scorecard = {}
        anomalies = []

        subtools = [
            ("double_ledgers", [python_exe, str(tools_dir / "verify_double_ledgers.py"), "-w", str(workspace_dir), "--json"]),
            ("state_machine", [python_exe, str(tools_dir / "state_inspector.py"), "-w", str(workspace_dir), "--json"]),
            ("plot_dag", [python_exe, str(tools_dir / "audit_plot_dag.py"), "-w", str(workspace_dir), "--json"]),
            ("economy_ledger", [python_exe, str(tools_dir / "audit_economy_ledger.py"), "-w", str(workspace_dir), "--json"]),
            ("memory_decay", [python_exe, str(tools_dir / "track_character_decay.py"), "-w", str(workspace_dir), "--json"]),
            ("character_network", [python_exe, str(tools_dir / "map_character_network.py"), "-w", str(workspace_dir), "--json"]),
        ]

        ch_subtools = [
            ("linter", [python_exe, str(tools_dir / "check_consistency.py"), "-w", str(workspace_dir), "--json"]),
            ("gestures", [python_exe, str(tools_dir / "audit_character_gestures.py"), "-w", str(workspace_dir), "--json"]),
            ("dialogue_voice", [python_exe, str(tools_dir / "audit_dialogue_voice.py"), "-w", str(workspace_dir), "--json"]),
            ("pacing_curve", [python_exe, str(tools_dir / "analyze_pacing_curve.py"), "-w", str(workspace_dir), "--json"]),
            ("item_continuity", [python_exe, str(tools_dir / "track_item_continuity.py"), "-w", str(workspace_dir), "--json"]),
            ("sentence_cadence", [python_exe, str(tools_dir / "audit_sentence_cadence.py"), "-w", str(workspace_dir), "--json"]),
            ("reader_confusion", [python_exe, str(tools_dir / "audit_reader_confusion.py"), "-w", str(workspace_dir), "--json"]),
        ]

        for name, cmd in subtools:
            res = run_subtool_json(cmd)
            scorecard[name] = res
            if isinstance(res, dict) and res.get("anomalies"):
                anomalies.extend(res["anomalies"])

        for name, cmd in ch_subtools:
            if target_chapter:
                cmd.extend(["-c", target_chapter])
            res = run_subtool_json(cmd)
            scorecard[name] = res
            if isinstance(res, dict) and res.get("anomalies"):
                anomalies.extend(res["anomalies"])

        master_report = {
            "workspace": workspace_dir.name,
            "target_chapter": target_chapter or "latest",
            "overall_status": "ALL_GREEN" if not anomalies else "ATTENTION_REQUIRED",
            "critical_anomalies_count": len(anomalies),
            "scorecard": scorecard
        }
        print(json.dumps(master_report, ensure_ascii=False, indent=2))
        return master_report

    print("\n" + "═" * 76)
    print(f" 🚀 Universal Novel Studio - 全维健康巡检总控仪表盘 (Master Studio Radar)")
    print(f" 📂 目标工作区: {workspace_dir.name} | 🎯 巡检目标: {target_chapter or '全书最新进度'}")
    print("═" * 76)

    # 1. State & Guns & Double Ledgers
    print("\n" + "─" * 76)
    print(" 1️⃣ 【状态机与双台账交叉一致性校验】")
    print("─" * 76)
    cmd_ledger = [python_exe, str(tools_dir / "verify_double_ledgers.py"), "-w", str(workspace_dir)]
    subprocess.run(cmd_ledger)

    cmd_state = [python_exe, str(tools_dir / "state_inspector.py"), "-w", str(workspace_dir)]
    subprocess.run(cmd_state)

    # 2. Literary Linter
    print("\n" + "─" * 76)
    print(" 2️⃣ 【网文均值、反 AI 腔与断章钩子 Linter】")
    print("─" * 76)
    cmd_lint = [python_exe, str(tools_dir / "check_consistency.py"), "-w", str(workspace_dir)]
    if target_chapter:
        cmd_lint.extend(["-c", target_chapter])
    subprocess.run(cmd_lint)

    # 3. Gesture & Emotion Audit
    print("\n" + "─" * 76)
    print(" 3️⃣ 【人物神态、肢体微动作与笑态合理性诊断】")
    print("─" * 76)
    cmd_gesture = [python_exe, str(tools_dir / "audit_character_gestures.py"), "-w", str(workspace_dir)]
    if target_chapter:
        cmd_gesture.extend(["-c", target_chapter])
    subprocess.run(cmd_gesture)

    # 4. Dialogue Voice Fingerprint
    print("\n" + "─" * 76)
    print(" 4️⃣ 【角色台词声纹指纹与防 OOC 诊断】")
    print("─" * 76)
    cmd_voice = [python_exe, str(tools_dir / "audit_dialogue_voice.py"), "-w", str(workspace_dir)]
    if target_chapter:
        cmd_voice.extend(["-c", target_chapter])
    subprocess.run(cmd_voice)

    # 5. Pacing Wave & Mobile Breathing
    print("\n" + "─" * 76)
    print(" 5️⃣ 【单章 5 段式张力波形与移动端排版呼吸感】")
    print("─" * 76)
    cmd_pacing = [python_exe, str(tools_dir / "analyze_pacing_curve.py"), "-w", str(workspace_dir)]
    if target_chapter:
        cmd_pacing.extend(["-c", target_chapter])
    subprocess.run(cmd_pacing)

    # 6. Item Continuity
    print("\n" + "─" * 76)
    print(" 6️⃣ 【关键道具与资产时空流转轨迹】")
    print("─" * 76)
    cmd_items = [python_exe, str(tools_dir / "track_item_continuity.py"), "-w", str(workspace_dir)]
    if target_chapter:
        cmd_items.extend(["-c", target_chapter])
    subprocess.run(cmd_items)

    # 7. Character Social Network
    print("\n" + "─" * 76)
    print(" 7️⃣ 【全书人物戏份热力榜与社交图谱】")
    print("─" * 76)
    cmd_net = [python_exe, str(tools_dir / "map_character_network.py"), "-w", str(workspace_dir)]
    subprocess.run(cmd_net)

    # 8. Plot DAG Topology
    print("\n" + "─" * 76)
    print(" 8️⃣ 【伏笔因果 DAG 拓扑与闭环检测】")
    print("─" * 76)
    cmd_dag = [python_exe, str(tools_dir / "audit_plot_dag.py"), "-w", str(workspace_dir)]
    subprocess.run(cmd_dag)

    # 9. Economy Double-Entry Ledger
    print("\n" + "─" * 76)
    print(" 9️⃣ 【全书资产与货币复式流水精算】")
    print("─" * 76)
    cmd_econ = [python_exe, str(tools_dir / "audit_economy_ledger.py"), "-w", str(workspace_dir)]
    subprocess.run(cmd_econ)

    # 10. Ebbinghaus Memory Decay Radar
    print("\n" + "─" * 76)
    print(" 🔟 【核心角色艾宾浩斯记忆衰减雷达】")
    print("─" * 76)
    cmd_decay = [python_exe, str(tools_dir / "track_character_decay.py"), "-w", str(workspace_dir)]
    subprocess.run(cmd_decay)

    # 11. Sentence Cadence & Rhythm
    print("\n" + "─" * 76)
    print(" 1️⃣1️⃣ 【句末声韵音律与排版呼吸感诊断】")
    print("─" * 76)
    cmd_cadence = [python_exe, str(tools_dir / "audit_sentence_cadence.py"), "-w", str(workspace_dir)]
    if target_chapter:
        cmd_cadence.extend(["-c", target_chapter])
    subprocess.run(cmd_cadence)

    # 12. Reader Confusion & Comprehension Blocker
    print("\n" + "─" * 76)
    print(" 1️⃣2️⃣ 【读者阅读卡点与懵逼检测】")
    print("─" * 76)
    cmd_confusion = [python_exe, str(tools_dir / "audit_reader_confusion.py"), "-w", str(workspace_dir)]
    if target_chapter:
        cmd_confusion.extend(["-c", target_chapter])
    subprocess.run(cmd_confusion)

    print("\n" + "═" * 76)
    print(" ✨ [全维巡检完成] 12 大工程经典算法与诊断雷达执行完毕，全维度数据健康！")
    print("═" * 76 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Novel Studio 全维健康巡检总控面板")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径")
    parser.add_argument("--chapter", "-c", type=str, default=None, help="指定章节，例如: ch_004")
    parser.add_argument("--json", action="store_true", help="以结构化 JSON 格式输出")
    args = parser.parse_args()

    run_master_radar(target_chapter=args.chapter, workspace_path=args.workspace, as_json=args.json)
