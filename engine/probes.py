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

    # v4.3：说话人归属重写——旧版「前置优先 + 名字后仅看距离」会把上一句动作主语
    # 错配给后置式对白（“「…」苏晚脱口而出。” 错认成前句的林渊），确认级泄露漏检。
    # 新规则按证据强度分级：句首名+言语动词(后置式铁证) ➔ 名+言语动词/冒号(前置式铁证)
    # ➔ 近距宽松兜底（仅后置宽松，前置宽松正是误配根源，弃用——归属失败宁交疑似级）。
    _SPEECH_VERBS = "说道问答喊吼喝叫嚷骂嘀咕低语咆哮怒斥冷笑回断言讲聊吟哼解释补充嘲讽讥笑喊叫道"

    def _speech_verb_adjacent(tail: str) -> bool:
        """言语动词是否**紧邻**姓名（允许中间夹 1~2 个助词/副词字）。

        v4.3.2 缺陷#34：旧版只要姓名后 25 字窗口内**任意位置**出现动词表中的字
        就判定为说话人。汉语叙述里「说/道/回/答」等字极常见，窗口一宽必然误命中。
        实测 ch_006：「"周老。"（裴砚在喊周伯）\\n\\n周伯的眼睛动了一下。他想说话」
        ——后置式因远处「他想**说**话」的「说」把这句归给了周伯，而实际说话人是裴砚。
        对白归属是认知泄露探针（error 级）的判定基础，错配会同时制造**漏检**
        （真泄露归错人而静默）与**误报**（合法台词被判成本人泄密）。
        """
        # 邻接窗口取 4 字：容纳「忽然笑了一声」「缓缓说道」「压低声音道」这类
        # 副词/状语前置的合法后置式，又能排除「的眼睛动了一下。他想说话」
        # 这种跨句误命中（「说」在第 12 字）。
        return any(v in tail[:4] for v in _SPEECH_VERBS)

    def _find_after(following: str) -> Optional[str]:
        s = following.lstrip("。，、！？：；’\"”」》 \n")
        for name in known:
            if s.startswith(name):
                tail = s[len(name):len(name) + 25]
                if _speech_verb_adjacent(tail):
                    return name
        return None

    def _find_before(context: str) -> Optional[str]:
        for name in known:
            pos = context.rfind(name)
            if pos >= 0:
                tail = context[pos + len(name):]
                if len(tail) <= 25 and (_speech_verb_adjacent(tail)
                                        or tail.rstrip().endswith(("：", ":"))):
                    return name
        return None

    def _find_after_loose(following: str) -> Optional[str]:
        """宽松兜底：仅当名字**紧跟**引号且短距内伴随言语动词时才归属。

        v4.3.2 缺陷#34：旧版只要名字出现在引号后 30 字符内就判为说话人，不要求
        任何言语动词，于是**下一段叙述的动作主语**被大面积误认。实测 ch_006：
        「"周老。"（裴砚在喊周伯）\\n\\n周伯的眼睛动了一下」——"周老。" 被归给周伯；
        「"崔。"她盯着那个残笔，"京里姓崔的官不止一个。"」——沈拂云的台词
        因下一句 "念珠。"裴砚说 落在窗口内而被归给裴砚。
        对白归属是认知泄露探针（error 级）的判定基础，错配会同时制造
        **漏检**（真泄露归错人）与**误报**（合法台词判成泄密），危害远大于归属失败。
        收紧后：名字须出现在引号后 12 字符内，且其后 15 字符内含言语动词；
        否则宁可返回 None 交由疑似级人工复核。
        """
        s = following.lstrip("。，、！？：；’\"”」》 \n")
        for name in known:
            pos = s.find(name)
            if 0 <= pos <= 12:
                tail = s[pos + len(name):pos + len(name) + 15]
                # 言语动词须**紧邻**姓名（允许中间夹一个副词/助词字），否则
                # 「周伯的眼睛动了一下。他想说话」这类叙述会因远处的「说」被误判。
                if _speech_verb_adjacent(tail):
                    return name
        return None

    # v4.3 缺陷#C7：对白识别兼容中文弯引号 “…”、直角引号 「…」 与英文直引号 "…"
    # （旧版只认弯引号，Drafter 若写成直引号对白，认知泄露探针会全军覆没）
    spans: List[Tuple[int, int, str]] = []
    for m in re.finditer(r"[“「](.*?)[”」]", text, flags=re.DOTALL):
        spans.append((m.start(), m.end(), m.group(1)))
    for m in re.finditer(r'"([^"\n]{2,}?)"', text):
        spans.append((m.start(), m.end(), m.group(1)))
    spans.sort(key=lambda s: s[0])
    for m_start, m_end, content in spans:
        start = max(0, m_start - 60)
        speaker = (
            _find_after(text[m_end:m_end + 35])
            or _find_before(text[start:m_start])
            or _find_after_loose(text[m_end:m_end + 35])
        )
        dialogues.append((speaker, content))
    return dialogues


def _secret_keywords(secret: str) -> Tuple[List[str], List[str]]:
    """从盲区机密文本提取关键词，按置信度分两级（v4.2.1 缺陷#16）。

    - strong：完整汉字串 + 全部 4 字滑窗——足具特异性，可作确认级判据；
    - weak：3 字头/尾碎片（如"十分钟""段记忆"）——通用性太强，只允许触发
      疑似级提醒，防止盲区角色说一句日常台词就被判"确认泄露"阻断流水线。
    """
    runs = re.findall(r"[\u4e00-\u9fff]{1,}", secret)
    strong: List[str] = []
    weak: List[str] = []
    for run in runs:
        strong.append(run)
        # v4.4.0 FIND-O：4 字滑窗只在**长机密**（≥8 字）上才有辨识度。旧版对 5~7 字
        # 的短机密也切 4 字窗，把「他其实不是人」切成「他其实不/其实不是/实不是人」
        # 等公共短语，盲区角色一句「他其实不是故意的」就被判成确认级泄露（error
        # 阻断）。短机密只有全串才是强证据；同义改写降级 suspected 交 Auditor 复核。
        if len(run) >= 8:
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
                    # 说话人可归属且盲区角色不在场 → 知情人合法陈述，继续扫描其余对白
                    # FIND-CT21（FN-4·确认级泄露漏检）：旧版此处无条件 break——本章
                    # 第一句合法陈述会永久挡住同一关键词下后续的「本人对白泄密」
                    # 确认级命中，双阻断级探针之一被首句静默废掉。仅 confirmed
                    # 命中才终止本关键词扫描（上方 189 行已 break）。
                    continue

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


def probe_address_matrix(text: str, persons_db: Optional[Dict[str, Any]] = None,
                         present_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """法定称谓落地探针（warning 级）：在场双方同章时，法定称谓从未出现则提醒。

    v4.3.2 缺陷#32：旧版仅以「名字是否在正文出现」判定在场，无法区分**在场**与
    **被提及**。实测 ch_005 崔敬亭全程未出场，只是被裴砚与沈拂云在对话里提到
    （「崔通判说尸格不成立」），探针却要求「崔敬亭→沈拂云 应称沈仵作」落地——
    两人根本不在同一场景，该称谓无从发生。误报会淹没真实疏漏，使探针失去可信度。
    修正：以细纲 `present_characters` 为权威在场名单，只校验**双方均在场**的称谓对。
    """
    persons_db = persons_db or {}
    ungrounded: List[Dict[str, str]] = []
    _present = set(present_ids or [])
    # 在场者的姓名集合（present_ids 为空时退回旧口径，保持向后兼容）
    _present_names = {
        str((persons_db.get(pid) or {}).get("name", "")).strip()
        for pid in _present
    } - {""}
    # v4.3.2 缺陷#33：称谓只能通过**开口说话**落地。旧版只要角色在场就要求其
    # 法定称谓出现，但重伤濒死、昏迷、被缚等无台词角色本就说不出话——实测 ch_006
    # 周伯全程濒死（status_in「重伤·濒死」，只递出半页纸便断气），探针仍要求
    # 「周伯→裴砚 应称裴大人」「周伯→沈拂云 应称云丫头」落地。这类提醒无法通过
    # 任何合理写法消除，只会淹没真实疏漏。改为：仅对**本章确有对白**的角色校验。
    _speakers = {sp for sp, _ in _extract_dialogues_with_speakers(
        text, [str((persons_db.get(i) or {}).get("name", "")).strip() for i in (_present or persons_db)]
    ) if sp}

    for pid, p in persons_db.items():
        speaker = p.get("name", "")
        if not speaker or speaker not in text:
            continue
        # 说话人必须真正在场，而非仅被提及
        if _present and pid not in _present:
            continue
        # 本章没有任何可归属台词的角色，不苛求其称谓落地
        if _speakers and speaker not in _speakers:
            continue
        for tgt, addr in (p.get("address_matrix") or {}).items():
            if not (tgt and tgt in text and addr):
                continue
            # 称谓对象同样必须在场——对不在场者不会当面称呼
            if _present_names and tgt not in _present_names:
                continue
            if addr not in text:
                ungrounded.append({"speaker": speaker, "target": tgt, "expected_address": addr})
    return {
        "name": "法定称谓矩阵探针",
        "passed": len(ungrounded) == 0,
        "ungrounded": ungrounded,
        "detail": ("未发现称谓缺位" if not ungrounded else
                   f"{len(ungrounded)} 条法定称谓本章未落地: " +
                   "；".join(f"{u['speaker']}→{u['target']} 应称「{u['expected_address']}」" for u in ungrounded[:4])),
    }


def probe_grounding(text: str, frontmatter: Dict[str, Any],
                    persons_db: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """伏笔与道具物象落地探针（warning 级）：细纲声明 plant/reveal 的伏笔、流转的道具，
    其名称/物象应至少在正文中出现一次，防止「细纲写了正文忘了写」。

    v4.3.2 缺陷#31：旧版把 `name` 与 `desc` 的全部 bigram 混为一池，命中任意一个即算落地。
    但 desc 是一句自然语言描述，必然混入角色名与通用词——实测 GUN-001
    「死者右手的半枚灯签」/desc「第七具死者右手攥着半枚铜灯签，与裴砚随身那半枚是一对」
    切出的 24 个 token 里，`第七`/`七具`/`死者`/`裴砚` 四个属无区分度通用词。
    把正文中全部「灯签」字样删光后，探针仍因这四个词判定「已落地」而静默。
    伏笔漏写正是本探针唯一的职责，却因此永远抓不到。

    新口径：
    1. `name`（伏笔的标志性物象）为主判据——命中即落地；
    2. 仅当 name 缺失时，才用 desc 的 bigram 兜底，且先剔除在场角色名与停用通用词。
    """
    misses: List[Dict[str, str]] = []

    # 在场角色名（含别名）与通用词一律不作为「物象落地」的判据
    _noise: set = set()
    for _p in (persons_db or {}).values():
        if not isinstance(_p, dict):
            continue
        _nm = str(_p.get("name", "")).strip()
        if _nm:
            _noise.add(_nm)
            for i in range(len(_nm) - 1):
                _noise.add(_nm[i:i + 2])
        for _al in (_p.get("aliases") or []):
            _al = str(_al).strip()
            if _al:
                _noise.add(_al)
                for i in range(len(_al) - 1):
                    _noise.add(_al[i:i + 2])
    _noise |= {
        "死者", "尸身", "尸体", "第一", "第二", "第三", "第四", "第五", "第六", "第七",
        "一具", "二具", "三具", "七具", "右手", "左手", "身上", "随身", "手里", "手中",
        "之后", "之前", "当年", "十年", "今日", "昨夜", "一个", "一处", "一道", "一张",
        "自己", "对方", "他们", "其中", "那半", "半枚", "这个", "那个",
    }

    def _desc_bigrams(desc: str) -> List[str]:
        runs = re.findall(r"[\u4e00-\u9fff]{2,}", desc)
        grams: List[str] = []
        for run in runs[:4]:
            grams.extend(run[i:i + 2] for i in range(0, max(1, len(run) - 1), 1))
        return [g for g in grams if g not in _noise]

    # v4.3：单 dict 形态统一包裹为列表（与 state.py 归一化口径一致）
    raw_fd = frontmatter.get("foreshadowing_deltas") or []
    fd_list = [raw_fd] if isinstance(raw_fd, dict) else (raw_fd if isinstance(raw_fd, list) else [])
    for fd in fd_list:
        if not isinstance(fd, dict):
            continue
        action = str(fd.get("action", "plant")).lower()
        if action not in ("plant", "reveal"):
            continue
        # v4.3.2 缺陷#31（续）：只有 GUN-（实体暗线/信物）才有可供字面核验的物象。
        # KNO-（知情差）与 MIS-（认知偏差）本质是角色脑内的认知状态，靠内心戏与
        # 言行错位来承载，没有对应的字面意象——实测合规正文写足了沈拂云的误判内心戏，
        # 仍被判「漏写 MIS-001」。对这两类做字面匹配只会制造无法消除的噪音，
        # 其落地与否交由 Stage 4A (Auditor) 语义评估。
        _fid = str(fd.get("id", "")).strip().upper()
        if _fid.startswith(("KNO-", "MIS-")):
            continue
        name = str(fd.get("name", "")).strip()
        desc = str(fd.get("desc", "")).strip()
        if name:
            # name 为主判据：整名命中，或其去噪 bigram 命中
            _ngrams = [name] + [g for g in (name[i:i + 2] for i in range(len(name) - 1))
                                if g not in _noise]
            grounded = any(t and t in text for t in _ngrams)
        else:
            tokens = _desc_bigrams(desc)
            grounded = any(t and t in text for t in tokens) if tokens else True
        if not grounded:
            misses.append({"kind": "伏笔", "ref": str(fd.get("id", "")), "hint": name or desc[:20]})

    sd = frontmatter.get("state_deltas") or {}
    raw_it = sd.get("items") or []
    it_list = [raw_it] if isinstance(raw_it, dict) else (raw_it if isinstance(raw_it, list) else [])
    for it in it_list:
        if isinstance(it, dict):
            iname = str(it.get("name", "")).strip()
            iid = str(it.get("id", "")).strip()
            tokens = [t for t in (iname, iid) if t]
            tokens += [g for g in (iname[i:i + 2] for i in range(max(0, len(iname) - 1)))
                       if g not in _noise]
            if tokens and not any(t and t in text for t in tokens):
                misses.append({"kind": "道具", "ref": iid, "hint": iname})

    return {
        "name": "伏笔与道具物象落地探针",
        "passed": len(misses) == 0,
        "misses": misses,
        "detail": ("细纲声明的伏笔/道具均已在正文落地" if not misses else
                   "正文疑似漏写: " + "；".join(f"[{m['kind']}] {m['ref']} ({m['hint']})" for m in misses[:4])),
    }


# 结构化死亡描写语义范式（取代僵化的成语枚举列表）
# 涵盖：系统通告、生理生机终止、致命物理毁灭、明确终结状态、尸体遗骸
_SYSTEM_DEATH_PATTERNS = [
    r"【[^】\n]{0,30}(?:生命体征归零|生命信号.*?(?:消失|湮灭|中断|归零)|已(?:死亡|阵亡|被杀|击杀|抹杀|牺牲|淘汰)|已确认死亡|判定死亡)[^】\n]{0,30}】",
    r"(?:生命体征归零|生命信号.*?(?:消失|湮灭|中断|归零)|已确认死亡|判定死亡)",
]

_VITAL_CESSATION_PATTERNS = [
    r"(?:彻底|完全|已经|早已|瞬间)?(?:失去|停止|毫无|散尽|断绝|没了|断了).{0,4}(?:心跳|呼吸|生机|脉搏|生命迹象|生命体征|生息|气息)",
    r"(?:心跳|呼吸|脉搏|生机|生息).{0,4}(?:停止|断绝|散尽|全无|死绝)",
    r"瞳孔.{0,4}(?:涣散|散大|失去焦距|彻底散开)",
]

_PHYSICAL_DESTRUCTION_PATTERNS = [
    r"(?:碾碎|咬碎|捏碎|轰碎|穿透|贯穿|刺穿|削下|斩落|斩断|撕成|粉碎|拍碎|绞碎|撕碎|砸碎).{0,6}(?:脖颈|咽喉|头颅|心脏|身躯|天灵盖|胸膛|神魂|生机)",
    r"(?:被|遭).{0,8}(?:一击必杀|一击毙命|轰杀|格杀|斩杀|斩首|碎尸|分尸|撕成两半|拍成肉泥|挫骨扬灰|形神俱灭|身首异处|爆头身亡)",
]

_TERMINAL_STATE_PATTERNS = [
    r"(?:当场|彻底|立即|随之|旋即|直接|重重)?(?:气绝|身亡|毙命|暴毙|横尸|断气|咽气|殒命|丧命|丧生|身死|亡故|死透|阵亡|咽下最后一口气|命丧|死于)",
]

_CORPSE_PATTERNS = [
    r"(?:尸体|尸身|残躯|断肢|遗体).{0,10}(?:倒|躺|跌落|僵硬|冰冷|横陈|跌入)",
]

# v4.3.3 BUG#47 分层说明：
#   以下正则属 **L2 语义线索层**——只用于「提醒作者补契约」，不做任何硬裁决。
#   角色是否死亡的权威判定在 state.is_deceased()，只读 life_status 结构化枚举。
#   因此这里漏掉某种汉语写法，后果仅是少一句提醒（作者仍可显式声明 life_status），
#   不会导致死者复活等数据事故；多匹配一条也只是多一句可忽略的 warning。
#   这就是把汉语的不可穷举性隔离在"提醒层"的意义：**词表不完备不再是致命缺陷**。

# L2 泛称停用词：仅用于抑制"未建档说话人"提醒的噪声，非硬裁决依据。
_GENERIC_SPEAKER_STOPWORDS = (
    "那人", "对方", "众人", "他们", "我们", "声音", "女子", "男子", "老者", "少年", "修士",
    # 常见题材泛称补充（同样不追求完备，漏掉只是多一句可忽略的提醒）
    "道友", "前辈", "晚辈", "差役", "小吏", "仆人", "侍女", "掌柜", "伙计", "路人",
    "士兵", "守卫", "同学", "老师", "护士", "医生", "旁人", "有人", "某人",
)

# 排除非死亡修辞与虚假语境（守卫：杜绝误报）
_NON_DEATH_GUARDS = [
    r"死死", r"找死", r"该死", r"不死", r"生死", r"要死", r"怕死",
    r"垂死", r"假死", r"濒死", r"想死", r"去死", r"死心", r"死角",
    r"死寂", r"死一般", r"送死", r"死党", r"起死回生", r"誓死",
    r"不知死活", r"哪怕死", r"宁可死", r"纵死", r"就算死",
    r"如果.{0,6}死", r"万一.{0,6}死", r"若是.{0,6}死", r"以为.{0,6}死",
]

# FIND-CT8：观察/回忆/旁述语境守卫——「裴砚望着脚边的尸体，冰冷僵硬」是观尸句，
# 死亡词描述的是尸体而非裴砚本人；「那年兄长战死」是回忆；「墓前」「遗像」
# 同理。这些语境里 NAME 与死亡词共现绝不等于 NAME 阵亡。
_OBSERVE_MEMORY_GUARDS = [
    r"望[着见]", r"看[着见]", r"瞧[见得]", r"注视", r"凝视", r"扫[了眼]",
    r"脚边", r"身边", r"面前", r"眼前", r"怀里", r"怀里抱着",
    r"尸体", r"尸身", r"遗骸", r"残骸", r"墓碑", r"坟前", r"墓前",
    r"遗像", r"遗物", r"遗稿", r"灵位", r"牌位", r"棺",
    r"想起", r"回想起", r"记得", r"回忆", r"梦里", r"梦中", r"那年",
    r"生前", r"死后", r"逝世", r"祭", r"悼", r"哀", r"奠",
    r"险些.{0,4}死", r"差点.{0,4}死", r"几乎.{0,4}死", r"捡回一条命",
]


def probe_dialogue_ratio(text: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """对白行占比遥测（v4.3.3 新增 · BUG#43）。

    `.agents/skills/dehydrator/SKILL.md` 第 5 节明文规定「对白行占比维持在
    25%~55% 之间」，但引擎此前无任何代码检测——一条可确定性量化、却完全
    无人守护的硬规则。实测 workspace/lantern 16 章有 11 章越界（最低 3.0%
    的独角戏章、最高 63.0% 的纯对话章）。

    判据：非空、非标题行中含成对引号（中英文直角/弯引号均计）的行视为对白行。
    体裁差异很大（独白章、战斗章天然低对白），故只报 warning，不阻断。
    """
    ratio_range = (config or {}).get("dialogue_ratio") or [25, 55]
    try:
        lo, hi = float(ratio_range[0]), float(ratio_range[1])
    except (TypeError, ValueError, IndexError):
        lo, hi = 25.0, 55.0

    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return {"name": "对白占比遥测", "passed": True, "ratio": 0.0,
                "dialogue_lines": 0, "total_lines": 0, "range": [lo, hi],
                "detail": "正文为空，跳过对白占比遥测"}

    dlg = [ln for ln in lines if re.search(r"[\"“”「」『』]", ln)]
    ratio = len(dlg) / len(lines) * 100.0
    passed = lo <= ratio <= hi
    if passed:
        detail = f"对白行 {len(dlg)}/{len(lines)}（{ratio:.1f}%），处于 {lo:.0f}%~{hi:.0f}% 区间"
    elif ratio < lo:
        detail = (f"对白行仅 {len(dlg)}/{len(lines)}（{ratio:.1f}%），低于下限 {lo:.0f}%"
                  f"——叙述压过人物，检查是否大段转述代替了现场交锋")
    else:
        detail = (f"对白行 {len(dlg)}/{len(lines)}（{ratio:.1f}%），高于上限 {hi:.0f}%"
                  f"——接近纯台词剧本，检查是否缺少动作、物象与场景落地")
    return {"name": "对白占比遥测", "passed": passed, "ratio": round(ratio, 1),
            "dialogue_lines": len(dlg), "total_lines": len(lines),
            "range": [lo, hi], "detail": detail}


def probe_unregistered_fatalities(
    text: str,
    frontmatter: Dict[str, Any],
    persons_db: Optional[Dict[str, Any]] = None,
    audit_text: str = "",
) -> Dict[str, Any]:
    """未登记死亡与新实体预警探针（v4.3）。

    扫描正文中的生死事件与新有名角色：
    1. 若正文中出现有名角色的明确死亡描写，但细纲 (beats)、审计报告 (audit) 与台账均未登记，触发告警；
    2. 若正文中高频出现未建档的对白说话人，提示 Auditor 关注建档。
    """
    misses: List[str] = []
    unregistered_speakers: List[str] = []

    # 1. 收集已知在世角色候选列表（包含括号清理后的 base_name 与别名）
    known_chars: Dict[str, Dict[str, Any]] = {}
    name_to_bases: Dict[str, List[str]] = {}

    for pid, prec in (persons_db or {}).items():
        if isinstance(prec, dict):
            pname = prec.get("name") or pid
            known_chars[pname] = prec
            known_chars[pid] = prec
            base = re.sub(r"[（\(].*?[）\)]", "", pname).strip()
            bases = [pname]
            if base and base != pname:
                bases.append(base)
            for alias in prec.get("aliases", []):
                if alias and alias not in bases:
                    bases.append(alias)
            name_to_bases[pname] = bases

    raw_pc = frontmatter.get("present_characters") or []
    pc_list = [raw_pc] if isinstance(raw_pc, (str, dict)) else (raw_pc if isinstance(raw_pc, list) else [])
    for c in pc_list:
        if isinstance(c, dict) and c.get("name"):
            cname = c["name"]
            known_chars[cname] = c
            base = re.sub(r"[（\(].*?[）\)]", "", cname).strip()
            bases = [cname]
            if base and base != cname:
                bases.append(base)
            name_to_bases[cname] = bases
        elif isinstance(c, str):
            known_chars[c] = {"name": c}
            base = re.sub(r"[（\(].*?[）\)]", "", c).strip()
            name_to_bases[c] = [c] if base == c else [c, base]

    # 已声明死亡的角色（在 locked_facts、character_status 或 audit_text 中）
    acknowledged_deaths = set()
    # v4.4.0 FIND-R：'死' 单字对 locked_facts 的**真死亡**判定过于宽泛——「死不承认」
    # 的修辞义会命中，把活人误吞进 acknowledged_deaths，从而对其真正的死亡描写永久静默。
    # 该判定现在是「是否已登记死亡」的确定性闸门，须收敛为明确的死亡措辞 + 角色名共现。
    for lf in (frontmatter.get("locked_facts") or []):
        lf_str = str(lf)
        # 明确的死亡/灭失措辞（去掉宽泛的 '死' 单字；「已死/死因/死于」这类明确语义另行收容）
        _death_phrase = any(k in lf_str for k in ("阵亡", "死亡", "身亡", "击杀", "被杀", "已死", "毙命", "殒命"))
        if _death_phrase:
            for cname, bases in name_to_bases.items():
                if any(len(b) >= 2 and b in lf_str for b in bases):
                    acknowledged_deaths.add(cname)

    c_status = (frontmatter.get("state_deltas") or {}).get("character_status") or {}
    for k, v in c_status.items():
        # v4.3.3 BUG#47：此处与 state._infer_life_status 是同一语义判断，
        # 旧版各自维护一套词表必然漂移（实测「病故」在 state 侧判死、在此侧不判，
        # 于是细纲已声明死亡却仍被探针报"未登记死亡"）。统一复用单一真值函数。
        if isinstance(v, dict):
            _vt = str(v.get("life_status") or v.get("condition") or v.get("status") or v.get("desc") or "")
        else:
            _vt = str(v or "")
        try:
            from engine.state import _infer_life_status as _inf_ls
            _hit = _inf_ls(_vt) == "deceased"
        except Exception:
            _hit = any(w in _vt.lower() for w in ("deceased", "dead", "阵亡", "死亡", "身亡", "气绝"))
        if _hit:
            acknowledged_deaths.add(k)
            if k in known_chars:
                acknowledged_deaths.add(known_chars[k].get("name", k))

    if audit_text:
        # 弹性打捞：审计报告中提及阵亡/死亡/牺牲且包含角色名的任何行均视为已登记
        for line in audit_text.splitlines():
            line_s = line.strip()
            if any(k in line_s for k in ("阵亡", "死亡", "牺牲")):
                for cname, bases in name_to_bases.items():
                    if any(len(b) >= 2 and b in line_s for b in bases):
                        acknowledged_deaths.add(cname)

    # 扫描正文：运用多范式语义分析器，精准捕捉角色阵亡描述
    all_semantic_patterns = (
        _SYSTEM_DEATH_PATTERNS
        + _VITAL_CESSATION_PATTERNS
        + _PHYSICAL_DESTRUCTION_PATTERNS
        + _TERMINAL_STATE_PATTERNS
        + _CORPSE_PATTERNS
    )

    for cname, crec in known_chars.items():
        if len(cname) < 2 or cname in acknowledged_deaths:
            continue
        # 已经死过的角色不在此重复抓
        life = str(crec.get("life_status", "")).lower()
        status = str(crec.get("status", "")).lower()
        if life in ("deceased", "dead") or status in ("deceased", "dead"):
            continue

        bases = name_to_bases.get(cname, [cname])
        found_death = False

        for target_name in bases:
            if len(target_name) < 2 or target_name not in text:
                continue

            for pat in all_semantic_patterns:
                # FIND-CT8（probes L1·假阳性+契约违反）：
                # (1) 共现窗口 35 → 15 字并优先取 NAME 后最近动词——「裴砚望着脚边的
                #     尸体，冰冷僵硬」这类观尸合规句（NAME 与死亡词同在 35 字内但分属
                #     主宾/旁观语境）不再被打成疑似阵亡；
                # (2) 增补观察/回忆/旁述语境守卫（望着尸体≠本人死亡）。
                pattern = rf"(?:{re.escape(target_name)}[^\n。！？]{{0,15}}(?:{pat})|(?:{pat})[^\n。！？]{{0,15}}{re.escape(target_name)})"
                for m in re.finditer(pattern, text):
                    matched_snippet = m.group(0)
                    # 守卫检查：若包含比喻/非死亡/观察回忆语境，跳过
                    if any(re.search(guard, matched_snippet) for guard in _NON_DEATH_GUARDS):
                        continue
                    if any(re.search(guard, matched_snippet) for guard in _OBSERVE_MEMORY_GUARDS):
                        continue
                    misses.append(f"正文描写中【{cname}】疑似阵亡（触发片段: 「{matched_snippet[:30]}」），但细纲与审计报告均未声明登记")
                    acknowledged_deaths.add(cname)
                    found_death = True
                    break
                if found_death:
                    break
            if found_death:
                break

    # 2. 扫描高频对白说话人是否未建档
    known_name_set = set(known_chars.keys())
    for bases in name_to_bases.values():
        known_name_set.update(bases)
    dialogues = _extract_dialogues_with_speakers(text, list(known_name_set))
    speaker_counts: Dict[str, int] = {}
    for spk, _ in dialogues:
        if spk and spk not in known_name_set and len(spk) in (2, 3, 4):
            # v4.3.3 BUG#47 分层说明：泛称停用词同属 L2 提醒层，天然无法穷举
            # （不同题材的泛称差异极大：修真"道友"、军事"士兵"、校园"同学"…）。
            # 因其只影响"是否多一句建档提醒"，不做硬裁决，故不追求完备；
            # 真正的守护在 check 的「未定义 ID 引用」阻断（那里走结构化 ID 校验）。
            if not any(stop in spk for stop in _GENERIC_SPEAKER_STOPWORDS):
                speaker_counts[spk] = speaker_counts.get(spk, 0) + 1

    for spk, cnt in speaker_counts.items():
        if cnt >= 2:
            in_new = any(
                isinstance(ne, dict) and ne.get("name") == spk
                for ne in (frontmatter.get("new_entities") or [])
            )
            in_audit = audit_text and spk in audit_text
            if not in_new and not in_audit:
                unregistered_speakers.append(f"【{spk}】(发言{cnt}次)")

    detail_parts = []
    if misses:
        detail_parts.append("🚨 " + "；".join(misses))
    if unregistered_speakers:
        detail_parts.append("💡 疑似新出场说话人未建档: " + "、".join(unregistered_speakers[:3]))
    if not detail_parts:
        detail_parts.append("正文生死与在场实体均已合账")

    return {
        "name": "未登记死亡与新实体预警探针",
        "passed": len(misses) == 0,
        "misses": misses,
        "unregistered_speakers": unregistered_speakers,
        "detail": " ｜ ".join(detail_parts),
    }


def run_all_probes(text: str, frontmatter: Dict[str, Any],
                   persons_db: Optional[Dict[str, Any]] = None,
                   config: Optional[Dict[str, Any]] = None,
                   audit_text: str = "") -> Dict[str, Any]:
    """运行确定性物理事实与数据探针，输出体检与字数遥测结果。"""
    name_by_id = {}
    for pid, p in (persons_db or {}).items():
        if isinstance(p, dict) and p.get("name"):
            name_by_id[pid] = p["name"]
    # v4.3.2 缺陷#4（首登场角色泄密漏判）：旧版 name_by_id 只取台账。
    # 而首章/新角色登场章在 audit 时人物尚未 sync 入账 ⇒ 盲区角色名解析不到，
    # 「本人对白泄密」被降级成疑似（warning），同一份正文等 sync 之后再 check
    # 又会突然升级为确认级 error，判定随时点漂移。此处并入细纲 present_characters
    # 的 id→name 声明（细纲是 SSOT，优先级高于尚未入账的台账）。
    _raw_pc_names = frontmatter.get("present_characters") or []
    _pc_name_list = [_raw_pc_names] if isinstance(_raw_pc_names, (str, dict)) else (
        _raw_pc_names if isinstance(_raw_pc_names, list) else []
    )
    for _c in _pc_name_list:
        if isinstance(_c, dict) and _c.get("id") and _c.get("name"):
            name_by_id[str(_c["id"]).strip()] = str(_c["name"]).strip()
    # v4.3：present_ids 兼容字符串紧凑形态（[p_001, p_003] 此前被整段跳过，
    # 导致「盲区角色在场，他人公开提及」的疑似级提醒失效）
    present_ids: List[str] = []
    raw_pc = frontmatter.get("present_characters") or []
    pc_list = [raw_pc] if isinstance(raw_pc, (str, dict)) else (raw_pc if isinstance(raw_pc, list) else [])
    for c in pc_list:
        if isinstance(c, dict) and c.get("id"):
            present_ids.append(str(c["id"]).strip())
        elif isinstance(c, str) and c.strip():
            present_ids.append(c.strip())
    # FIND-CT38（漏网补丁）：旧版在此的裸 `.get("blind_spots")` 先于下方形态防御
    # 执行——epistemology 为 list 时 `[].get` 直接 AttributeError（实测
    # check ch_017 崩 exit 4）。旧行删除，统一由下方 FIND-CT22 块防御。
    # FIND-CT22（RB-3+FP-3 组合）：
    # (1) 形态防御——epistemology/blind_spots 被写成 list/标量时旧版裸奔，
    #     check/audit/cruise 三入口连环 exit 4「未预期异常」。非预期形态归一为
    #     {} 并记 form_warning，探针跳过而非崩栈；
    # (2) 姓名键反查——模板未强制 ID 键，首章新角色作者倾向写姓名
    #    （如 {"沈拂云": [...]}）。旧版 name_by_id 只认 ID ⇒ owner_name 永空，
    #    确认级「本人对白泄密」分支不可达，只剩疑似级 warning。用姓名→ID 反向
    #    映射把键归一到 ID（台账/细纲均查）。
    _form_warnings: List[str] = []
    _epi = frontmatter.get("epistemology")
    if _epi is None:
        _epi = {}
    elif not isinstance(_epi, dict):
        _form_warnings.append(
            f"细纲 epistemology 形态非法（{type(_epi).__name__}，应为字典），认知盲区探针已跳过。\n"
            f"      💡 方案：请改为 `epistemology: {{known: ..., blind_spots: ...}}` 字典结构。"
        )
        _epi = {}
    blind_spots = _epi.get("blind_spots") or {}
    if not isinstance(blind_spots, dict):
        _form_warnings.append(
            f"细纲 epistemology.blind_spots 形态非法（{type(blind_spots).__name__}，应为字典），认知盲区探针已跳过。\n"
            f"      💡 方案：请改为 `blind_spots: {{\"p_002\": [\"秘密内容\"]}}` 字典结构。"
        )
        blind_spots = {}
    _name_to_id = {str(_v).strip(): _k for _k, _v in name_by_id.items()}
    _norm_blind: Dict[str, Any] = {}
    for _bk, _bv in blind_spots.items():
        _key = str(_bk).strip()
        _nid = _name_to_id.get(_key)
        if _nid:
            _norm_blind[_nid] = _bv
        elif _key in name_by_id:
            _norm_blind[_key] = _bv
        else:
            # 既非已建档 ID 也非已知姓名：保持原键（owner_name 为空，走疑似级并提示）
            _norm_blind[_key] = _bv
            _form_warnings.append(
                f"认知盲区键 [{_key}] 既不是已建档角色 ID 也不是已知角色姓名，"
                f"该条盲区只能做疑似级提醒。\n      💡 方案：请改用 p_XXX 形式的人物 ID。"
            )
    blind_spots = {
        _k: ([_v] if isinstance(_v, str) else (_v if isinstance(_v, list) else [_v]))
        for _k, _v in _norm_blind.items()
    }

    total_words = _count_total(text)
    # v4.3.3 BUG#42：config 此前收而不用——字数遥测只判 >0，体量偏离要等 sync
    # 入账之后才由 ops 警告，体检阶段（check/audit）对 24 字的残章报「✅ 通过」，
    # 拦截时机完全失位。此处让探针按项目配置的 words_per_chapter 做体量遥测。
    _wpc = (config or {}).get("words_per_chapter") or [1500, 2600]
    try:
        _wc_min, _wc_max = int(_wpc[0]), int(_wpc[1])
    except (TypeError, ValueError, IndexError):
        _wc_min, _wc_max = 1500, 2600
    _words_detail = f"当前 {total_words} 字（参考区间 {_wc_min}~{_wc_max}）"
    _words_level = "ok"
    if total_words <= 0:
        _words_detail = "正文内容为空（0 字）"
        _words_level = "empty"
    elif total_words < _wc_min * 0.5:
        _words_detail = f"当前 {total_words} 字，不足标准下限（{_wc_min} 字）的一半，疑为残章或截断"
        _words_level = "severe_short"
    elif total_words < _wc_min:
        _words_detail = f"当前 {total_words} 字，低于参考下限 {_wc_min} 字"
        _words_level = "short"
    elif total_words > _wc_max:
        _words_detail = f"当前 {total_words} 字，超出参考上限 {_wc_max} 字"
        _words_level = "long"
    p_epistemology = probe_epistemology_leaks(text, blind_spots, name_by_id=name_by_id, present_ids=present_ids)
    p_address = probe_address_matrix(text, persons_db, present_ids=present_ids)
    p_grounding = probe_grounding(text, frontmatter, persons_db=persons_db)
    p_fatalities = probe_unregistered_fatalities(text, frontmatter, persons_db=persons_db, audit_text=audit_text)
    p_dialogue = probe_dialogue_ratio(text, config=config)

    # 阻断级错误：仅空正文 (0字) 与确认级角色认知泄露（probes.py 模块 docstring
    # 与 check.py 头注释共同承诺的「阻断级仅 2」契约）。
    # FIND-CT8（probes L1）：未登记死亡回归 L2 提醒层——BUG#47 分层治理注释明言
    # 这批语义正则「只用于提醒、不做硬裁决」，旧版却把 p_fatalities 纳入
    # all_passed 并经 check 升级为 error：既违背契约，又会因 35 字共现窗口无
    # 观察守卫把「望着尸体冰冷僵硬」这类每章必现合规句打成 exit 1 硬阻断。
    # 现降为 warning（misses 仍随 summary 输出交 Auditor 审阅）。
    all_passed = (total_words > 0) and p_epistemology["passed"]
    return {
        "all_passed": all_passed,
        "word_count": total_words,
        "form_warnings": _form_warnings,
        "summary": {
            "words": {
                "name": "正文字数遥测",
                "word_count": total_words,
                "passed": total_words > 0,
                # BUG#42：level 供消费侧分级展示；仍只有「空正文」是阻断级，
                # 体量偏离属创作自由，报 warning 由作者定夺（短章/长章都可能是有意为之）。
                "level": _words_level,
                "words_range": [_wc_min, _wc_max],
                "detail": _words_detail,
            },
            "epistemology": p_epistemology,
            "address": p_address,
            "grounding": p_grounding,
            "fatalities_and_entities": p_fatalities,
            "dialogue_ratio": p_dialogue,
        },
    }
