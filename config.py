"""J1 全局配置。多项目人物架构：projects/<名字_日期>/ 为独立人物单元。

项目内目录命名（用户钦定）：
  memory settings/initial memories/  人设+初始记忆（定死，全量注入，仅"提取人物特征"时修改）
  memory settings/memory_bank.jsonl  对话动态记忆（检索注入）
  chats/  对话记录    audios of the conversation/  语音    initial files/  设定源文件
"""
from pathlib import Path

# j1 项目根目录（本文件所在目录）
ROOT = Path(__file__).resolve().parent

# ---- GPT-SoVITS 推理引擎（内嵌于包内 engine/，由 install 脚本自动下载解压） ----
# 自定位结构：engine/GPT-SoVITS-v2pro-20250604-nvidia50/ 与本目录同级。
# 兼容旧的外部布局（本目录旁 GPT-SoVITS/...）以便开发期平滑过渡。
def _find_sovits_root() -> Path:
    cands = [
        ROOT / "engine" / "GPT-SoVITS-v2pro-20250604-nvidia50",                      # 便携包内嵌（目标）
        ROOT.parent / "GPT-SoVITS" / "GPT-SoVITS_v1_sweetiefox" / "GPT-SoVITS-v2pro-20250604-nvidia50",  # 旧外部布局
        ROOT.parent / "GPT-SoVITS" / "GPT-SoVITS-v2pro-20250604-nvidia50",
    ]
    for c in cands:
        if (c / "runtime" / "python.exe").exists():
            return c
    return cands[0]   # 未安装时返回内嵌目标路径，install/start 据此给出统一报错

SOVITS_ROOT = _find_sovits_root()
RUNTIME_PY = SOVITS_ROOT / "runtime" / "python.exe"   # 嵌入式 Python 3.9（含 torch/gradio）
TTS_API_HOST = "127.0.0.1"
TTS_API_PORT = 9880
TTS_API = f"http://{TTS_API_HOST}:{TTS_API_PORT}"

# ---- 语音模型文件（voice_model/ 仅存两个权重，由 install 从 GitHub Release 下载） ----
#   GPT（文本->读音）用【预训练 s1v3.ckpt】——微调版 GPT 是用中文乱码转写训练的，已废；
#   SoVITS（音色）用微调 sf_e8_s144.pth——保留 sweetiefox 音色。
# 推理所需的 BERT/HuBERT/语言检测等头模型在引擎自带 GPT_SoVITS/pretrained_models/，
# 通过相对路径加载（见 tools/run_tts_api.py），与 voice_model/ 解耦。
VOICE_MODEL_DIR = ROOT / "voice_model"
GPT_WEIGHTS = VOICE_MODEL_DIR / "s1v3.ckpt"
SOVITS_WEIGHTS = VOICE_MODEL_DIR / "sf_e8_s144.pth"
TTS_VERSION = "v2Pro"
TTS_YAML = ROOT / "generated" / "j1_tts_infer.yaml"

# 参考音频与参考文本【必须真实对应】（whisper 英文转写，见 20261018 诊断）。
ASSETS = ROOT / "assets"
REF_AUDIO = ASSETS / "ref_aux2.wav"
PROMPT_TEXT = "Good morning. My name is India, but you can just call me foxy."
PROMPT_LANG = "en"
AUX_REF_AUDIOS = []

# ---- Ollama LLM ----
OLLAMA_HOST = "http://127.0.0.1:11434"
LLM_MODEL = "R4C3R/qwen3-8b-heretic:q4_k_m"   # heretic 微调版，无审查、活人感更好
LLM_NO_THINK_SUFFIX = " /no_think"               # 该模型默认开思考模式，追加此标记关闭
LLM_NUM_CTX = 4096
LLM_TEMPERATURE = 0.6   # 0.8 在短人设下易收敛到模板；0.6 更稳且仍有变化
LLM_TOP_P = 0.9
LLM_PRESENCE_PENALTY = 0.6   # 惩罚已出现过的概念，压制复读口癖/反问
LLM_TIMEOUT = 180
HISTORY_TURNS = 10

# ---- 多项目人物管理 ----
PROJECTS_DIR = ROOT / "projects"
ACTIVE_FILE = PROJECTS_DIR / "active.txt"   # 当前激活的人物项目名

def projects() -> list:
    """所有可用人物项目目录名。"""
    if not PROJECTS_DIR.exists():
        return []
    return sorted([d.name for d in PROJECTS_DIR.iterdir() if d.is_dir()])

def active_project() -> str:
    """当前激活项目；默认取第一个。"""
    names = projects()
    if not names:
        return ""
    try:
        saved = ACTIVE_FILE.read_text(encoding="utf-8").strip()
        if saved in names:
            return saved
    except OSError:
        pass
    return names[0]

def set_active_project(name: str) -> bool:
    if name in projects():
        ACTIVE_FILE.write_text(name, encoding="utf-8")
        return True
    return False

def project_dir(name: str = None) -> Path:
    """项目目录：projects/<name>/。"""
    name = name or active_project()
    d = PROJECTS_DIR / name
    for sub in ("memory settings", "memory settings/initial memories",
                "chats", "audios of the conversation", "initial files"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d

def profile_dir(name: str = None) -> Path:
    """人设+初始记忆（定死内容，全量注入；仅提取人物特征时修改）。"""
    return project_dir(name) / "memory settings" / "initial memories"

def memory_bank(name: str = None) -> Path:
    """对话动态记忆（检索注入）。"""
    return project_dir(name) / "memory settings" / "memory_bank.jsonl"

def initial_dir(name: str = None) -> Path:
    """项目的人物设定源文件夹（仅新建项目时提取一次）。"""
    return project_dir(name) / "initial files"

def chat_dir(name: str = None) -> Path:
    return project_dir(name) / "chats"

def audio_dir(name: str = None) -> Path:
    return project_dir(name) / "audios of the conversation"

# ---- 记忆提取参数 ----
MEMORY_EVERY_N_TURNS = 5

# ---- 主动搭话 ----
PROACTIVE_POLL_SEC = 30         # 轮询间隔（检查是否该主动开口）
PROACTIVE_IDLE_SEC = 600        # 用户沉默多久后主动开口
PROACTIVE_COOLDOWN_SEC = 1800   # 两次主动搭话最小间隔

# ---- 提取人物特征参数 ----
ICF_EXTRACT_CHARS = 12000     # 提取源文件开头字符数
ICF_SEGMENTS = 4              # 分段数（每段 ~3000 字，配合 num_ctx=6144 防截断）
ICF_MAX_ENTRIES = 12

# ---- 联网检索（Bing CN，免费无 key；失败自动降级） ----
SEARCH_ENABLED = True
SEARCH_TIMEOUT = 8

# ---- 实时环境信息 ----
WEATHER_CITY = "天津"
WEATHER_LAT, WEATHER_LON = 39.1285, 117.2010
WEATHER_TIMEOUT = 6

# ---- Gradio 面板 ----
APP_HOST = "127.0.0.1"
APP_PORT = 14001
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
