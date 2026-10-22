"""记忆系统：动态记忆库（memory_bank.jsonl）+ 关键词检索。

注意：人设与初始记忆（initial memories/）是定死内容，由 core/persona.py
全量注入，不经过本模块检索。本模块只处理对话中动态学到的记忆。
零外部依赖：中文按 2/3-gram、英文数字按词切分打分，繁体折叠为简体，取 top-k。
写入时按归一化内容去重（借鉴 N.E.K.O FactStore：同文/子串不重复入库）。
"""
import json
import re
import time

import config

_STOP = set("的了吗呢吧啊呀哦嘛么呢我你他她它们这个那个是的就是不也都很和跟与及或者但是因为所以如果还又再就才只更最挺蛮挺么啥啥呀哇嗯哦哦哈啦咯喽呗啦欸嘿喂哈喽么怎么样怎样什么怎么") | {"j1"}

# 常用繁体→简体折叠（成对书写：每个繁体字后跟其简体，零依赖）
_TS_PAIRS = (
    "們们這这裡里說说時时對对過过來来後后東东車车馬马鳥鸟龍龙風风飛飞雲云電电"
    "學学國国会会開开關关门门問问間间見见聽听覺觉語语話话讀读書书寫写愛爱歡欢"
    "樂乐貓猫妳你個个無无沒没係系網网給给為为與与從从麼么課课業业親亲戰战鬥斗"
    "買买賣卖錢钱銀银記记憶忆體体點点樣样條条處处辦办動动應应該该認认識识議议"
    "訓训試试計计許许訪访誰谁謝谢講讲護护讓让變变響响驚惊憂忧慮虑願愿頭头顏颜"
    "額额項项順顺須须餘余館馆髮发麗丽舉举舊旧藝艺藥药補补裝装製制複复觀观觸触"
    "註注誠诚調调談谈請请論论質质賽赛贈赠輸输聯联職职膽胆臉脸興兴萬万葉叶號号"
    "衛卫詞词證证譯译豐丰賓宾資资賠赔賴赖趕赶軌轨軍军較较輛辆輪轮軟软輕轻載载"
    "轉转農农進进遠远適适選选還还邊边郵邮鄉乡醫医鍵键鎮镇鏡镜閒闲難难雙双雞鸡"
    "離离霧雾靜静頁页頂顶領领頻频顆颗題题類类顧顾飯饭飲饮養养廳厅歷历歸归當当"
    "發发監监盤盘確确礙碍禮礼穩稳種种積积筆笔節节範范簡简緊紧練练總总織织續续"
    "經经結结絕绝統统維维紅红約约級级紀纪純纯歲岁鐘钟兒儿幾几"
)
_T2S = str.maketrans(_TS_PAIRS[0::2], _TS_PAIRS[1::2])


def _tokenize(s: str) -> set:
    s = (s or "").lower().translate(_T2S)
    toks = set(re.findall(r"[a-z0-9]+", s))
    zh = re.sub(r"[^\u4e00-\u9fff]", " ", s)
    zh = re.sub(r"\s+", " ", zh).strip()
    for part in zh.split(" "):
        if len(part) == 1:
            toks.add(part)
        else:
            toks.update(part[i:i + 2] for i in range(len(part) - 1))
            toks.update(part[i:i + 3] for i in range(len(part) - 2))
    return toks - _STOP


def _score_tokens(toks: set) -> tuple:
    """拆成 2-gram 与 3-gram 两组，3-gram 命中权重更高（更具体）。"""
    tri = {t for t in toks if len(t) == 3}
    return toks - tri, tri


def _bank_entries(project=None):
    out = []
    f = config.memory_bank(project)
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            out.append({"src": "bank", "title": rec.get("ts", ""),
                        "tags": rec.get("tags", ""), "content": rec.get("content", "")})
        except json.JSONDecodeError:
            continue
    return out


def retrieve(query: str, k: int = 3, project=None) -> list:
    q = _tokenize(query)
    if not q:
        return []
    q2, q3 = _score_tokens(q)
    scored = []
    for e in _bank_entries(project):
        hay_tags = set(_tokenize(e["tags"]))
        hay = _tokenize(e["tags"] + " " + e["title"] + " " + e["content"])
        h2, h3 = _score_tokens(hay)
        hit2, hit3 = len(q2 & h2), len(q3 & h3)
        if hit2 + hit3 <= 0:
            continue
        score = hit2 + 2 * hit3 + (2 if (q & hay_tags) else 0)
        scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:k]]


def render_entries(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        head = e["title"] if e["src"] == "memories" else f"{e['title']}（对话记忆）"
        lines.append(f"- {head}：{e['content']}")
    return "\n".join(lines)


# ---------- 写入（仅动态记忆库，带去重） ----------

def _norm(s: str) -> str:
    """归一化：去空白/标点、转小写、繁→简，用于判重。"""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", (s or "").lower().translate(_T2S))


def _existing_norms(f) -> list:
    out = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(_norm(json.loads(line).get("content", "")))
            except json.JSONDecodeError:
                continue
    return out


def add_dynamic(entries: list, project=None) -> int:
    if not entries:
        return 0
    f = config.memory_bank(project)
    f.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_norms(f)
    added = 0
    with f.open("a", encoding="utf-8") as fh:
        for e in entries:
            rec = {"ts": time.strftime("%Y-%m-%d %H:%M"),
                   "tags": str(e.get("tags", "")).strip(),
                   "content": str(e.get("content", "")).strip()[:300]}
            n = _norm(rec["content"])
            if not n:
                continue
            # 与已有条目相同或互为子串 → 视为重复，跳过
            if any(n in x or x in n for x in existing):
                continue
            existing.append(n)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            added += 1
    return added


def add_user_note(text: str, context: str = "", project=None):
    """保存用户要求记住的内容；context 为从 chats 取出的相关对话（含 AI 回复）。"""
    content = text if not context else f"{text}\n（相关对话上下文）{context}"
    return add_dynamic([{"tags": "用户要求记住", "content": content}], project)
