# Voice2txt

本项目是一个 macOS Apple Silicon 本地音频转录桌面应用，技术栈为 `PySide6 + mlx-whisper`。

## 功能

1. 导入本地音频（`wav/mp3/m4a/flac`）并转录英文文本。
2. 本地录音，停止后自动触发转录。
3. 音频预处理（如 `mp3 -> wav 16k mono`）与转录均在后台线程执行，界面不会因转换卡死。
4. 录音监控支持实时显示录音时长和输入电平（RMS/Peak 映射百分比）。
5. 开始录音前自动检查当前输入设备可用性，不可用时提示修复方向。
6. GUI 右侧显示可复制文本。
7. 采用卡片化浅色界面，区分工作区、麦克风、操作区、录音监控和转写结果区。
8. 文本默认只在内存中展示，不自动落盘。
9. 点击 `Save as TXT` 后才写入 txt 文件（每次弹出 Save As）。
10. 固定使用单一高精度模型：`mlx-community/whisper-large-v3-fp16`。
11. 可查看并选择当前录音麦克风设备（支持“系统默认”）。
12. 支持一键清理没有对应 TXT 的 WAV 缓存文件（例如历史录音或转换残留）。

## 环境要求

1. Apple Silicon Mac（`arm64`）。
2. Python 3.11（建议 conda 项目内环境）。
3. 已安装 `ffmpeg`、`portaudio`、`libsndfile`。

## 安装步骤

```bash
cd /Users/smilechen/Documents/Codex_vibe_coding/voice2txt

conda create -p ./.conda python=3.11 -y
conda activate /Users/smilechen/Documents/Codex_vibe_coding/voice2txt/.conda

conda install -c conda-forge portaudio libsndfile ffmpeg -y

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 运行

```bash
cd /Users/smilechen/Documents/Codex_vibe_coding/voice2txt
python main.py
```

## 首次启动行为

1. 若 `state/app_config.json` 不存在或无效，应用会强制要求选择工作区目录。
2. 录音 wav 文件始终保存到工作区。
3. 转录文本仅在用户点击保存后写入磁盘。

## 缓存与临时文件策略

应用在转录前会将缓存环境变量重定向到工作区：

1. `MLX_HOME=<workspace>/.model_cache/mlx`
2. `HF_HOME=<workspace>/.model_cache/hf`
3. `HUGGINGFACE_HUB_CACHE=<workspace>/.model_cache/hf/hub`
4. `TMPDIR=<workspace>/.tmp`

模型路径缓存按工作区隔离，切换工作区后不会复用旧工作区的模型路径记录。

## 常见问题

1. 麦克风无法录音：请在 macOS 系统设置中给 Python/终端授予麦克风权限。
2. 导入失败提示 ffmpeg：确认 `ffmpeg` 已安装且在 PATH 中。
3. 首次转录较慢：模型首次下载和初始化耗时较高，后续会更快。
4. 固定使用高精度模型，首次下载体积较大，请耐心等待。
5. 若录音监控电平始终为 `0%`：请确认输入设备不是静音源，或尝试切换到其他麦克风。

## 测试

```bash
cd /Users/smilechen/Documents/Codex_vibe_coding/voice2txt
python -m pytest
```
