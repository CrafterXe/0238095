"""GPT-SoVITS api_v2 语音合成客户端。"""
import re
import time
from pathlib import Path

import requests

import config

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F]"
)


def clean_for_tts(text: str) -> str:
    t = _EMOJI_RE.sub("", text)
    t = re.sub(r"[*#`>~_]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def check() -> bool:
    try:
        r = requests.get(f"{config.TTS_API}/docs", timeout=3)
        return r.ok
    except Exception:
        return False


def speak(text: str, project=None) -> Path:
    """合成整段文本，返回 wav 文件路径（存当前项目 audio/）。"""
    t = clean_for_tts(text)
    if not t:
        raise ValueError("清理后没有可朗读的文本")
    payload = {
        "text": t,
        "text_lang": "zh",
        "ref_audio_path": str(config.REF_AUDIO),
        "prompt_text": config.PROMPT_TEXT,
        "prompt_lang": config.PROMPT_LANG,
        "aux_ref_audio_paths": [str(p) for p in config.AUX_REF_AUDIOS],
        "top_k": 15,
        "top_p": 1.0,
        "temperature": 1.0,
        "text_split_method": "cut5",
        "batch_size": 1,
        "speed_factor": 1.0,
        "media_type": "wav",
        "streaming_mode": False,
        "parallel_infer": True,
        "repetition_penalty": 1.35,
    }
    r = requests.post(f"{config.TTS_API}/tts", json=payload, timeout=300)
    r.raise_for_status()
    out = config.audio_dir(project) / time.strftime("%Y%m%d_%H%M%S.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return out
