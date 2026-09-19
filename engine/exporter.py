"""Novel Studio 成书导出引擎 (engine/exporter.py)。

补齐「从 final/ch_XXX.md 到读者可读的一本书」的最后一公里（路线图 §5.1）：
- export md：书名页 + 分卷结构 + 每卷前情提要页 + 规范化章节标题；
- export txt：纯文本连排版（适配发布平台粘贴）；
- 自动从 state/synopsis.json 生成前情提要（digest）与分卷简介草稿（blurb）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.errors import BusinessError
from engine.ops import _count_words, _ensure_dir, _load_json


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(name)).strip("_") or "book"


def _chapter_num(chapter_id: str) -> int:
    m = re.search(r"(\d+)$", str(chapter_id))
    return int(m.group(1)) if m else 0


def _list_volume_dirs(workspace: Path) -> List[Path]:
    ms = workspace / "manuscript"
    if not ms.exists():
        return []
    return sorted([d for d in ms.glob("vol_*") if d.is_dir()])


def _list_final_chapters(vol_dir: Path) -> List[Path]:
    final = vol_dir / "final"
    if not final.exists():
        return []
    files = [f for f in final.glob("ch_*.md") if f.is_file()]
    return sorted(files, key=lambda f: _chapter_num(f.stem))


def _strip_frontmatter(text: str) -> str:
    # v4.2.1：与 parser.parse_frontmatter 对齐——容忍无正文的纯头部文件
    m = re.match(r"^---\s*\r?\n.*?\r?\n---\s*(.*)$", text, flags=re.DOTALL)
    return m.group(1) if m else text


def _read_project_meta(workspace: Path) -> Dict[str, Any]:
    p = workspace / "project.json"
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _volume_digest(workspace: Path, volume_id: str, chapters: List[Path]) -> List[str]:
    """从 synopsis.json 生成分卷前情提要行。"""
    synopsis = _load_json(workspace / "state" / "synopsis.json", default={})
    lines: List[str] = []
    for cf in chapters:
        cid = cf.stem
        syn = synopsis.get(cid, {}) if isinstance(synopsis, dict) else {}
        title = syn.get("title", "")
        goal = syn.get("dramatic_goal", "")
        if not title and not goal:
            continue
        seg = f"- **{cid}** 《{title}》" if title else f"- **{cid}**"
        if goal:
            seg += f"：{goal}"
        lines.append(seg)
    return lines


def export_book(
    workspace: Path,
    volume_id: Optional[str] = None,
    out_format: str = "md",
    include_digest: bool = True,
) -> Dict[str, Any]:
    """把 manuscript/*/final 的定稿章节装配成读者可读的一本书。

    返回 {"outputs": [路径], "chapters": N, "total_words": N, "missing_volumes": [...]}。
    """
    workspace = Path(workspace)
    meta = _read_project_meta(workspace)
    title = meta.get("title", "未命名小说")
    genre = meta.get("genre", "")
    protagonist = meta.get("protagonist", "")

    vol_dirs = _list_volume_dirs(workspace)
    if volume_id:
        vol_dirs = [d for d in vol_dirs if d.name == volume_id]
        if not vol_dirs:
            raise BusinessError(
                f"未找到分卷目录 manuscript/{volume_id}/",
                solution=f"请确认卷号是否输入正确，或先通过创作流水线封存该卷章节。",
            )


    empty_vols: List[str] = []
    total_words = 0
    total_chapters = 0
    out_name = _safe_filename(title) + (f"_{volume_id}" if volume_id else "")
    ext = "md" if out_format == "md" else "txt"
    out_path = _ensure_dir(workspace / "export") / f"{out_name}.{ext}"

    book: List[str] = []
    if out_format == "md":
        book.append(f"# 《{title}》")
        meta_line = " | ".join(x for x in [f"题材：{genre}" if genre else "", f"主角：{protagonist}" if protagonist else ""] if x)
        if meta_line:
            book.append(f"\n> {meta_line}")
    else:
        book.append(f"《{title}》")
        if genre or protagonist:
            book.append(f"{'题材：' + genre if genre else ''}{'  ｜  ' if genre and protagonist else ''}{'主角：' + protagonist if protagonist else ''}")
        book.append("")

    for vol_dir in vol_dirs:
        chapters = _list_final_chapters(vol_dir)
        if not chapters:
            empty_vols.append(vol_dir.name)
            continue

        vol_label = vol_dir.name
        digest = _volume_digest(workspace, vol_label, chapters) if include_digest else []

        if out_format == "md":
            book.append(f"\n\n## {vol_label}")
            if digest:
                book.append("\n### 📜 前情提要（可置卷首）\n")
                book.extend(digest)
        else:
            book.append(f"\n{'=' * 36}")
            book.append(vol_label)
            book.append("=" * 36)
            if digest:
                book.append("【前情提要】")
                for d in digest:
                    book.append("- " + re.sub(r"\*\*(.+?)\*\*", r"\1", d))
                book.append("")

        for cf in chapters:
            raw = _strip_frontmatter(cf.read_text(encoding="utf-8-sig", errors="replace")).strip()
            lines = [ln for ln in raw.splitlines()]
            # 规范化章节标题：优先取首行 # 标题，统一改写为 「第 N 章 标题」
            heading = ""
            body_start = 0
            for i, ln in enumerate(lines):
                if ln.strip():
                    m = re.match(r"^#\s+(.+)$", ln.strip())
                    heading = m.group(1).strip() if m else ""
                    body_start = i + 1
                    break
            syn = _load_json(workspace / "state" / "synopsis.json", default={}).get(cf.stem, {})
            display = syn.get("title") or heading or cf.stem
            num = _chapter_num(cf.stem)
            chapter_title = f"第 {num} 章 {display}" if num else display

            body_lines = [ln for ln in lines[body_start:]]
            if out_format == "md":
                book.append(f"\n### {chapter_title}\n")
                book.append("\n".join(body_lines).strip())
            else:
                book.append(f"\n【{chapter_title}】\n")
                book.append("\n".join(body_lines).strip())
            total_words += _count_words("\n".join(body_lines))
            total_chapters += 1

    if total_chapters == 0:
        raise BusinessError(
            "未发现任何已封存章节（manuscript/*/final/ch_*.md 为空）",
            solution="成书导出需要至少有一章已定稿并封存的正文，请先完成 Stage 1~5 创作流水线并执行 sync 封存。",
        )


    out_path.write_text("\n".join(book) + "\n", encoding="utf-8")
    return {
        "outputs": [str(out_path)],
        "format": out_format,
        "chapters": total_chapters,
        "total_words": total_words,
        "volumes_exported": [d.name for d in vol_dirs if d.name not in empty_vols],
        "empty_volumes": empty_vols,
    }
