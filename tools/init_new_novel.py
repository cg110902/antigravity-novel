# -*- coding: utf-8 -*-
"""
Universal Novel Initialization & Reset Tool (init_new_novel.py)
Initializes or force-resets the novel workspace by dynamically rendering templates from templates/.
Automatically syncs project metadata to novel_config.yaml.

Usage:
    python tools/init_new_novel.py --title "星际深渊" --genre "硬核科幻 / 幽闭悬疑" --protagonist "陈昂"
    python tools/init_new_novel.py --clean
"""

import sys
import os
import shutil
import argparse
import re
from pathlib import Path

_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from novel_utils import resolve_workspace, reconfigure_utf8

reconfigure_utf8()

def clean_workspace_manuscripts(workspace: Path):
    """Cleans all drafts, beats, exported manuscripts, and snapshots."""
    # Clean manuscripts
    ms_dir = workspace / "05_manuscript"
    if ms_dir.exists():
        for f in ms_dir.glob("**/*"):
            if f.is_file() and not f.name.startswith("."):
                try:
                    f.unlink()
                except Exception:
                    pass

    # Clean beats
    outlines_dir = workspace / "03_outlines"
    if outlines_dir.exists():
        for f in outlines_dir.glob("**/beats/*.md"):
            if not f.name.startswith("."):
                try:
                    f.unlink()
                except Exception:
                    pass

    # Clean snapshots
    snap_dir = workspace / "04_timeline_and_state" / "snapshots"
    if snap_dir.exists():
        for d in snap_dir.glob("*"):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

    # Clean full novel exports
    for exp_file in ["full_novel.md", "full_novel.txt"]:
        p = workspace / exp_file
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

def sync_novel_config(title: str, genre: str, root_dir: Path):
    """Syncs novel project title and genre into root novel_config.yaml."""
    cfg_path = root_dir / "novel_config.yaml"
    if cfg_path.exists():
        try:
            content = cfg_path.read_text(encoding="utf-8")
            content = re.sub(r'(name:\s*)"[^"]*"', f'\\1"{title}"', content)
            content = re.sub(r'(default_genre:\s*)"[^"]*"', f'\\1"{genre}"', content)
            cfg_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            pass
    return False

def render_template_file(template_path: Path, replacements: dict) -> str:
    """Reads a template file and replaces placeholders."""
    if not template_path.exists():
        return ""
    content = template_path.read_text(encoding="utf-8")
    for k, v in replacements.items():
        content = content.replace(k, v)
    return content

def init_novel(title="未命名新书", genre="通用题材", protagonist="主角名", clean_only=False, workspace_path=None):
    workspace = resolve_workspace(workspace_path)
    root_dir = workspace.parent
    templates_dir = root_dir / "templates"

    print("=" * 68)
    print(f" 🚀 Universal Novel Studio - 全题材项目初始化与母版创生引擎")
    print(f" 📂 目标工作区: {workspace.name} (绝对路径: {workspace})")
    print(f" 📖 新书标题: 《{title}》 | 题材: {genre} | 核心主角: {protagonist}")
    print("=" * 68)

    # 1. Ensure Full Directory Topology Exists
    dirs = [
        workspace / "00_meta",
        workspace / "01_world",
        workspace / "02_characters" / "profiles",
        workspace / "02_characters" / "templates",
        workspace / "03_outlines" / "vol_01" / "beats",
        workspace / "04_timeline_and_state" / "snapshots",
        workspace / "05_manuscript" / "vol_01" / "raw_drafts",
        workspace / "05_manuscript" / "vol_01" / "finalized",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("# keep directory structure\n", encoding="utf-8")

    # 2. Clean Existing Artifacts
    clean_workspace_manuscripts(workspace)
    
    if clean_only:
        print("✨ [清空完成] 已清空所有手稿、分章细纲与历史快照。")
        return

    # Clean old character profiles when initializing
    profiles_dir = workspace / "02_characters" / "profiles"
    if profiles_dir.exists():
        for pf in profiles_dir.glob("*.md"):
            if not pf.name.startswith("."):
                try:
                    pf.unlink()
                except Exception:
                    pass

    # Replacement dictionary
    replacements = {
        "[《书名》]": f"《{title}》",
        "《[书名]》": f"《{title}》",
        "[书名]": title,
        "[如：玄幻脑洞 / 科幻末世 / 规则怪谈 / 悬疑惊悚 / 都市异能 / 历史架空 / 诡秘领主]": genre,
        "[主类型]": genre,
        "[通用题材]": genre,
        "[主角姓名]": protagonist,
        "[主角名]": protagonist,
        "[角色名]": protagonist,
        "[本卷卷名]": "破局立足与名动一方",
        "《[首卷卷名]》": "破局立足与名动一方",
        "[首卷卷名]": "破局立足与名动一方",
        "[起始章]": "1",
        "[结束章]": "30",
        "[X]": "1",
        "[章节核心看点标题]": "破局之始！初显锋芒",
    }

    # Helper function to write from template or fallback
    def write_from_template(rel_template_path: str, target_rel_path: str, fallback_content: str):
        t_file = templates_dir / rel_template_path
        target_file = workspace / target_rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if t_file.exists():
            content = render_template_file(t_file, replacements)
            target_file.write_text(content, encoding="utf-8")
        else:
            target_file.write_text(fallback_content, encoding="utf-8")

    # 3. 00_meta/project_bible.md
    write_from_template(
        "00_meta/project_bible.template.md",
        "00_meta/project_bible.md",
        f"# 小说项目圣经 (Project Bible)\n\n## 1. 基本信息\n- **书名（主选）**：《{title}》\n- **主类型**：{genre}\n"
    )

    # 4. 01_world/
    write_from_template("01_world/world_rules.template.md", "01_world/world_rules.md", "# 世界底层规则与力量/经济体系\n")
    write_from_template("01_world/factions.template.md", "01_world/factions.md", "# 势力分布与博弈格局\n")
    write_from_template("01_world/geography.template.md", "01_world/geography.md", "# 地理空间与距离尺度\n")

    # 5. 02_characters/
    write_from_template("02_characters/character_index.template.md", "02_characters/character_index.md", "# 核心角色索引表\n")
    write_from_template("02_characters/character_card.template.md", "02_characters/profiles/protagonist.md", f"# 角色姓名：{protagonist} (主角)\n")
    write_from_template("02_characters/character_card.template.md", "02_characters/templates/character_card_template.md", "# 角色姓名：[角色名] ([身份定位])\n")

    # 6. 03_outlines/
    write_from_template("03_outlines/main_plot.template.md", "03_outlines/main_plot.md", "# 全书主线大纲\n")
    write_from_template("03_outlines/volume_outline.template.md", "03_outlines/vol_01_outline.md", "# 第 1 卷卷纲\n")
    write_from_template("03_outlines/chapter_beats.template.md", "03_outlines/vol_01/beats/ch_001_beats.md", "# 第 1 章 Beats 细纲\n")

    # 7. 04_timeline_and_state/
    write_from_template("04_timeline_and_state/current_state.template.md", "04_timeline_and_state/current_state.md", "# 实时状态机\n")
    write_from_template("04_timeline_and_state/timeline.template.md", "04_timeline_and_state/timeline.md", "# 故事编年史\n")
    write_from_template("04_timeline_and_state/chekhov_guns.template.md", "04_timeline_and_state/chekhov_guns.md", "# 契诃夫之枪\n")
    write_from_template("04_timeline_and_state/misunderstandings.template.md", "04_timeline_and_state/misunderstandings.md", "# 误会与信息差台账\n")
    write_from_template("04_timeline_and_state/character_growth_arcs.template.md", "04_timeline_and_state/character_growth_arcs.md", "# 核心人物动态成长与心智演进总台账\n")
    write_from_template("04_timeline_and_state/economy_ledger.template.json", "04_timeline_and_state/economy_ledger.json", '{\n  "resource_pools": {}\n}\n')

    # 8. Sync Root novel_config.yaml
    synced = sync_novel_config(title, genre, root_dir)

    print(f"✨ [初始化成功] 小说《{title}》全套标准化资产已从 templates/ 母版中心生成至: {workspace.name}/")
    print("   - 00_meta/project_bible.md (项目圣经)")
    print("   - 01_world/ (世界观、势力格局、地理空间与防通胀购买力锚定表)")
    print("   - 02_characters/ (角色索引表、主角人物卡与标准人物卡母版)")
    print("   - 03_outlines/ (全局主线、首卷卷纲与第 1 章 Beats 细纲)")
    print("   - 04_timeline_and_state/ (状态机、编年史、心智台账、多资源复式账本、伏笔池、误会台账)")
    print("   - 05_manuscript/vol_01/ (手稿目录与微创处方单目录)")
    if synced:
        print("   - novel_config.yaml (全局配置已自动同步更新书名与题材)")
    print("=" * 68)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Novel Studio 项目初始化与脚手架创生工具")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径 (默认为 novel_workspace)")
    parser.add_argument("--title", "-t", type=str, default="未命名新书", help="小说书名")
    parser.add_argument("--genre", "-g", type=str, default="通用题材", help="小说题材分类")
    parser.add_argument("--protagonist", "-p", type=str, default="主角名", help="主角姓名")
    parser.add_argument("--clean", action="store_true", help="清空已有稿件、细纲与快照，保留世界观母版")
    args = parser.parse_args()

    init_novel(title=args.title, genre=args.genre, protagonist=args.protagonist, clean_only=args.clean, workspace_path=args.workspace)
