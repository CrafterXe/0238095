"""人物项目：从 initial files/ 生成人物设定模板。

核心原则：
- 无论源文件是否有内容，都生成一份完整的 人物设定.md（可以是全空白模板）。
- 模型只做辅助填充：有原文依据才填，没有依据的字段保持空白，绝不编造。
- 用户可把示例对话/正反例写进 initial files/用户补充.md，原样附到第五节。
- 输出只有 memory settings/initial memories/人物设定.md；手工编写的 00- 规则文件保留。
"""
import json
import re

import config
from core import llm

PROFILE_FILENAME = "人物设定.md"
SUPPLEMENT_FILENAME = "用户补充.md"

_EMOTIONS = ("兴奋", "开心", "生气", "尴尬", "回避", "敷衍", "安慰人")

_EXTRACT_SYSTEM = (
    "你是人设提取器。阅读文本，按字段提取人物设定，只输出一个 JSON 对象。"
    "【字段定义】"
    "name=姓名；identity=身份/职业；relation=与用户的关系；address_user=对用户的称呼方式；"
    "personality_core=核心性格(2个词+一句解释)；trigger=被踩雷时的反应；cares=在意的东西；"
    "emotion_expressiveness=情绪外放程度；"
    "catchphrases=口头禅数组(最多3项，每项格式 口头禅——\"原文原话\")；"
    "particles=语气词及句尾频率；punctuation=标点习惯(句长/省略号/感叹号)；"
    "register=敬语/脏话/网络用语习惯；metaphor=比喻方式；"
    "sentence_length=句长偏好；opening=典型开头；ending=典型收尾；"
    "avoid_words=不会用的词数组(最多5项)；"
    "emotion_samples=对象，键为兴奋/开心/生气/尴尬/回避/敷衍/安慰人，值为原话；"
    "refusal=拒绝时的原话；diversion=转移话题的原话；trigger_reply=被问雷点时的原话；"
    "topics_like=爱聊的话题；topics_dislike=不爱聊的话题；no_answer=被问不想答时的原话；"
    "scene=当前场景/身份；scene_relation=场景中与用户的关系；"
    "proactive_quotes=会主动说的话数组(最多5项)；not_proactive=不会主动说的话题；"
    "proactive_openers=主动开口样例数组(最多2项)；"
    "events=重要经历数组(最多4项，每项格式 事件→影响)；"
    "actions=紧张/心虚时的小动作；habit_actions=习惯动作；"
    "banned=禁止项数组(最多6项)。"
    "【硬规则】"
    "1. 只提取人物本身；场景/画面/动作/身体描写不得进入任何字段(actions 的小动作除外)。"
    "2. 成人向文本只提取姓名、身份、互动模式；身体部位、动作细节、性暗示词汇一律不得出现。"
    "3. 凡是要求“原话”的字段(trigger/catchphrases/opening/ending/emotion_samples/refusal/diversion/"
    "trigger_reply/no_answer/proactive_quotes/proactive_openers)，只能逐字摘抄文本中人物实际说出的对白。"
    "文本没有对白、或没有对应内容，就留空，绝不编写、改写、续写。"
    "4. 不要为了填满而猜测；没有依据的字段留空字符串或空数组。宁可空着。"
    "5. 只输出 JSON，不要代码块，不要解释。"
    "【输出骨架】"
    '{"name":"","identity":"","relation":"","address_user":"","personality_core":"",'
    '"trigger":"","cares":"","emotion_expressiveness":"","catchphrases":[],"particles":"",'
    '"punctuation":"","register":"","metaphor":"","sentence_length":"","opening":"",'
    '"ending":"","avoid_words":[],"emotion_samples":{"兴奋":"","开心":"","生气":"","尴尬":"",'
    '"回避":"","敷衍":"","安慰人":""},"refusal":"","diversion":"","trigger_reply":"",'
    '"topics_like":"","topics_dislike":"","no_answer":"","scene":"","scene_relation":"",'
    '"proactive_quotes":[],"not_proactive":"","proactive_openers":[],"events":[],'
    '"actions":"","habit_actions":"","banned":[]}'
)

_SCALARS = ("name", "identity", "relation", "address_user", "personality_core",
            "trigger", "cares", "emotion_expressiveness", "particles", "punctuation",
            "register", "metaphor", "sentence_length", "opening", "ending", "refusal",
            "diversion", "trigger_reply", "topics_like", "topics_dislike", "no_answer",
            "scene", "scene_relation", "not_proactive", "actions", "habit_actions")
_LISTS = ("catchphrases", "avoid_words", "proactive_quotes", "proactive_openers",
          "events", "banned")


def _read_source(project: str) -> str:
    texts = []
    for p in sorted(config.initial_dir(project).glob("*")):
        if not p.is_file() or p.suffix.lower() not in (".txt", ".md"):
            continue
        if p.name == SUPPLEMENT_FILENAME:      # 用户补充原样附入，不交给模型改写
            continue
        try:
            texts.append(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(texts)[: config.ICF_EXTRACT_CHARS]


def _read_supplement(project: str) -> str:
    p = config.initial_dir(project) / SUPPLEMENT_FILENAME
    if not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def _segment(src: str, n: int) -> list:
    """源文本太短时整段处理，避免把一两个字符切碎后模型读不出信息。"""
    if len(src) < 400:
        return [src]
    seg_len = max(1, len(src) // n)
    return [src[i * seg_len:(i + 1) * seg_len] for i in range(n)
            if src[i * seg_len:(i + 1) * seg_len]]


def _clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _parse_object(raw: str):
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _render(data: dict, supplement: str = "") -> str:
    """始终输出完整模板：所有小节和字段都在，有内容则填，没内容留空。"""
    def v(key) -> str:
        return _clean(data.get(key))

    def items(key, limit) -> list:
        raw = data.get(key)
        if isinstance(raw, str):
            raw = [raw]
        return [_clean(x) for x in raw if _clean(x)][:limit] if isinstance(raw, list) else []

    name = v("name")
    lines = [f"# 人物设定：{name}" if name else "# 人物设定", ""]

    lines += [
        "## 一、身份",
        f"- 姓名：{name}",
        f"- 身份/职业：{v('identity')}",
        f"- 与用户关系：{v('relation')}",
        f"- 称呼用户：{v('address_user')}",
        "",
        "## 二、性格",
        f"- 核心性格：{v('personality_core')}",
        f"- 雷点：{v('trigger')}",
        f"- 在意的东西：{v('cares')}",
        f"- 情绪外放程度：{v('emotion_expressiveness')}",
        "",
        "## 三、说话方式",
        "### 3.1 语言指纹",
        "- 口头禅：",
    ]
    lines += [f"  - {x}" for x in items("catchphrases", 3)]
    lines += [
        f"- 语气词：{v('particles')}",
        f"- 标点：{v('punctuation')}",
        f"- 敬语/脏话/网络用语：{v('register')}",
        f"- 比喻方式：{v('metaphor')}",
        "",
        "### 3.2 句法",
        f"- 句长：{v('sentence_length')}",
        f"- 典型开头：{v('opening')}",
        f"- 典型收尾：{v('ending')}",
        "",
        "### 3.3 不会用的词",
    ]
    lines += [f"  - {x}" for x in items("avoid_words", 5)]
    lines += ["", "### 3.4 情绪原话样例"]
    emo = data.get("emotion_samples")
    if not isinstance(emo, dict):
        emo = {}
    lines += [f"  - {k}：{_clean(emo.get(k))}" for k in _EMOTIONS]
    lines += [
        "",
        "### 3.5 拒绝与回避",
        f"- 怎么说不：{v('refusal')}",
        f"- 转移话题原话：{v('diversion')}",
        f"- 被问雷点时的原话：{v('trigger_reply')}",
        "",
        "### 3.6 话题",
        f"- 爱聊：{v('topics_like')}",
        f"- 不爱聊：{v('topics_dislike')}",
        f"- 被问不想答的：{v('no_answer')}",
        "",
        "## 四、场景卡",
        f"- 场景/身份：{v('scene')}",
        f"- 与用户关系：{v('scene_relation')}",
        "- 会主动说的话：",
    ]
    lines += [f"  - {x}" for x in items("proactive_quotes", 5)]
    lines += [
        f"- 不会主动说：{v('not_proactive')}",
        "- 主动开口样例：",
    ]
    lines += [f"  - {x}" for x in items("proactive_openers", 2)]
    lines += ["", "## 五、示例对话"]
    if supplement:
        lines.append(supplement)
    lines += [
        "",
        "## 六、重要经历",
    ]
    lines += [f"- {x}" for x in items("events", 4)]
    lines += [
        "",
        "## 七、小动作",
        f"- 紧张/心虚时：{v('actions')}",
        f"- 习惯动作：{v('habit_actions')}",
        "",
        "## 八、禁止项",
    ]
    lines += [f"  - {x}" for x in items("banned", 6)]

    return "\n".join(lines).rstrip() + "\n"


def extract_initial_memories(project: str, progress=None) -> int:
    """生成人物设定模板，返回写入文件数（正常为 1）。源文件为空也照常生成空白模板。"""
    src = _read_source(project)
    supplement = _read_supplement(project)
    data = {"emotion_samples": {}}

    if src.strip():
        segs = _segment(src, config.ICF_SEGMENTS)
        for i, seg in enumerate(segs, 1):
            if progress:
                progress(f"提取人物特征 {i}/{len(segs)}...")
            try:
                raw = llm.chat_raw(_EXTRACT_SYSTEM, seg, num_ctx=6144)
            except Exception:
                continue
            obj = _parse_object(raw)
            if not obj:
                continue
            for k in _SCALARS:
                val = _clean(obj.get(k))
                if val and not data.get(k):
                    data[k] = val
            for k in _LISTS:
                vals = obj.get(k)
                if isinstance(vals, str):
                    vals = [vals]
                if not isinstance(vals, list):
                    continue
                cur = data.setdefault(k, [])
                for x in vals:
                    x = _clean(x)
                    if x and x not in cur:
                        cur.append(x)
            emo = obj.get("emotion_samples")
            if isinstance(emo, dict):
                for k in _EMOTIONS:
                    val = _clean(emo.get(k))
                    if val and not data["emotion_samples"].get(k):
                        data["emotion_samples"][k] = val
    elif progress:
        progress("源文件为空，生成空白人物模板。")

    d = config.profile_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    # 提取即整体更新：删掉旧提取条目（保留手工编写的 00- 规则条目）
    for old in d.glob("*.md"):
        if not old.name.startswith("00-"):
            old.unlink()
    (d / PROFILE_FILENAME).write_text(_render(data, supplement), encoding="utf-8")
    return 1


def create_project(name: str, progress=None) -> bool:
    """新建项目骨架 + 生成人物设定模板。name 已含日期后缀。"""
    if not name or name in config.projects():
        return False
    config.project_dir(name)          # 建目录骨架
    extract_initial_memories(name, progress)
    if progress:
        progress(f"项目 {name} 创建完成，已生成 {PROFILE_FILENAME}。")
    return True
