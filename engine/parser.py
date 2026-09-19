"""Novel Studio 4.0 纯标准库 YAML Front-Matter 与 Markdown 解析器。

无需任何三方依赖（如 PyYAML），安全解析细纲与卷纲。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


def _strip_quotes(val: str) -> str:
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val


def _parse_scalar(val: str) -> Any:
    val = val.strip()
    if not val:
        return ""
    # 去除两端引号
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    # 布尔值
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if val.lower() in ("null", "none", "~"):
        return None
    # 整数
    if re.fullmatch(r"[-+]?\d+", val):
        try:
            return int(val)
        except ValueError:
            pass
    # 浮点数
    if re.fullmatch(r"[-+]?\d+\.\d+", val):
        try:
            return float(val)
        except ValueError:
            pass
    # 空列表或字典与内联列表
    if val == "[]":
        return []
    if val == "{}":
        return {}
    if val.startswith("[") and val.endswith("]"):
        try:
            return json.loads(val)
        except Exception:
            items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
            return items
    return val


def _strip_comment(line: str) -> str:
    """去除行内注释，保留引号内的 #。"""
    in_quote = False
    quote_char = ""
    res = []
    for i, ch in enumerate(line):
        if ch in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif quote_char == ch:
                in_quote = False
                quote_char = ""
            res.append(ch)
        elif ch == "#" and not in_quote:
            break
        else:
            res.append(ch)
    return "".join(res).rstrip()


def _split_key_value(line: str) -> Tuple[str, str]:
    """安全拆分 YAML 键值对，正确处理键包含冒号、引号与 slot 占位符的情况。"""
    s = line.strip()
    if s.endswith(":"):
        return _strip_quotes(s[:-1].strip()), ""
    if s.startswith(('"', "'")):
        q = s[0]
        end_q = s.find(q, 1)
        if end_q != -1:
            rest = s[end_q + 1:].strip()
            if rest.startswith(":"):
                return s[1:end_q], rest[1:].strip()
    k, v = s.split(":", 1)
    return _strip_quotes(k.strip()), v.strip()


def parse_mini_yaml(text: str) -> Dict[str, Any]:
    """使用缩进栈解析符合规范的轻量级 YAML 文本。

    v4.1 确定性契约：**永远使用内置解析器**。旧版会优先尝试 import PyYAML，
    导致同一份细纲在「装了/没装 PyYAML」的不同机器上可能解析出不同结果——
    这直接违背「确定性引擎」定位。内置解析器能力边界（单行值、内联 JSON、
    注释剥离、单对象自动包裹为列表）
    """
    lines = text.splitlines()
    cleaned_lines: List[Tuple[int, str]] = []
    for line in lines:
        stripped = _strip_comment(line)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        cleaned_lines.append((indent, stripped.strip()))

    if not cleaned_lines:
        return {}

    # 递归树状解析
    def _parse_block(start_idx: int, min_indent: int) -> Tuple[Any, int]:
        if start_idx >= len(cleaned_lines):
            return {}, start_idx

        curr_indent, curr_line = cleaned_lines[start_idx]
        is_list = curr_line.startswith("- ")

        if is_list:
            result_list: List[Any] = []
            idx = start_idx
            while idx < len(cleaned_lines):
                ind, line = cleaned_lines[idx]
                if ind < min_indent:
                    break
                if line.startswith("- "):
                    item_content = line[2:].strip()
                    if not item_content:  # 复合对象，下一行开始
                        sub_obj, idx = _parse_block(idx + 1, ind + 2)
                        result_list.append(sub_obj)
                    is_dict_item = False
                    dict_k, dict_v = "", ""
                    if not item_content.startswith("{"):
                        if item_content.startswith(('"', "'")):
                            q = item_content[0]
                            end_q = item_content.find(q, 1)
                            if end_q != -1 and item_content[end_q + 1:].strip().startswith(":"):
                                is_dict_item = True
                                dict_k = item_content[1:end_q]
                                dict_v = item_content[end_q + 1:].strip()[1:].strip()
                        elif ":" in item_content:
                            is_dict_item = True
                            dict_k, dict_v = item_content.split(":", 1)
                            dict_k = _strip_quotes(dict_k.strip())
                            dict_v = dict_v.strip()

                    if is_dict_item:
                        # 字典列表项: - id: "p_001"
                        entry_dict: Dict[str, Any] = {dict_k: _parse_scalar(dict_v)}
                        idx += 1
                        # 收集该条目下相同或更深缩进的子字段
                        while idx < len(cleaned_lines):
                            sub_ind, sub_line = cleaned_lines[idx]
                            if sub_ind <= ind:
                                break
                            if sub_line.startswith("- "):
                                break
                            if ":" in sub_line:
                                sub_k, sub_v = _split_key_value(sub_line)
                                if not sub_v:
                                    sub_sub, idx = _parse_block(idx + 1, sub_ind + 2)
                                    entry_dict[sub_k] = sub_sub
                                else:
                                    entry_dict[sub_k] = _parse_scalar(sub_v)
                                    idx += 1
                            else:
                                idx += 1
                        result_list.append(entry_dict)
                    else:
                        result_list.append(_parse_scalar(item_content))
                        idx += 1
                else:
                    break
            return result_list, idx

        else:
            result_dict: Dict[str, Any] = {}
            idx = start_idx
            while idx < len(cleaned_lines):
                ind, line = cleaned_lines[idx]
                if ind < min_indent:
                    break
                if ":" in line:
                    k, v_str = _split_key_value(line)
                    if not v_str:  # 下级块
                        sub_val, idx = _parse_block(idx + 1, ind + 1)
                        result_dict[k] = sub_val
                    else:
                        result_dict[k] = _parse_scalar(v_str)
                        idx += 1
                else:
                    idx += 1
            return result_dict, idx

    root, _ = _parse_block(0, 0)
    return root if isinstance(root, dict) else {}


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """提取 Markdown 中的 YAML front-matter 及正文内容。"""
    # v4.2.1：允许"只有 frontmatter、无正文"的文件（旧正则要求闭合 --- 后必须有换行+正文，
    # 纯头部细纲会被整体判为无 frontmatter）
    pattern = r"^---\s*\r?\n(.*?)\r?\n---\s*(.*)$"
    match = re.search(pattern, content, flags=re.DOTALL)
    if not match:
        return {}, content
    yaml_text = match.group(1)
    body_text = match.group(2)
    data = parse_mini_yaml(yaml_text)
    return data, body_text


def parse_volume_outline(outline_text: str, chapter_id: str) -> Optional[Dict[str, str]]:
    """从分卷大纲中解析出指定章节（例如 ch_001）的规划数据。"""
    # 匹配形如 ### ch_001: 掌墨借刀 或 ### ch_001 掌墨借刀
    header_pattern = rf"^###\s+{re.escape(chapter_id)}[:\s]*(.*)$"
    lines = outline_text.splitlines()
    found = False
    title = ""
    chunk_lines: List[str] = []

    for line in lines:
        if not found:
            match = re.match(header_pattern, line, re.IGNORECASE)
            if match:
                found = True
                title = match.group(1).strip()
        else:
            if line.startswith("### ") or line.startswith("## ") or line.startswith("---"):
                break
            chunk_lines.append(line)

    if not found:
        return None

    info: Dict[str, str] = {"chapter_id": chapter_id, "title": title}
    kv_pattern = r"^-\s*\*\*(.*?)\*\*[:：]\s*(.*)$"
    for cl in chunk_lines:
        m = re.match(kv_pattern, cl)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if "功能" in key:
                info["function"] = val
            elif "戏眼" in key or "事件" in key:
                info["event"] = val
            elif "实体" in key:
                info["entities"] = val
            elif "伏笔" in key or "信息差" in key:
                info["lines"] = val
            elif "刀口" in key:
                info["cliffhanger"] = val

    return info


def _yaml_str(s: str) -> str:
    """对 YAML 字符串做严格转义（含反斜杠、双引号与换行符），防止破坏格式。"""
    cleaned = str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "\\n")
    return f'"{cleaned}"'


def _yaml_key(k: str) -> str:
    """对包含特殊符号或空格的键添加引号包裹。"""
    s = str(k).strip()
    if any(c in s for c in (':', ' ', '\t', '[', ']', '{', '}', ',', '#', '&', '*', '!', '|', '>', "'", '"', '%', '@', '`')):
        cleaned = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{cleaned}"'
    return s


def dump_mini_yaml(data: Any, indent: int = 0) -> str:
    """将基础 Python 对象安全序列化为格式规范的轻量级 YAML 文本。"""
    if data == {} and indent == 0:
        return "{}"
    if data == [] and indent == 0:
        return "[]"
    lines: List[str] = []
    prefix = " " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            yk = _yaml_key(str(k))
            if v is None:
                lines.append(f"{prefix}{yk}: null")
            elif isinstance(v, bool):
                lines.append(f"{prefix}{yk}: {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{prefix}{yk}: {v}")
            elif isinstance(v, str):
                lines.append(f'{prefix}{yk}: {_yaml_str(v)}')
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{prefix}{yk}: []")
                else:
                    lines.append(f"{prefix}{yk}:")
                    for item in v:
                        if isinstance(item, dict):
                            item_keys = list(item.keys())
                            if not item_keys:
                                lines.append(f"{prefix}  - {{}}")
                            else:
                                first_k = item_keys[0]
                                first_y_k = _yaml_key(str(first_k))
                                first_v = item[first_k]
                                if isinstance(first_v, bool):
                                    lines.append(f"{prefix}  - {first_y_k}: {'true' if first_v else 'false'}")
                                elif isinstance(first_v, (int, float)):
                                    lines.append(f"{prefix}  - {first_y_k}: {first_v}")
                                elif isinstance(first_v, str):
                                    lines.append(f'{prefix}  - {first_y_k}: {_yaml_str(first_v)}')
                                elif first_v is None:
                                    lines.append(f"{prefix}  - {first_y_k}: null")
                                else:
                                    lines.append(f"{prefix}  - {first_y_k}:")
                                    lines.append(dump_mini_yaml(first_v, indent + 6))
                                for rem_k in item_keys[1:]:
                                    rem_y_k = _yaml_key(str(rem_k))
                                    rem_v = item[rem_k]
                                    if isinstance(rem_v, bool):
                                        lines.append(f"{prefix}    {rem_y_k}: {'true' if rem_v else 'false'}")
                                    elif isinstance(rem_v, (int, float)):
                                        lines.append(f"{prefix}    {rem_y_k}: {rem_v}")
                                    elif isinstance(rem_v, str):
                                        lines.append(f'{prefix}    {rem_y_k}: {_yaml_str(rem_v)}')
                                    elif rem_v is None:
                                        lines.append(f"{prefix}    {rem_y_k}: null")
                                    else:
                                        lines.append(f"{prefix}    {rem_y_k}:")
                                        lines.append(dump_mini_yaml(rem_v, indent + 6))
                        elif isinstance(item, bool):
                            lines.append(f"{prefix}  - {'true' if item else 'false'}")
                        elif isinstance(item, (int, float)):
                            lines.append(f"{prefix}  - {item}")
                        elif isinstance(item, str):
                            lines.append(f'{prefix}  - {_yaml_str(item)}')
                        elif item is None:
                            lines.append(f"{prefix}  - null")
                        else:
                            lines.append(f"{prefix}  -")
                            lines.append(dump_mini_yaml(item, indent + 4))
            elif isinstance(v, dict):
                if not v:
                    lines.append(f"{prefix}{yk}: {{}}")
                else:
                    lines.append(f"{prefix}{yk}:")
                    lines.append(dump_mini_yaml(v, indent + 2))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                lines.append(f'{prefix}- {_yaml_str(item)}')
            elif isinstance(item, (int, float)):
                lines.append(f"{prefix}- {item}")
            elif isinstance(item, bool):
                lines.append(f"{prefix}- {'true' if item else 'false'}")
            else:
                lines.append(f"{prefix}-")
                lines.append(dump_mini_yaml(item, indent + 2))
    return "\n".join(lines)

