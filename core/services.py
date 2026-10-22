"""本地服务管理：检查/拉起 Ollama 与 GPT-SoVITS TTS API。"""
import socket
import subprocess
import time

import config

CREATE_NO_WINDOW = 0x08000000


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ollama_up() -> bool:
    return _port_open(11434)


def tts_up() -> bool:
    return _port_open(config.TTS_API_PORT)


def ensure_ollama(timeout: int = 30) -> bool:
    if ollama_up():
        return True
    subprocess.Popen(["ollama", "serve"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=CREATE_NO_WINDOW)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if ollama_up():
            return True
        time.sleep(1)
    return ollama_up()


def ensure_tts(timeout: int = 300) -> bool:
    """TTS 未运行时拉起 api_v2（加载权重较慢，给长超时）。"""
    if tts_up():
        return True
    log = open(config.LOG_DIR / "tts_api.log", "ab")
    subprocess.Popen([str(config.RUNTIME_PY),
                      str(config.ROOT / "tools" / "run_tts_api.py")],
                     stdout=log, stderr=subprocess.STDOUT,
                     cwd=str(config.SOVITS_ROOT),
                     creationflags=CREATE_NO_WINDOW)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if tts_up():
            return True
        time.sleep(2)
    return tts_up()


def status() -> str:
    return f"LLM(Ollama): {'在线' if ollama_up() else '离线'} | TTS(SoVITS): {'在线' if tts_up() else '离线'}"
