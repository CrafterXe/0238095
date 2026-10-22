"""本地对话记录：每项目每天一个 jsonl 文件。"""
import json
import time
from pathlib import Path

import config


def _today_file(project=None) -> Path:
    return config.chat_dir(project) / (time.strftime("%Y%m%d") + ".jsonl")


def add_turn(user: str, reply: str, project=None) -> None:
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "user": user, "j1": reply}
    f = _today_file(project)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def count_today(project=None) -> int:
    f = _today_file(project)
    if not f.exists():
        return 0
    return sum(1 for line in f.read_text(encoding="utf-8").splitlines()
               if line.strip())


def recent_messages(turns: int = None, project=None) -> list:
    turns = turns or config.HISTORY_TURNS
    f = _today_file(project)
    if not f.exists():
        return []
    lines = f.read_text(encoding="utf-8").strip().splitlines()
    msgs = []
    for line in lines[-turns:]:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("user"):
            msgs.append({"role": "user", "content": rec["user"]})
        msgs.append({"role": "assistant", "content": rec["j1"]})
    return msgs
