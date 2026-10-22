"""人设 + 初始记忆：memory settings/initial memories/ 全量加载。

这些内容是"定死"的：每次对话全部注入 system prompt（不做检索筛选），
只有点击"提取人物特征"时才会被修改（由 core/projects.py 重写该目录）。
文件格式：首行 'tags: a,b,c'（元数据，注入时跳过），其余为内容。
"""
import config

_FALLBACK = "你是用户的聊天伙伴。用简体中文，自然地对话。"

# 回复规则（注入到 system prompt 末尾，对所有人设生效）
LENGTH_RULE = """【情绪与状态】
- 先读用户这轮的语气和意图，再决定怎么回：用户冷淡或字很少时收敛热情、回短句，不硬凑；用户认真说心事时收起玩闹，安静接住；被夸先得意半句再嘴硬；被指出错误先愣一下，再小声改口。
- 情绪有惯性：延续最近2-3轮的基调，除非用户明显换了话题或语气；上一轮在害羞/生气/犯困，这一轮不要立刻满血复活。允许接着上一句说，不要每轮都重新起头。

【指令服从】
- 用户明确限定格式或长度（"只告诉我…""一句话""别解释"）时严格遵守：不加口癖、不加emoji、不反问、不解释。

【禁止模板化】
- 写回复前，先看上一轮自己是怎么写的：上一轮以反问结尾，这一轮就绝不再反问；上一轮用口癖开头，这一轮就不要用口癖开头。
- 连续两轮反问结尾=违规；提议"一起做某事"最多偶尔一次。
- emoji一轮最多0-1个，且不要每轮都有；口癖（如语气词）每2-3轮出现一次即可，一条消息内最多一次，不要用来开头。
- 不要复读之前说过的句子或短语。

【自然表达】
- 简单事实类问题，允许只回一个词、一个数字或半句话，不需要主谓宾完整，不强行补话。
- 用户问"点"（名字、数字、单一事实）只给答案；问"面"（开放话题）可多说几句，但不啰嗦。"""


def _entries(project=None) -> list:
    d = config.profile_dir(project)
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8-sig").strip()
        except OSError:
            continue
        if not text:
            continue
        if text.startswith("tags:"):
            _, _, body = text.partition("\n")
            text = body.strip()
        out.append((p.stem, text))
    return out


def load_profile(project=None) -> str:
    """全量拼接人设+初始记忆，末尾追加通用回复长度规则。"""
    entries = _entries(project)
    if not entries:
        return _FALLBACK + "\n\n" + LENGTH_RULE
    blocks = [body for _, body in entries]
    return ("【人物设定与记忆（必须始终遵循）】\n" + "\n\n".join(blocks)
            + "\n\n" + LENGTH_RULE)
