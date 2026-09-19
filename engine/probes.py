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

# 排除非死亡修辞与虚假语境（守卫：杜绝误报）
_NON_DEATH_GUARDS = [
    r"死死", r"找死", r"该死", r"不死", r"生死", r"要死", r"怕死",
    r"垂死", r"假死", r"濒死", r"想死", r"去死", r"死心", r"死角",
    r"死寂", r"死一般", r"送死", r"死党", r"起死回生", r"誓死",
    r"不知死活", r"哪怕死", r"宁可死", r"纵死", r"就算死",
    r"如果.{0,6}死", r"万一.{0,6}死", r"若是.{0,6}死", r"以为.{0,6}死",
]


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
    for lf in (frontmatter.get("locked_facts") or []):
        lf_str = str(lf)
        if any(k in lf_str for k in ("阵亡", "死亡", "身亡", "击杀", "被杀", "死")):
            for cname, bases in name_to_bases.items():
                if any(len(b) >= 2 and b in lf_str for b in bases):
                    acknowledged_deaths.add(cname)

    c_status = (frontmatter.get("state_deltas") or {}).get("character_status") or {}
    for k, v in c_status.items():
        v_str = str(v).lower()
        if any(w in v_str for w in ("deceased", "dead", "阵亡", "死亡", "身亡", "气绝")):
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
                # 匹配同一分句（35字内，不跨标点句尾）中角色名与死亡语义共现
                pattern = rf"(?:{re.escape(target_name)}[^\n。！？]{{0,35}}(?:{pat})|(?:{pat})[^\n。！？]{{0,35}}{re.escape(target_name)})"
                for m in re.finditer(pattern, text):
                    matched_snippet = m.group(0)
                    # 守卫检查：若包含比喻/非死亡语境，跳过
                    if any(re.search(guard, matched_snippet) for guard in _NON_DEATH_GUARDS):
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
            if not any(stop in spk for stop in ("那人", "对方", "众人", "他们", "我们", "声音", "女子", "男子", "老者", "少年", "修士")):
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
    blind_spots = (frontmatter.get("epistemology") or {}).get("blind_spots", {})

    total_words = _count_total(text)
    p_epistemology = probe_epistemology_leaks(text, blind_spots, name_by_id=name_by_id, present_ids=present_ids)
    p_address = probe_address_matrix(text, persons_db, present_ids=present_ids)
    p_grounding = probe_grounding(text, frontmatter, persons_db=persons_db)
    p_fatalities = probe_unregistered_fatalities(text, frontmatter, persons_db=persons_db, audit_text=audit_text)

    # 阻断级错误：空正文 (0字)、确认级角色认知泄露、未登记角色死亡
    all_passed = (total_words > 0) and p_epistemology["passed"] and p_fatalities["passed"]
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
            "fatalities_and_entities": p_fatalities,
        },
    }
