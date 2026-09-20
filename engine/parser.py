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
    # FIND-CT41（P-7·中文弯引号静默失配）：Word/微信粘贴的 `name: “张三”`
    # 旧版带着弯引号原样落账——人物名永久含引号，后续名称匹配、防撞名、
    # 死者检索全部静默失配（匹配不上又叫"查无此人"）。成对出现才剥离。
    if len(val) >= 2 and (
        (val[0] in ("“", "‘") and val[-1] in ("”", "’") and (val[0] == "“") == (val[-1] == "”"))
    ):
        return val[1:-1]
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return _unescape_quoted(val[1:-1])
    return val


def _unescape_quoted(s: str) -> str:
    """反转义 _yaml_str/_yaml_key 输出的双引号内转义，与其成为互逆对。

    v4.3.3 FIND-B：serializer 严格转义（`\\\"`、`\\\\`、`\\n`→`\\\\n`），旧的
    `_strip_quotes` 只剥离引号不做反转义，导致含双引号 / 反斜杠 / 换行的字符串
    经 dump→parse 往返后带字面反斜杠，锁定事实 / 伏笔 desc / 称谓被污染。
    """
    out: List[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if nxt == "t":
                out.append("\t")
                i += 2
                continue
            if nxt in ('"', "'", "\\"):
                out.append(nxt)
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_flow_items(inner: str) -> List[str]:
    """按顶层逗号分割 flow 形态内容，尊重引号内逗号与嵌套花括号/方括号。"""
    items: List[str] = []
    depth = 0
    in_quote = False
    quote_char = ""
    cur: List[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if in_quote:
            cur.append(ch)
            if ch == quote_char and (i == 0 or inner[i - 1] != "\\"):
                in_quote = False
                quote_char = ""
            i += 1
            continue
        if ch in ('"', "'"):
            in_quote = True
            quote_char = ch
            cur.append(ch)
        elif ch in ("{", "["):
            depth += 1
            cur.append(ch)
        elif ch in ("}", "]"):
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if cur:
        items.append("".join(cur))
    return items


def parse_flow_mapping(s: str) -> Dict[str, Any]:
    """解析单行 flow mapping（如 `{life_status: deceased, condition: "病故"}`）。

    v4.3.3 FIND-G：mini-YAML 此前把花括号整串当标量，导致 state_deltas 里
    `\"p_005\": {\"life_status\": \"deceased\"}` 的显式生死契约被当成字符串，
    `isinstance(s_val, dict)` 分支永不可达。此处补上 flow mapping 支持，
    使显式契约通道真正生效。
    """
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return {}
    inner = s[1:-1].strip()
    if not inner:
        return {}
    result: Dict[str, Any] = {}
    for part in _split_flow_items(inner):
        part = part.strip()
        if not part:
            continue
        # 兼容全角冒号与半角冒号（先按全角切，再按半角切）
        if "：" in part:
            k, v = part.split("：", 1)
        elif ":" in part:
            k, v = part.split(":", 1)
        else:
            continue
        result[_strip_quotes(k.strip())] = _parse_scalar(v.strip())
    return result


def _parse_scalar(val: str) -> Any:
    val = val.strip()
    if not val:
        return ""
    # 去除两端引号并反转义（v4.3.3 FIND-B：与 _yaml_str 严格转义互为逆运算）
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return _unescape_quoted(val[1:-1])
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
    # v4.3.3 FIND-G：单行 flow mapping（原名「inline dict」）支持
    if val.startswith("{") and val.endswith("}"):
        return parse_flow_mapping(val)
    if val.startswith("[") and val.endswith("]"):
        try:
            return json.loads(val)
        except Exception:
            # FIND-CT42b（P-6·类型静默漂移）：json 解析失败时旧版退化为逗号切分
            # 并剥掉方括号——字符串值 `"[主角]"` 变成列表 ["主角"]，字段类型从
            # str 静默变 list，下游按字符串消费的代码得到 list（不可下标/不可比较）。
            # 修正：非法 JSON 方括号内容保持原始字符串（宁可类型不变，不做猜测）。
            return val
    return val


def _find_unescaped(s: str, ch: str, start: int = 0) -> int:
    """返回 s 中从 start 起第一个**未转义**的字符 ch 的位置；找不到返回 -1。

    v4.3.3 FIND-B(fuzz)：引号边界扫描此前用 str.find，会把序列化器转义出的
    `\\\"` / `\\'` 误当真正的闭合引号（`"尸瘸'\\\\\\":"` 里的 `\\\"` 被当结尾，
    整串被误判为 `key: value` 的 dict-item 而拦腰截断）。转义引号前面有奇数个
    反斜杠，不算字符串边界。
    """
    i = start
    n = len(s)
    while i < n:
        if s[i] == ch:
            bs = 0
            j = i - 1
            while j >= 0 and s[j] == "\\":
                bs += 1
                j -= 1
            if bs % 2 == 0:
                return i
        i += 1
    return -1


def _strip_comment(line: str) -> str:
    """去除行内注释，保留引号内的 #。"""
    in_quote = False
    quote_char = ""
    res = []
    i = 0
    while i < len(line):
        ch = line[i]
        # v4.3.3 FIND-B(fuzz)：序列化器用 `\"` 转义引号，旧逻辑把转义出的 `"` 误当
        # 引号边界切换状态——`"语头\"b#照"` 里的 `#` 因此被误判为行外注释而截断，
        # 硅失数据。遇到反斜杠时,把其与下一字符一并原样保留,不改变引号跟踪状态。
        if ch == "\\" and i + 1 < len(line):
            res.append(ch)
            res.append(line[i + 1])
            i += 2
            continue
        if ch in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif quote_char == ch:
                in_quote = False
                quote_char = ""
            res.append(ch)
        elif ch == "#" and not in_quote:
            # FIND-CT16（parser P-1·值数据静默截断）：YAML 1.2 规定注释起始 `#`
            # 前必须是空白或行首；旧版引号外遇 `#` 无脑断行，`desc: 货号 C#117`
            # 被截成「货号 C」、`summary: 第#3章` 截成「第」——值数据静默丢失
            # 且零告警。仅当 `#` 位于行首或其前一个字符为空格/tab 时才算注释。
            prev = res[-1] if res else " "
            if prev in (" ", "\t"):
                break
            res.append(ch)
        else:
            res.append(ch)
        i += 1
    return "".join(res).rstrip()


def _split_key_value(line: str) -> Tuple[str, str]:
    """安全拆分 YAML 键值对，正确处理键包含冒号、引号与 slot 占位符的情况。"""
    s = line.strip()
    # FIND-CT42（P-8·值被静默丢弃）：旧版 `s.endswith(":")` 早退把整行当键——
    # 标量值本身以冒号结尾时（`note: 待定:`、`title: 尾声:`）值被静默丢弃，
    # 整行沦为键名。改为先按第一个未转义冒号拆分，仅当右侧 strip 后为空时
    # 才判为"键行（值在下一层）"。
    _k, _v = _split_first_colon(s)
    if _k is not None:
        if _v.strip():
            return _strip_quotes(_k.strip()), _v.strip()
        return _strip_quotes(_k.strip()), ""
    return _strip_quotes(s), ""


def _split_first_colon(s: str) -> Tuple[Optional[str], Optional[str]]:
    """按第一个未处于引号内的冒号拆分为 (key, value)；无冒号返回 (None, None)。"""
    in_quote = False
    qc = ""
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            i += 2
            continue
        if ch in ('"', "'", "“", "”", "‘", "’"):
            if not in_quote:
                in_quote = True
                qc = ch
            elif qc == ch:
                in_quote = False
                qc = ""
        elif ch == ":" and not in_quote:
            return s[:i], s[i + 1:]
        i += 1
    return None, None


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
        # FIND-CT17（parser P-2·树结构静默错位）：缩进计算只数空格（lstrip(" ")），
        # 行首 tab 不计入缩进——用 tab 缩进的嵌套块（Windows 编辑器/VS Code 默认
        # 极易产出）会被判为根级键合并进顶层 dict，或被 min_indent 边界静默截断，
        # 整棵 YAML 树错位且零报错。确定性展开：行首 tab 统一按 4 空格计。
        if "\t" in stripped[: len(stripped) - len(stripped.lstrip(" \t"))]:
            _lead = stripped[: len(stripped) - len(stripped.lstrip(" \t"))]
            stripped = _lead.expandtabs(4) + stripped.lstrip(" \t")
        indent = len(stripped) - len(stripped.lstrip(" "))
        cleaned_lines.append((indent, stripped.strip()))

    if not cleaned_lines:
        return {}

    # 递归树状解析
    def _parse_block(start_idx: int, min_indent: int) -> Tuple[Any, int]:
        if start_idx >= len(cleaned_lines):
            return {}, start_idx

        curr_indent, curr_line = cleaned_lines[start_idx]
        is_list = curr_line.startswith("- ") or curr_line == "-"

        if is_list:
            result_list: List[Any] = []
            idx = start_idx
            while idx < len(cleaned_lines):
                ind, line = cleaned_lines[idx]
                if ind < min_indent:
                    break
                # v4.3.3 FIND-B(fuzz)：dump 对「嵌套 dict/list 复合项」输出裸 `-` 标记行，
                # 旧版只认 `- `（startswith），strip 后的单字符 `-` 匹配不到，导致该复合
                # 项的子结构被静默丢弃、或与后续 list 项错位（写入侧宽容、消费侧无感）。
                if line == "-":
                    sub_obj, idx = _parse_block(idx + 1, ind + 2)
                    result_list.append(sub_obj)
                    continue
                if line.startswith("- "):
                    item_content = line[2:].strip()
                    if not item_content:  # 复合对象，下一行开始
                        sub_obj, idx = _parse_block(idx + 1, ind + 2)
                        result_list.append(sub_obj)
                        continue
                    is_dict_item = False
                    dict_k, dict_v = "", ""
                    if not item_content.startswith("{"):
                        if item_content.startswith(('"', "'")):
                            q = item_content[0]
                            end_q = _find_unescaped(item_content, q, 1)
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
                        idx += 1
                        entry_dict: Dict[str, Any] = {}
                        # v4.3.3 FIND-B(fuzz)：`- k:`（行内值为空、值在下一层缩进块）时，
                        # 旧版把 "" 当值，嵌套块随后被 `startswith("- ")` 的 break 拦腰截断。
                        # 此处行内值为空则递归解析嵌套块作为该键的值。
                        # 下界须为 ind + 4：dict 项初键在 ind+2、同级的 rem 键也在 ind+2，
                        # 初键的值块子键在 ind+4 —— 若用 ind+2 会把 rem 同级键误吞进初键
                        # 值块（fuzz 实锤），用 ind+4 才能停在与初键同层的兄弟键之前。
                        if dict_v == "" and idx < len(cleaned_lines) and cleaned_lines[idx][0] > ind:
                            sub_obj, idx = _parse_block(idx, ind + 4)
                            entry_dict[dict_k] = sub_obj
                        else:
                            entry_dict[dict_k] = _parse_scalar(dict_v)
                        # 收集该条目下相同或更深缩进的子字段
                        while idx < len(cleaned_lines):
                            sub_ind, sub_line = cleaned_lines[idx]
                            if sub_ind <= ind:
                                break
                            if sub_line.startswith("- ") or sub_line == "-":
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
                    # FIND-CT18（parser P-3·多行文本静默蒸发）：YAML 块标量
                    # （`key: |` / `key: >`）旧版把 `|` 当标量值，后续多行内容
                    # 因无冒号被逐行静默丢弃——伏笔 desc/锁定 fact 的多行描述
                    # 整体消失且零告警。内置解析器明确不支持块标量，遇到即显式
                    # 报错（BusinessError → exit 1 + 方案），杜绝静默吞数据。
                    if v_str.strip() in ("|", ">", "|-", ">-", "|+", ">+"):
                        from engine.errors import BusinessError as _BE
                        raise _BE(
                            f"暂不支持 YAML 块标量语法: 字段 [{k}] 使用了 '{v_str.strip()}' 多行文本写法。",
                            solution=(
                                f"请将 [{k}] 的值改为单行加双引号书写（较长文本可在一行内写完，"
                                f"或用 '\\n' 转义表示换行）。当前细纲的该字段若确为多行描述，"
                                f"请压缩为单行后重试。"
                            ),
                        )
                    if not v_str:  # 下级块
                        sub_val, idx = _parse_block(idx + 1, ind + 1)
                        result_dict[k] = sub_val
                    else:
                        # FIND-CT43（P-5·锚点别名字面量化）：`key: &a 值` / `key: *base` /
                        # `<<: *base`（YAML 锚点与合并键）旧版按字面量落入数据结构
                        # （值变成 "&a"、键变成 "<<"）——从标准 YAML 复制片段会得到
                        # 语义错乱的数据而非错误提示。内置解析器不支持，显式报错。
                        _vs = v_str.strip()
                        if _vs.startswith("&") or _vs.startswith("*") or k == "<<":
                            from engine.errors import BusinessError as _BE2
                            raise _BE2(
                                f"暂不支持 YAML 锚点/别名/合并键语法: 字段 [{k}] 的值为 {_vs!r}。",
                                solution=(
                                    "本解析器为确定性内置子集，不支持 &anchor / *alias / << 合并键。"
                                    "请将引用展开为字面值（如把 `*base` 替换为 base 节点的实际内容）后重试。"
                                ),
                            )
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
            elif item is None:
                # v4.3.3 FIND-B(fuzz)：None 落进 else 分支会被 dump 成裸 `-`（值丢失），
                # parse 后变成空结构；显式 dump 为 `- null` 保证往返一致。
                lines.append(f"{prefix}- null")
            else:
                lines.append(f"{prefix}-")
                lines.append(dump_mini_yaml(item, indent + 2))
    return "\n".join(lines)

