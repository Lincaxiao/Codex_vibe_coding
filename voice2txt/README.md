# Voice2txt

本项目是一个 macOS Apple Silicon 本地音频转录桌面应用，技术栈为 `PySide6 + mlx-whisper`。

## 功能

1. 导入本地音频（`wav/mp3/m4a/flac`）并转录英文文本。
2. 本地录音，停止后自动触发转录。
3. GUI 右侧显示可复制文本。
4. 文本默认只在内存中展示，不自动落盘。
5. 点击 `Save as TXT` 后才写入 txt 文件（每次弹出 Save As）。
6. 固定使用单一高精度模型：`mlx-community/whisper-large-v3-fp16`。
7. 可查看并选择当前录音麦克风设备（支持“系统默认”）。

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

## 常见问题

1. 麦克风无法录音：请在 macOS 系统设置中给 Python/终端授予麦克风权限。
2. 导入失败提示 ffmpeg：确认 `ffmpeg` 已安装且在 PATH 中。
3. 首次转录较慢：模型首次下载和初始化耗时较高，后续会更快。
4. 固定使用高精度模型，首次下载体积较大，请耐心等待。

## 测试

```bash
cd /Users/smilechen/Documents/Codex_vibe_coding/voice2txt
python -m pytest
```
