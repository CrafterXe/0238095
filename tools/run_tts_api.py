"""生成 J1 专用 tts_infer.yaml 并以前台进程方式运行 GPT-SoVITS api_v2。

不修改 GPT-SoVITS 目录内的任何已有文件：
- yaml 生成到 j1/generated/，权重用绝对路径，预训练模型用相对路径（cwd=SoVITS 根目录）。
- 权重组合（20261018 ASR 客观测评 sim=0.90）：
  GPT = 预训练 s1v3.ckpt（微调版 GPT 用乱码转写训练过，已废）
  SoVITS = 微调 sf_e8_s144.pth（sweetiefox 音色）
用法：runtime/python.exe tools/run_tts_api.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

YAML_TEMPLATE = """custom:
  bert_base_path: GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large
  cnhuhbert_base_path: GPT_SoVITS/pretrained_models/chinese-hubert-base
  device: cuda
  is_half: true
  t2s_weights_path: {gpt_weights}
  version: {version}
  vits_weights_path: {sovits_weights}
"""


def write_yaml() -> Path:
    gpt_w = config.GPT_WEIGHTS.resolve()
    vits_w = config.SOVITS_WEIGHTS.resolve()
    for p in (gpt_w, vits_w):
        if not p.exists():
            raise FileNotFoundError(f"权重不存在: {p}")
    config.TTS_YAML.write_text(
        YAML_TEMPLATE.format(gpt_weights=gpt_w.as_posix(),
                             sovits_weights=vits_w.as_posix(),
                             version=config.TTS_VERSION),
        encoding="utf-8")
    return config.TTS_YAML


def main():
    yaml_path = write_yaml()
    print(f"[J1-TTS] yaml: {yaml_path}")
    print(f"[J1-TTS] 启动 api_v2 于 {config.TTS_API_HOST}:{config.TTS_API_PORT} ...")
    cmd = [str(config.RUNTIME_PY), "api_v2.py",
           "-a", config.TTS_API_HOST, "-p", str(config.TTS_API_PORT),
           "-c", str(yaml_path)]
    subprocess.run(cmd, cwd=str(config.SOVITS_ROOT))


if __name__ == "__main__":
    main()
