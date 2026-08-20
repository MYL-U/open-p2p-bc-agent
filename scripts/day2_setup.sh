#!/usr/bin/env bash
# 第 2 天：GPU 服务器环境初始化 + toy 子集 + 150M 权重下载
# 说明：本脚本按官方 README（elefant-ai/open-p2p）整理，在服务器 Linux 上执行。
# 用法：bash scripts/day2_setup.sh [仓库目录，默认 $HOME/open-p2p]
set -euo pipefail

REPO_DIR="${1:-$HOME/open-p2p}"

echo "==> [1/6] 安装 uv（Python 依赖统一由 uv 按锁文件管理，自动创建虚拟环境）"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

echo "==> [2/6] 安装系统级依赖（ffmpeg7、clang、socat 等）"
sudo apt update
sudo apt install -y build-essential git nvtop htop software-properties-common
sudo add-apt-repository -y ppa:ubuntuhandbook1/ffmpeg7
sudo apt update
sudo apt install -y ffmpeg
sudo apt install -y libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libavdevice-dev libavfilter-dev
sudo apt install -y clang libclang-dev socat
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

echo "==> [3/6] 提升文件描述符上限（本会话生效）"
ulimit -n 65535 || echo "警告：ulimit 设置失败（可能因权限），如推理报 Too many open files 再处理"

echo "==> [4/6] 克隆官方仓库"
if [ ! -d "$REPO_DIR/.git" ]; then
  git clone https://github.com/elefant-ai/open-p2p.git "$REPO_DIR"
fi
cd "$REPO_DIR"

echo "==> [5/6] 登录 Hugging Face（Gemma tokenizer 需要，交互式输入 token）"
uv run huggingface-cli login

echo "==> [6/6] 下载 toy 子集（--toy，绝不下载全量）与 150M 权重"
# 数据源：HF elefantai/p2p-toy-examples（--toy 固定，防误拉全量 p2p-full-data）
# 权重源：HF guaguaa/open-p2p 的 150M/* → ./checkpoints/150M/
uv run python scripts/download_data.py --toy
uv run python scripts/download_checkpoints.py 150M

echo "==> 完整性自检（官方脚本无显式校验，依赖 huggingface_hub ETag + 文件清单 + 加载 smoke test）"
echo "--- 权重文件清单（应含 model_config.yaml + checkpoint-step=*.ckpt）---"
ls -lh checkpoints/150M/
echo "--- 数据目录清单（toy 子集，VideoAnnotation proto 文件）---"
ls -laR dataset 2>/dev/null | head -40 || echo "dataset 目录暂为空，请检查下载"

echo "第 2 天初始化完成。下一步：运行推理服务 + 自研采集客户端（见 README 命令速查）。"
