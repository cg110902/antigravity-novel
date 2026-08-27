"""
State Inspector for Novel Workspace
Scans state files, active Chekhov guns, active misunderstandings, finalized chapter statistics,
and provides Snapshot & Rollback capabilities for multi-branch writing.
Usage:
    python tools/state_inspector.py
    python tools/state_inspector.py
    python tools/state_inspector.py --snapshot ch_003_done
    python tools/state_inspector.py --rollback ch_003_done
    python tools/state_inspector.py --list-snapshots
"""

import sys
import re
import json
import shutil
import argparse
from datetime import datetime
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8

reconfigure_utf8()

def create_snapshot(workspace_dir: Path, snapshot_name: str):
    state_dir = workspace_dir / "04_timeline_and_state"
    if not state_dir.exists():
        print(f"[错误] 状态机目录不存在: {state_dir}")
        return False
    
    snapshots_dir = state_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_name = re.sub(r"[^\w\-.]", "_", snapshot_name) if snapshot_name else "auto"
    snap_folder = snapshots_dir / f"{timestamp}_{clean_name}"
    snap_folder.mkdir(parents=True, exist_ok=True)
    
    # Copy key state files (both md and json ledger)
    copied_files = []
    for pattern in ["*.md", "*.json"]:
        for f in state_dir.glob(pattern):
            if f.is_file():
                shutil.copy2(f, snap_folder / f.name)
                copied_files.append(f.name)
            
    print(f"📸 [快照创建成功] 保存至: 04_timeline_and_state/snapshots/{snap_folder.name}")
    print(f"   - 备份文件: {', '.join(copied_files)}")
    return True

def list_snapshots(workspace_dir: Path):
    snapshots_dir = workspace_dir / "04_timeline_and_state" / "snapshots"
    print("=" * 60)
    print(f" 📂 [状态机历史快照清单] 工作区: {workspace_dir.name}")
    print("=" * 60)
    if not snapshots_dir.exists() or not list(snapshots_dir.iterdir()):
        print("   (暂无任何历史快照)")
        print("=" * 60)
        return
        
    for item in sorted(snapshots_dir.iterdir(), reverse=True):
        if item.is_dir():
            files = [f.name for f in item.iterdir() if f.is_file() and (f.suffix in [".md", ".json"])]
            print(f"   📦 [{item.name}] 包含: {', '.join(files)}")
    print("=" * 60)

def rollback_snapshot(workspace_dir: Path, snapshot_target: str):
    state_dir = workspace_dir / "04_timeline_and_state"
    snapshots_dir = state_dir / "snapshots"
    
    if not snapshots_dir.exists():
        print("[错误] 没有找到任何快照目录！")
        return False
        
    matched_dirs = [d for d in snapshots_dir.iterdir() if d.is_dir() and snapshot_target in d.name]
    if not matched_dirs:
        print(f"[错误] 未找到匹配 '{snapshot_target}' 的快照！")
        list_snapshots(workspace_dir)
        return False
        
    target_dir = sorted(matched_dirs, reverse=True)[0]
    
    # Backup current state before rollback
    auto_backup = snapshots_dir / f"pre_rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    auto_backup.mkdir(parents=True, exist_ok=True)
    for pattern in ["*.md", "*.json"]:
        for f in state_dir.glob(pattern):
            if f.is_file():
                shutil.copy2(f, auto_backup / f.name)
            
    # Restore from target
    restored_files = []
    for pattern in ["*.md", "*.json"]:
        for f in target_dir.glob(pattern):
            if f.is_file():
                shutil.copy2(f, state_dir / f.name)
                restored_files.append(f.name)
            
    print(f"🔄 [回滚成功] 已将状态机复原至快照: {target_dir.name}")
    print(f"   - 恢复文件: {', '.join(restored_files)}")
    print(f"   - 原当前状态已自动安全备份至: {auto_backup.name}")
    return True

def inspect_state(workspace_path=None, as_json=False):
    workspace_dir = resolve_workspace(workspace_path)
    state_report = {
        "workspace": workspace_dir.name,
        "title": "未设置",
        "genre": "通用",
        "pov": "第三人称限制视角",
        "guns": {"planted": 0, "reminded": 0, "resolved": 0, "active_list": []},
        "spatial_temporal_anchor": {"location": "未知", "time": "未明确"},
        "misunderstandings": [],
        "character_growth_arcs": {},
        "manuscript_stats": {"total_chapters": 0, "total_words": 0, "chapters": []}
    }

    # 1. Check Project Bible
    bible_file = workspace_dir / "00_meta" / "project_bible.md"
    if bible_file.exists():
        content = bible_file.read_text(encoding="utf-8")
        title_match = re.search(r"(?:^|\n)\s*[-*]?\s*\*\*书名.*?\*\*\s*[:：]\s*(.*)", content)
        if not title_match:
            title_header = re.search(r"#+\s*《?(.*?)》?\s*(?:项目圣经|设定|档案)", content)
            title = title_header.group(1).strip() if title_header else "未设置"
        else:
            title = title_match.group(1).strip()
            
        genre_match = re.search(r"(?:^|\n)\s*[-*]?\s*\*\*(?:主类型|题材|题材定位).*?\*\*\s*[:：]\s*(.*)", content)
        pov_match = re.search(r"(?:^|\n)\s*[-*]?\s*\*\*视角.*?\*\*\s*[:：]\s*(.*)", content)
        genre = genre_match.group(1).strip() if genre_match else "通用"
        pov = pov_match.group(1).strip() if pov_match else "第三人称限制视角"
        state_report["title"] = title
        state_report["genre"] = genre
        state_report["pov"] = pov

    # 2. Check Chekhov's Guns & Expiry
    guns_file = workspace_dir / "04_timeline_and_state" / "chekhov_guns.md"
    if guns_file.exists():
        content = guns_file.read_text(encoding="utf-8")
        planted = len(re.findall(r"\|\s*(?:Planted|Pending|已埋下)\b", content, re.IGNORECASE))
        reminded = len(re.findall(r"\|\s*(?:Reminded|Active|激化|已激化)\b", content, re.IGNORECASE))
        resolved = len(re.findall(r"\|\s*(?:Resolved|Triggered|已回收|已触发)\b", content, re.IGNORECASE))
        state_report["guns"]["planted"] = planted
        state_report["guns"]["reminded"] = reminded
        state_report["guns"]["resolved"] = resolved
        
        # Parse active guns with expected chapter
        for line in content.splitlines():
            if line.startswith("|") and not line.startswith("| 伏笔 ID") and not line.startswith("|---") and not line.startswith("|:---"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 5:
                    gun_id = parts[0]
                    gun_name = parts[1]
                    status = parts[3]
                    target_ch = parts[4]
                    if not any(k in status.lower() for k in ["resolved", "triggered", "已回收", "已触发"]):
                        state_report["guns"]["active_list"].append({"id": gun_id, "name": gun_name, "status": status, "target_ch": target_ch})

    # 3. Check Current Assets & State Machine
    state_file = workspace_dir / "04_timeline_and_state" / "current_state.md"
    if state_file.exists():
        s_content = state_file.read_text(encoding="utf-8")
        loc_match = re.search(r"(?:[-*]?\s*\*\*当前(?:故事)?地点\*\*|[>🚩]\s*当前(?:故事|空间)?(?:地点|坐标))\s*[:：]\s*(.*)", s_content)
        time_match = re.search(r"(?:[-*]?\s*\*\*当前(?:故事)?时间(?:节点)?\*\*|[>📍]\s*当前(?:故事)?时间(?:锚点)?)\s*[:：]\s*(.*)", s_content)
        loc = loc_match.group(1).strip() if loc_match else "未知"
        ctime = time_match.group(1).strip() if time_match else "未明确"
        state_report["spatial_temporal_anchor"]["location"] = loc
        state_report["spatial_temporal_anchor"]["time"] = ctime

    # 4. Check Misunderstandings
    mis_file = workspace_dir / "04_timeline_and_state" / "misunderstandings.md"
    if mis_file.exists():
        content = mis_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "MIS-" in line and not line.startswith("| ID") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 6:
                    mis_id = parts[0]
                    who = parts[1]
                    target = parts[5]
                    state_report["misunderstandings"].append({"id": mis_id, "parties": who, "target": target})

    # 4.5 Check Character Growth Arcs (Mindset Evolution)
    growth_file = workspace_dir / "04_timeline_and_state" / "character_growth_arcs.md"
    if growth_file.exists():
        g_content = growth_file.read_text(encoding="utf-8")
        for line in g_content.splitlines():
            if line.startswith("|") and not line.startswith("| 角色姓名") and not line.startswith("|---") and not line.startswith("| :---"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 4:
                    cname = parts[0]
                    current_stage = parts[2]
                    strategy = parts[3]
                    clean_cname = re.sub(r"[*_`]", "", cname).strip()
                    state_report["character_growth_arcs"][clean_cname] = {
                        "stage": re.sub(r"[*_`]", "", current_stage).strip(),
                        "strategy": strategy
                    }

    # 5. Check Chapters & Word Count
    manuscript_dir = workspace_dir / "05_manuscript"
    total_words = 0
    total_chapters = 0

    if manuscript_dir.exists():
        finalized_files = sorted([f for f in manuscript_dir.glob("**/finalized/*.md") if not f.name.startswith(".")])
        for ch_file in finalized_files:
            text = ch_file.read_text(encoding="utf-8")
            chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', text))
            total_words += chinese_chars
            total_chapters += 1
            first_line = text.strip().splitlines()[0] if text.strip() else ch_file.stem
            ch_title = re.sub(r"^#+\s*", "", first_line)
            state_report["manuscript_stats"]["chapters"].append({
                "stem": ch_file.stem,
                "title": ch_title,
                "words": chinese_chars
            })
        state_report["manuscript_stats"]["total_chapters"] = total_chapters
        state_report["manuscript_stats"]["total_words"] = total_words

    if as_json:
        print(json.dumps(state_report, ensure_ascii=False, indent=2))
        return state_report

    # Human-Readable Output
    print("=" * 64)
    print(" 🔍 Universal Novel Studio - 状态机与双台账巡检报告")
    print(f" 📂 目标工作区: {workspace_dir.name}")
    print("=" * 64)
    print(f"📖 小说书名: {state_report['title']} | 题材: {state_report['genre']} | POV: {state_report['pov']}")
    print(f"\n🎯 契诃夫之枪 (伏笔台账与爆发雷达):")
    print(f"   - 已埋下 (Planted/Pending) : {state_report['guns']['planted']} | 已激化 (Reminded/Active): {state_report['guns']['reminded']} | 已回收/触发 (Resolved/Triggered): {state_report['guns']['resolved']}")
    for g in state_report["guns"]["active_list"]:
        print(f"   👉 [{g['status']}] {g['id']}: 《{g['name']}》 (预定引爆: {g['target_ch']})")

    print(f"\n📍 实时时空锚点: {state_report['spatial_temporal_anchor']['time']} @ {state_report['spatial_temporal_anchor']['location']}")
    print(f"\n🎭 误会与信息差台账 (发酵中): {len(state_report['misunderstandings'])} 处")
    for m in state_report["misunderstandings"]:
        print(f"   👉 {m['id']}: {m['parties']} (计划引爆: {m['target']})")

    print(f"\n🧠 核心角色心智演进台账 (Growth Arcs):")
    for cname, arc in state_report["character_growth_arcs"].items():
        print(f"   👉 【{cname}】当前处于: {arc['stage']} (策略: {arc['strategy']})")

    print(f"\n📝 稿件进度统计:")
    ch_list = state_report["manuscript_stats"]["chapters"]
    display_list = ch_list if len(ch_list) <= 5 else ch_list[-3:]
    if len(ch_list) > 5:
        print(f"   ... (前 {len(ch_list) - 3} 章已归档收录)")
    for ch in display_list:
        print(f"   ✓ {ch['stem']}: {ch['title']} ({ch['words']} 字)")

    if total_chapters == 0:
        print("   - 暂无定稿章节 (finalized 为空)")
    else:
        print(f"\n📊 全书累计定稿: {total_chapters} 章 | 总字数: 约 {total_words} 字 (均章: {total_words // max(1, total_chapters)} 字)")
    print("=" * 64)
    return state_report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Novel Studio 状态机与双台账巡检工具")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径 (默认为 novel_workspace)")
    parser.add_argument("--snapshot", type=str, nargs="?", const="manual", default=None, help="保存当前状态机快照 (可指定名称)")
    parser.add_argument("--rollback", type=str, default=None, help="回滚至指定的历史快照")
    parser.add_argument("--list-snapshots", action="store_true", help="列出所有可用的历史状态机快照")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出巡检报告")
    args = parser.parse_args()

    ws = resolve_workspace(args.workspace)
    if args.list_snapshots:
        list_snapshots(ws)
    elif args.snapshot is not None:
        create_snapshot(ws, args.snapshot)
    elif args.rollback is not None:
        rollback_snapshot(ws, args.rollback)
    else:
        inspect_state(workspace_path=args.workspace, as_json=args.json)
