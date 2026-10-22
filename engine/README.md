# 此目录由安装脚本自动填充

运行 `install.bat` 后，安装脚本会自动下载 GPT-SoVITS 推理引擎（约 8 GB）
并解压到本目录，形成：

```
engine/
└─ GPT-SoVITS-v2pro-20250604-nvidia50/
    ├─ runtime/python.exe      ← 嵌入式 Python（含全部依赖）
    ├─ GPT_SoVITS/             ← 推理代码 + 预训练模型
    └─ ...
```

无需手动下载或解压。引擎来源（官方集成包）：
https://huggingface.co/lj1995/GPT-SoVITS-windows-package
