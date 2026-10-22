"""J1 聊天机器人 · Gradio 面板（多人物项目版）。

- projects/<名字_日期>/ 为独立人物单元：memory/（人设+记忆）、chats/、audio/、initial/（新建时提取一次的源文件）。
- 切换项目即切换性格、记忆、历史、语音存档。
- 新建项目：把设定源文件放进 projects/<新名>/initial/ 后点“提取人物特征”。
启动：runtime/python.exe app.py （或由 start.bat 拉起）
"""
import json
import queue
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gradio as gr

import config
from core import history, llm, memory, persona, projects, services, tts, webinfo, websearch

_EXTRACT_LOCK = threading.Lock()
_PROACTIVE_LOCK = threading.Lock()
_PROACTIVE_OUT = queue.Queue()   # 后台主动搭话线程 -> 轮询事件的完工结果
_SEARCH_RE = re.compile(r"\[\[SEARCH[:：]\s*(.+?)\]\]", re.S)
_state = {"project": config.active_project(), "persona": None,
          "last_activity": time.time(), "last_proactive": 0.0}


def current_project() -> str:
    return _state["project"]


def current_persona() -> str:
    if _state["persona"] is None:
        _state["persona"] = persona.load_profile(current_project())
    return _state["persona"]


def build_system(message: str) -> str:
    p = current_project()
    parts = [current_persona(), "[当前环境]\n" + webinfo.context_line()]
    rendered = memory.render_entries(memory.retrieve(message, k=3, project=p))
    if rendered:
        parts.append("[相关记忆（可自然引用，勿复述）]\n" + rendered)
    return "\n\n".join(parts)


def _ask_llm(system: str, message: str):
    p = current_project()
    msgs = history.recent_messages(project=p)
    reply = llm.chat(system, msgs, message)
    m = _SEARCH_RE.search(reply)
    if m:
        query = m.group(1).strip()[:50]
        results = websearch.search(query)
        extra = "[联网检索结果]\n" + (results or "（这次没查到，凭已知回答）")
        reply = llm.chat(system + "\n\n" + extra, msgs, message)
        reply = _SEARCH_RE.sub("", reply).strip()
    return reply


def extract_and_store():
    """定期记忆提取：只从【用户输入】提取，AI 回复不写入记忆。"""
    if not _EXTRACT_LOCK.acquire(blocking=False):
        return
    try:
        p = current_project()
        user_msgs = [m["content"] for m in history.recent_messages(12, project=p)
                     if m["role"] == "user"]
        if not user_msgs:
            return
        dialog = "\n".join(f"用户: {t}" for t in user_msgs)
        system = ("你是记忆提取器。从【用户说过的话】中提取值得长期记住的关键事实"
                  "（用户偏好、身份信息、重要约定、重要事件）。"
                  '只输出 JSON 数组：[{"tags":"逗号分隔关键词","content":"一句话"}]，'
                  "最多3条；没有值得记的就输出 []。不要输出其他任何内容。")
        raw = llm.chat_raw(system, dialog)
        start, end = raw.find("["), raw.rfind("]")
        if start < 0 or end <= start:
            return
        entries = json.loads(raw[start:end + 1])
        if isinstance(entries, list):
            memory.add_dynamic(entries, project=p)
    except Exception:
        pass
    finally:
        _EXTRACT_LOCK.release()


def _maybe_extract_async():
    p = current_project()
    n = history.count_today(project=p)
    if n > 0 and n % config.MEMORY_EVERY_N_TURNS == 0:
        threading.Thread(target=extract_and_store, daemon=True).start()


def respond(message, chat):
    message = (message or "").strip()
    if not message:
        yield chat, None, services.status(), ""
        return
    _state["last_activity"] = time.time()
    p = current_project()
    if message.startswith("记住"):
        note = message[2:].strip()
        if note:
            # 用户要求记住的内容若与 AI 说过的话有关，附带 chats 里的近期上下文一起存
            ctx = "\n".join(f"{m['role']}: {m['content']}"
                            for m in history.recent_messages(2, project=p))
            memory.add_user_note(note, context=ctx, project=p)
    yield chat, None, "J1 思考中...", ""
    try:
        services.ensure_ollama()
        reply = _ask_llm(build_system(message), message)
    except Exception as e:
        yield chat, None, f"LLM 出错：{e}", ""
        return
    if not reply:
        yield chat, None, "LLM 返回了空内容，请换个说法试试。", ""
        return
    yield chat, None, "语音合成中...", ""
    try:
        services.ensure_tts()
        wav = str(tts.speak(reply, project=p))
    except Exception as e:
        chat = chat + [[message, reply]]
        history.add_turn(message, reply, project=p)
        yield chat, None, f"TTS 出错（文字正常）：{e} | " + services.status(), ""
        _maybe_extract_async()
        return
    chat = chat + [[message, reply]]
    history.add_turn(message, reply, project=p)
    yield chat, wav, services.status(), ""
    _maybe_extract_async()


def _proactive_reply() -> str:
    """用户沉默后，以人设主动开一句话。"""
    p = current_project()
    idle_min = max(1, int((time.time() - _state["last_activity"]) / 60))
    msgs = history.recent_messages(6, project=p)
    system = (current_persona() + "\n\n[当前环境]\n" + webinfo.context_line()
              + f"\n\n[主动搭话]\n用户已经约{idle_min}分钟没有说话了。"
                "请以人设身份主动开口说一句话：结合你的生活、当前时间，"
                "或自然衔接最近聊过的话题。要简短，不要问“在吗”，"
                "不要重复最近说过的话，不要以反问收尾。只输出要说的话。")
    try:
        return llm.chat(system, msgs, "[系统]请主动开口。")
    except Exception:
        return ""


def _proactive_worker():
    """后台线程：主动搭话的慢活（LLM+TTS）不占用面板事件队列。"""
    try:
        reply = _proactive_reply()
        if reply:
            p = current_project()
            wav = None
            try:
                services.ensure_tts()
                wav = str(tts.speak(reply, project=p))
            except Exception:
                pass
            history.add_turn("", reply, project=p)
            _PROACTIVE_OUT.put((reply, wav))
    except Exception:
        pass
    finally:
        _PROACTIVE_LOCK.release()


def poll_proactive(chat):
    """Gradio 定时轮询：只做触发判断和结果收取（毫秒级返回），慢活在后台线程。"""
    now = time.time()
    idle = now - _state["last_activity"]
    if (idle >= config.PROACTIVE_IDLE_SEC
            and now - _state["last_proactive"] >= config.PROACTIVE_COOLDOWN_SEC
            and _PROACTIVE_LOCK.acquire(blocking=False)):
        _state["last_proactive"] = now   # 触发即记冷却，防止重复派工
        threading.Thread(target=_proactive_worker, daemon=True).start()
    # 收取已完成的结果（可能不止一条）
    new_chat, wav_out, posted = chat, gr.update(), False
    try:
        while True:
            reply, wav = _PROACTIVE_OUT.get_nowait()
            new_chat = new_chat + [["（她主动开口）", reply]]
            if wav:
                wav_out = wav
            posted = True
    except queue.Empty:
        pass
    if posted:
        return new_chat, wav_out, services.status()
    return gr.update(), gr.update(), gr.update()


def switch_project(name):
    """切换人物项目。"""
    if not config.set_active_project(name):
        return [], None, f"项目不存在：{name}", gr.update()
    _state["project"] = name
    _state["persona"] = None
    _state["last_activity"] = time.time()
    _state["last_proactive"] = 0.0
    proj = config.project_dir(name)
    return ([], None,
            f"已切换到「{name}」。人设/记忆/历史已隔离。",
            gr.update(value=str(proj)))


def new_project(name):
    """新建项目骨架（名字自动追加日期后缀）。"""
    name = (name or "").strip()
    if not name:
        return gr.update(), "项目名不能为空。"
    full = f"{name}_{__import__('time').strftime('%Y%m%d')}"
    if full in config.projects():
        return gr.update(choices=config.projects(), value=full), f"项目已存在：{full}"
    config.project_dir(full)
    config.set_active_project(full)
    _state["project"] = full
    _state["persona"] = None
    _state["last_activity"] = time.time()
    return (gr.update(choices=config.projects(), value=full),
            f"已创建并切换到「{full}」。把设定源文件放入 {config.initial_dir(full)} 后点“提取人物特征”；"
            f"示例对话/正反例可另写进同目录的 {projects.SUPPLEMENT_FILENAME}，提取时会原样附入。")


def refresh_projects():
    """页面加载时重读 projects/ 目录：外部新建/改名/删除文件夹后，刷新页面即可同步。"""
    names = config.projects()
    cur = current_project()
    if cur not in names:
        # 当前项目已不存在（被外部改名/删除）：回退到已保存激活项或第一个可用项目
        cur = config.active_project()
        _state["project"] = cur
        _state["persona"] = None
    proj = config.project_dir(cur) if cur else config.PROJECTS_DIR
    return (gr.update(choices=names, value=cur or None),
            str(proj), services.status())


def extract_features():
    """生成人物设定模板（源文件为空也会生成空白模板）。"""
    p = current_project()
    projects.extract_initial_memories(p, progress=print)
    _state["persona"] = None
    return (f"提取完成：已生成 {projects.PROFILE_FILENAME}，空白处可手动补全。"
            f"（{config.profile_dir(p)}）")


def build_demo():
    with gr.Blocks(title="J1", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# J1\n多人物本地聊天 · 切换项目即切换性格/记忆/历史。")
        with gr.Row():
            proj_dd = gr.Dropdown(label="当前人物项目",
                                  choices=config.projects(),
                                  value=current_project(), scale=2,
                                  interactive=True)
            new_name = gr.Textbox(label="新建项目名", scale=2)
            new_btn = gr.Button("新建项目", scale=1)
            extract_btn = gr.Button("提取人物特征", scale=1)
        proj_info = gr.Textbox(label="项目目录", value=str(config.project_dir(current_project())),
                               interactive=False)
        status_box = gr.Textbox(label="状态", value=services.status(), interactive=False)
        chatbot = gr.Chatbot(label="对话", height=440)
        audio = gr.Audio(label="语音", autoplay=True, interactive=False)
        with gr.Row():
            msg = gr.Textbox(label="输入", scale=5)
            send = gr.Button("发送", variant="primary", scale=1)

        proj_dd.change(switch_project, [proj_dd],
                       [chatbot, audio, status_box, proj_info])
        new_btn.click(new_project, [new_name], [proj_dd, status_box])
        extract_btn.click(extract_features, outputs=[status_box])
        msg.submit(respond, [msg, chatbot], [chatbot, audio, status_box, msg])
        send.click(respond, [msg, chatbot], [chatbot, audio, status_box, msg])
        # 页面加载/刷新时同步项目列表、目录与服务状态（重读 projects/ 目录）
        demo.load(refresh_projects, None, [proj_dd, proj_info, status_box],
                  show_progress="hidden")
        # 主动搭话：轮询只做触发判断和结果收取（毫秒级），慢活在后台线程不阻塞聊天
        demo.load(poll_proactive, [chatbot], [chatbot, audio, status_box],
                  every=config.PROACTIVE_POLL_SEC, show_progress="hidden")
    return demo


if __name__ == "__main__":
    threading.Thread(target=services.ensure_ollama, daemon=True).start()
    threading.Thread(target=services.ensure_tts, daemon=True).start()
    demo = build_demo()
    demo.launch(inbrowser=True, server_name=config.APP_HOST,
                server_port=config.APP_PORT, show_error=True)
