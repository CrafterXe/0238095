# -*- coding: utf-8 -*-
"""J1 本地AI陪伴 · 一键安装（便携版）

新设备首次使用：双击 install.bat（= 运行本脚本），自动完成：
  1. 下载并解压 GPT-SoVITS 推理引擎到包内 engine\\（约 8GB，官方集成包）
  2. 下载语音模型 voice_model\\（音色模型约 129MB，GitHub Release；
     GPT 底模 s1v3.ckpt 复用引擎自带文件，无需重复下载）
  3. 检查 / 安装 Ollama（本地大模型服务）
  4. 下载对话模型 R4C3R/qwen3-8b-heretic:q4_k_m（约 5GB）

之后双击 start.bat 即可使用。
"""
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ================== 可按需修改 ==================
# GPT-SoVITS 官方集成包（Windows / NVIDIA，v2pro-20250604）下载地址与解压后目录名。
# 直连 HuggingFace 官方 CDN（不使用镜像站），需能访问 huggingface.co（请开启 VPN）。
ENGINE_URLS = (
    "https://huggingface.co/lj1995/GPT-SoVITS-windows-package/resolve/main/GPT-SoVITS-v2pro-20250604-nvidia50.7z",
)
ENGINE_DIRNAME = "GPT-SoVITS-v2pro-20250604-nvidia50"
ENGINE_APPROX_GB = 8.2
# 对话模型（Ollama）
OLLAMA_MODEL = "R4C3R/qwen3-8b-heretic:q4_k_m"
# 语音模型（你的音色 + GPT 预训练底模）：从 GitHub Release 直连下载。
# 需能访问 github.com（请开启 VPN）；网络中断时脚本会自动断点续传重试。
# 注：引擎集成包里自带同名 s1v3.ckpt，已实测与 Release 文件 SHA256 完全一致，
#     若解压后已存在就直接复用，省掉这次下载（只剩 sf_e8_s144.pth 要下）。
VOICE_FILES = {
    # 文件名: (Release 直链, 约略大小MB)
    "s1v3.ckpt": (
        "https://github.com/CrafterXe/model-files/releases/download/v1/s1v3.ckpt", 148),
    "sf_e8_s144.pth": (
        "https://github.com/CrafterXe/model-files/releases/download/v1/sf_e8_s144.pth", 129),
}
# ==============================================

IS_WIN = os.name == "nt"
ENGINE_DIR = ROOT / "engine"
ENGINE_TARGET = ENGINE_DIR / ENGINE_DIRNAME
RUNTIME_PY = ENGINE_TARGET / "runtime" / "python.exe"
# 7zr 是随包携带的迷你解压器（仅解 .7z），无需用户装 7-Zip
SEVENZR = ROOT / "tools" / "7zr.exe"


def log(msg=""):
    print(msg, flush=True)


def run(cmd, **kw):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", **kw)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return False, "命令不存在: " + (cmd[0] if isinstance(cmd, list) else str(cmd))
    except Exception as e:
        return False, str(e)


def which(name):
    return shutil.which(name) is not None


def _curl_download(urls, dest: Path, approx_mb: float = 0, passes: int = 3) -> bool:
    """用 curl.exe 从 GitHub 直连下载（跟随重定向，断点续传 -C -）。
    连接中途被重置时，同一源会继续从断点续传（最多 passes 轮）；
    下载完成后校验体积，明显偏小视为失败并换源。"""
    if isinstance(urls, str):
        urls = (urls,)
    approx_bytes = approx_mb * 1024 ** 2
    min_bytes = int(approx_bytes * 0.85)
    if dest.exists() and (approx_bytes <= 0 or dest.stat().st_size >= min_bytes):
        log(f"  [跳过] 已存在：{dest.name}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    curl = shutil.which("curl") or "curl.exe"
    tmp = dest.with_suffix(dest.suffix + ".part")
    size_txt = f"{approx_mb / 1024:.1f}GB" if approx_mb >= 1024 else f"{approx_mb:.0f}MB"
    for url in urls:
        log(f"  正在下载 {dest.name}（约 {size_txt}）...")
        log(f"  源：{url.split('/')[2]}")
        for attempt in range(1, passes + 1):
            before = tmp.stat().st_size if tmp.exists() else 0
            code = subprocess.call([
                curl, "-L", "-C", "-", "--retry", "4", "--retry-delay", "5",
                "--connect-timeout", "20", "-A", "Mozilla/5.0", "-o", str(tmp), url,
            ])
            got = tmp.stat().st_size if tmp.exists() else 0
            # 33 = 服务器返回 416，说明 .part 已完整
            if code in (0, 33) and got > 0:
                if approx_bytes > 0 and got < min_bytes:
                    log(f"  [失败] 文件不完整（{got / 1024 ** 2:.0f}MB < 约 {approx_mb:.0f}MB），换源...")
                    tmp.unlink(missing_ok=True)
                    break
                tmp.rename(dest)
                log(f"  [OK] {dest.name}（{got / 1024 ** 2:.0f}MB）")
                return True
            if got > before:
                log(f"  [中断] 已下载 {got / 1024 ** 2:.0f}MB（curl 退出码 {code}）")
                if attempt < passes:
                    log(f"  从断点续传（第 {attempt}/{passes - 1} 次）...")
                    continue
            else:
                log(f"  [失败] 本轮无进展（curl 退出码 {code}），换下一个源...")
                break
    log(f"  [失败] 未能下载 {dest.name}")
    log(f"         请确认已开启 VPN / 能访问 github.com，然后重新运行本脚本")
    log(f"         （会从已下载的部分继续）。也可手动下载后放到：{dest}")
    for url in urls:
        log(f"           {url}")
    return False


# ---------- 1. 引擎下载 + 解压 ----------

def ensure_engine() -> bool:
    if RUNTIME_PY.exists():
        log(f"  [OK] 引擎就绪：{ENGINE_TARGET.name}")
        return True
    log(f"  未找到 GPT-SoVITS 引擎，准备自动下载并解压（约 {ENGINE_APPROX_GB}GB）...")
    log("  提示：下载源会跳转到 HuggingFace 官方 CDN，需可访问（如已开启 VPN）。")
    pkg = ENGINE_DIR / (ENGINE_DIRNAME + ".7z")
    if not _curl_download(ENGINE_URLS, pkg, ENGINE_APPROX_GB * 1024):
        return False
    if not SEVENZR.exists():
        log(f"  [失败] 缺少解压器 {SEVENZR}（应随包携带）")
        log(f"         请手动用 7-Zip 把 {pkg} 解压到 {ENGINE_DIR}\\")
        return False
    log("  正在解压（约几分钟，请耐心等待）...")
    ok, out = run([str(SEVENZR), "x", str(pkg), f"-o{ENGINE_DIR}", "-y"])
    if not ok:
        log(f"  [失败] 解压出错：{out[-300:]}")
        return False
    pkg.unlink(missing_ok=True)   # 解压成功后删除安装包省空间
    if RUNTIME_PY.exists():
        log(f"  [OK] 引擎解压完成：{ENGINE_TARGET.name}")
        return True
    log(f"  [失败] 解压后未找到 {RUNTIME_PY.name}，请检查 {ENGINE_DIR}\\ 目录结构")
    return False


# ---------- 2. 语音模型下载（从 GitHub Release） ----------

def ensure_voice() -> bool:
    vdir = ROOT / "voice_model"
    vdir.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, (url, mb) in VOICE_FILES.items():
        dest = vdir / name
        # 引擎包自带的同名文件（实测 SHA256 与 Release 一致）直接复用，不再下载
        bundled = ENGINE_TARGET / "GPT_SoVITS" / "pretrained_models" / name
        if (not dest.exists() and bundled.exists()
                and bundled.stat().st_size >= mb * 1024 ** 2 * 0.85):
            shutil.copy2(bundled, dest)
            log(f"  [OK] {name} 复用引擎自带文件（与 Release 一致，跳过下载）")
            continue
        if not _curl_download(url, dest, mb):
            ok = False
    if ok:
        log("  [OK] 语音模型就绪（s1v3.ckpt + sf_e8_s144.pth）")
    return ok


# ---------- 3/4. Ollama 与对话模型 ----------

def ensure_ollama():
    if which("ollama"):
        ok, out = run(["ollama", "--version"])
        log(f"  [OK] 已安装 Ollama（{out.strip().splitlines()[0] if out.strip() else '版本未知'}）")
        return True
    log("  未检测到 Ollama，尝试自动安装...")
    if IS_WIN and which("winget"):
        log("  使用 winget 安装（可能弹出授权窗口，请允许）...")
        ok, out = run(["winget", "install", "-e", "--id", "Ollama.Ollama",
                       "--accept-source-agreements", "--accept-package-agreements"])
        if ok or "Successfully installed" in out or "已安装" in out:
            log("  [OK] Ollama 安装完成")
            log("  [重要] 请【关闭本窗口，重新双击 安装.bat】让 PATH 生效后继续。")
            return "restart"
    log("  [提示] 无法自动安装，请手动安装 Ollama：")
    log("         https://ollama.com/download/windows")
    return False


def ensure_ollama_running() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
        return True
    except Exception:
        pass
    log("  正在启动 Ollama 服务以下载模型...")
    try:
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=(subprocess.CREATE_NO_WINDOW if IS_WIN else 0))
    except Exception:
        return False
    import time
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def ensure_chat_model() -> bool:
    if not ensure_ollama_running():
        log("  [失败] Ollama 服务未启动，无法下载模型。")
        log(f"         请手动运行 ollama serve 后再执行 ollama pull {OLLAMA_MODEL}")
        return False
    ok, out = run(["ollama", "list"])
    if ok and OLLAMA_MODEL in out:
        log(f"  [跳过] 对话模型已存在：{OLLAMA_MODEL}")
        return True
    log(f"  正在下载对话模型（约 5GB，视网速需几分钟到更久）...")
    try:
        if subprocess.call(["ollama", "pull", OLLAMA_MODEL]) == 0:
            log(f"  [OK] 对话模型就绪：{OLLAMA_MODEL}")
            return True
    except Exception as e:
        log(f"  [失败] 下载出错：{e}")
    log(f"  [失败] 可稍后手动执行 ollama pull {OLLAMA_MODEL}")
    return False


def main():
    log("=" * 58)
    log("   J1 本地AI陪伴 · 一键安装（便携版）")
    log("=" * 58)
    log("  需要联网：引擎约 8GB + 对话模型约 5GB + 语音模型约 0.1GB。")
    log()
    ok = True

    log("[1/4] GPT-SoVITS 引擎 ...")
    if not ensure_engine():
        ok = False
    log()

    log("[2/4] 语音模型（GitHub Release，需能访问 github.com）...")
    if not ensure_voice():
        ok = False
    log()

    log("[3/4] Ollama 服务 ...")
    r = ensure_ollama()
    if r == "restart":
        log()
        log("=" * 58)
        log("  Ollama 刚装好，请【重新双击 安装.bat】继续。")
        log("=" * 58)
        return 0
    if not r:
        ok = False
    log()

    log("[4/4] 对话模型 ...")
    if not ensure_chat_model():
        ok = False
    log()

    log("=" * 58)
    log("   安装完成！" if ok else "   部分完成，补齐上面 [缺失]/[失败] 项即可。")
    log("=" * 58)
    log("  启动：双击 启动.bat，浏览器打开 http://127.0.0.1:14001/")
    log("  首次启动 TTS 需约 1 分钟加载语音模型，请耐心等待。")
    log()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已取消安装。")
        sys.exit(130)
