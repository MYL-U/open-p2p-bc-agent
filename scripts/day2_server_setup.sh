#!/usr/bin/env bash
# 第 2 天：a100-1 (10.14.3.52) 环境初始化（在 /root/workspace 下执行）
# 用法：bash /root/workspace/day2_server_setup.sh
# 说明：系统为 Ubuntu 24.04 精简镜像（无 python3/git），本脚本补齐基础工具后按官方 README 安装。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

WS=/root/workspace
REPO_DIR="$WS/open-p2p"
mkdir -p "$WS"
cd "$WS"

echo "==> [1/7] 基础系统包（git/python3 等）"
apt-get update
apt-get install -y git python3 python3-pip python3-venv curl ca-certificates build-essential nvtop htop software-properties-common socat

echo "==> [2/7] ffmpeg（Ubuntu 24.04 自带 ffmpeg 6.x；PPA 升级 ffmpeg7 失败不中断）"
apt-get install -y ffmpeg libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libavdevice-dev libavfilter-dev
ffmpeg -version 2>/dev/null | head -1 || true
add-apt-repository -y ppa:ubuntuhandbook1/ffmpeg7 2>/dev/null && apt-get update && apt-get install -y ffmpeg 2>/dev/null || echo "PPA ffmpeg7 不可用，沿用系统 ffmpeg"
ffmpeg -version 2>/dev/null | head -1 || true

echo "==> [3/7] clang + rust（推理服务依赖）"
apt-get install -y clang libclang-dev
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
export PATH="$HOME/.cargo/bin:$PATH"

echo "==> [4/7] uv（项目依赖统一由 uv 按 uv.lock 管理）"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
uv --version

echo "==> [5/7] 提升文件描述符上限（本会话生效）"
ulimit -n 65535 || echo "警告：ulimit 失败，如推理报 Too many open files 再处理"

echo "==> [6/7] 克隆官方仓库到 /root/workspace"
if [ ! -d "$REPO_DIR/.git" ]; then
  git clone https://github.com/elefant-ai/open-p2p.git "$REPO_DIR"
fi
cd "$REPO_DIR"
git --no-pager log --oneline -1 2>/dev/null || true

echo "==> [7/7] 阶段一完成。下一步（需 HF token）：登录 + 下载 toy 子集与 150M 权重。"
echo "仓库位置: $REPO_DIR"
