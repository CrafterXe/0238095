"""Ollama 本地 LLM 对话。"""
import re

import requests

import config


def _strip_think(text: str) -> str:
    """去掉 qwen3 可能的思考块。"""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def check() -> bool:
    try:
        r = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=3)
        return r.ok
    except Exception:
        return False


def _user_msg(text: str) -> str:
    """heretic 模型默认开思考模式；在用户消息末尾追加 /no_think 关闭。"""
    return text + config.LLM_NO_THINK_SUFFIX


def chat_raw(system: str, user_text: str, temperature: float = 0.3,
             num_ctx: int = 4096) -> str:
    """不做括号清洗的原始调用（用于记忆提取等结构化任务）。"""
    payload = {
        "model": config.LLM_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": _user_msg(user_text)}],
        "stream": False,
        "think": False,
        "keep_alive": -1,
        "options": {"num_ctx": num_ctx, "temperature": temperature},
    }
    r = requests.post(f"{config.OLLAMA_HOST}/api/chat", json=payload,
                      timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    return _strip_think(r.json().get("message", {}).get("content", ""))


def chat(system: str, history: list, message: str) -> str:
    """history: [{"role": "user"/"assistant", "content": ...}, ...]（最近若干轮）"""
    msgs = [{"role": "system", "content": system}] + history + [
        {"role": "user", "content": _user_msg(message)}
    ]
    payload = {
        "model": config.LLM_MODEL,
        "messages": msgs,
        "stream": False,
        "think": False,
        "keep_alive": -1,
        "options": {
            "num_ctx": config.LLM_NUM_CTX,
            "temperature": config.LLM_TEMPERATURE,
            "top_p": config.LLM_TOP_P,
            "repeat_penalty": 1.1,          # 抑制复读，活人感
            "presence_penalty": config.LLM_PRESENCE_PENALTY,
        },
    }
    r = requests.post(f"{config.OLLAMA_HOST}/api/chat", json=payload,
                      timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    reply = _strip_think(r.json().get("message", {}).get("content", ""))
    # 防御：去掉模型可能输出的括号动作描写（念出来很奇怪）
    reply = re.sub(r"[（(【\[][^（()）【\]\n]*[)）】\]]", "", reply).strip()
    return reply
