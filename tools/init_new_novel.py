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

from novel_utils import resolve_workspace, reconfigure_utf8, project_root

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

def init_novel(title="未命名新书", genre="通用题材", protagonist="主角名", clean_only=False,
               workspace_path=None, force=False):
    workspace = resolve_workspace(workspace_path)
    # 模板母版始终来自仓库根目录（脚本所在 tools/ 的上一级），与工作区位置无关。
    # 旧代码用 workspace.parent/templates，导致 -w 指向仓库外时静默退化为极简 fallback。
    root_dir = project_root()
    templates_dir = root_dir / "templates"

    if not templates_dir.exists():
        print(f"❌ [致命错误] 未找到模板母版目录: {templates_dir}")
        print("   请确认在 Universal Novel Studio 仓库根目录内运行，且 templates/ 目录完整。")
        return False

    print("=" * 68)
    print(f" 🚀 Universal Novel Studio - 全题材项目初始化与母版创生引擎")
    print(f" 📂 目标工作区: {workspace.name} (绝对路径: {workspace})")
    print(f" 📖 新书标题: 《{title}》 | 题材: {genre} | 核心主角: {protagonist}")
    print("=" * 68)

    # 防止误操作：工作区已存在定稿/细纲/状态机时，必须显式 --force 才会清空重建。
    existing_manuscripts = list((workspace / "05_manuscript").glob("**/ch_*.md")) if (workspace / "05_manuscript").exists() else []
    existing_beats = list((workspace / "03_outlines").glob("**/beats/ch_*_beats.md")) if (workspace / "03_outlines").exists() else []
    if (existing_manuscripts or existing_beats) and not force:
        print(f"⚠️ [中止] 工作区 {workspace} 已存在 {len(existing_manuscripts)} 份手稿 / {len(existing_beats)} 份细纲。")
        print("   初始化会清空这些内容。如确认要重开，请追加 --force；仅清空稿件请使用 `studio.py clean`。")
        return False

    # 1. Ensure Full Directory Topology Exists
    dirs = [
        workspace / "00_meta",
        workspace / "01_world",
        workspace / "02_characters" / "profiles",
        workspace / "02_characters" / "templates",
        workspace / "03_outlines" / "vol_01" / "beats",
        workspace / "04_timeline_and_state" / "snapshots",
        workspace / "04_timeline_and_state" / "state_inbox" / "processed",
        workspace / "04_timeline_and_state" / "state_inbox" / "failed",
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
        return True

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
        "[角色姓名]": protagonist,
        "[身份定位]": "核心主角",
        "[本卷卷名]": "破局立足与名动一方",
        "《[首卷卷名]》": "破局立足与名动一方",
        "[首卷卷名]": "破局立足与名动一方",
        "[起始章]": "1",
        "[结束章]": "30",
        "[X]": "1",
        "[章节核心看点标题]": "破局之始！初显锋芒",
    }

    missing_templates = []

    # Helper function to write from template (missing templates are reported, never silent)
    def write_from_template(rel_template_path: str, target_rel_path: str, fallback_content: str):
        t_file = templates_dir / rel_template_path
        target_file = workspace / target_rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if t_file.exists():
            content = render_template_file(t_file, replacements)
            target_file.write_text(content, encoding="utf-8")
        else:
            # 母版缺失属于工程异常：写入 fallback 占位并记录，最终显式告警。
            target_file.write_text(fallback_content, encoding="utf-8")
            missing_templates.append(rel_template_path)

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

    # 7.5 State-inbox guide (structured mutation proposals)
    inbox = workspace / "04_timeline_and_state" / "state_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "README.md").write_text(
        "# 状态变更提案投递箱 (State Inbox)\n\n"
        "章节定稿后，把结构化的状态变更提案（JSON）放入本目录，再运行：\n\n"
        "```\n"
        "python studio.py apply        # 确定性地合并进 6 大状态文件并自动记账\n"
        "python studio.py sync ch_xxx  # 也会自动先合并本目录提案，再校验并打快照\n"
        "```\n\n"
        "提案格式（schema: novel-studio.state-mutation/v1）：\n"
        "- `current_state`：时空锚点/在场角色/境界/伤势/资产/局势（按字段更新）\n"
        "- `guns`：伏笔 plant/update/resolve（id 可省略，自动编号）\n"
        "- `misunderstandings`：误会 plant/update/resolve\n"
        "- `growth_arcs`：角色心智阶段更新\n"
        "- `timeline`：编年史事件追加（幂等去重）\n"
        "- `transactions`：复式账本流水（delta 正=收入负=支出，余额由流水自动重算）\n"
        "- `synopsis`：（可选）本章 2~3 句精炼梗概 + `chapter_title`，登记进章节梗概脊柱\n"
        "  chapter_synopsis.json（source=manual，优先于自动梗概，供 pack 防场景/情节重复）\n\n"
        "合并成功的提案自动移入 processed/，校验失败的移入 failed/。\n\n"
        "## 记忆与上下文引擎（P1，纯本地零 Token）\n"
        "- `python studio.py pack ch_xxx --budget 6000`：打包语境并按 token 预算裁剪（报告裁掉了什么）；\n"
        "  pack 会自动注入「全书梗概脊柱」「BM25 资料员召回的相关旧段落」「跨章重复预警」。\n"
        "- `python studio.py memory spine`：扫描定稿章节，为缺失梗概的章节补自动梗概。\n"
        "- `python studio.py memory recall \"铁壁公司 芯片\"`：BM25 召回最相关的旧章节段落。\n"
        "- `python studio.py memory repeat`：跨章重复检测（已登场角色被再次首次介绍 / n-gram 雷同 / 场景节拍相似）。\n",
        encoding="utf-8")

    # 8. Sync Root novel_config.yaml —— 仅当工作区位于本仓库内时才回写仓库配置，
    # 避免 -w 指向仓库外（或测试临时目录）时污染仓库的 novel_config.yaml。
    synced = False
    try:
        if workspace.parent.resolve() == root_dir.resolve():
            synced = sync_novel_config(title, genre, root_dir)
    except Exception:
        synced = False

    print(f"✨ [初始化成功] 小说《{title}》全套标准化资产已从 templates/ 母版中心生成至: {workspace.name}/")
    print("   - 00_meta/project_bible.md (项目圣经)")
    print("   - 01_world/ (世界观、势力格局、地理空间与防通胀购买力锚定表)")
    print("   - 02_characters/ (角色索引表、主角人物卡与标准人物卡母版)")
    print("   - 03_outlines/ (全局主线、首卷卷纲与第 1 章 Beats 细纲)")
    print("   - 04_timeline_and_state/ (状态机、编年史、心智台账、多资源复式账本、伏笔池、误会台账)")
    print("   - 05_manuscript/vol_01/ (手稿目录与微创处方单目录)")
    if synced:
        print("   - novel_config.yaml (全局配置已自动同步更新书名与题材)")
    if missing_templates:
        print("\n⚠️ [警告] 以下母版文件缺失，已用极简占位内容代替，请补齐 templates/ 母版：")
        for mt in missing_templates:
            print(f"   - {mt}")
    print("=" * 68)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Novel Studio 项目初始化与脚手架创生工具")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="目标小说工作区路径 (默认为 novel_workspace)")
    parser.add_argument("--title", "-t", type=str, default="未命名新书", help="小说书名")
    parser.add_argument("--genre", "-g", type=str, default="通用题材", help="小说题材分类")
    parser.add_argument("--protagonist", "-p", type=str, default="主角名", help="主角姓名")
    parser.add_argument("--clean", action="store_true", help="清空已有稿件、细纲与快照，保留世界观母版")
    parser.add_argument("--force", action="store_true", help="工作区已有手稿/细纲时仍强制重建（危险：会清空已有稿件）")
    args = parser.parse_args()

    ok = init_novel(title=args.title, genre=args.genre, protagonist=args.protagonist,
                    clean_only=args.clean, workspace_path=args.workspace, force=args.force)
    sys.exit(0 if ok else 1)
