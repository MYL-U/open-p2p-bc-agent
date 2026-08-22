# 基于 Open P2P 的游戏行为克隆智能体（腾讯 IEG 课题工作区）

行为克隆游戏智能体，研究对象为 Open P2P / Pixels2Play 模型。输入游戏画面帧，输出预测的键盘与鼠标操作。
完成方式：独立完成。实验环境：老师提供的 GPU 服务器（推理与评测）；交付：课内不演示真机，主路径以录屏 + 逐帧比对呈现。

## 官方资源

- 仓库：https://github.com/elefant-ai/open-p2p
- 项目主页：https://elefant-ai.github.io/open-p2p/
- 数据集：https://huggingface.co/datasets/elefantai/p2p-full-data（**仅用 `--toy` / 官方分批参数，绝不下载全量**）
- 论文：arXiv:2601.04575（Pixels2Play-0.1）

## 工作区结构

```
.
├── README.md                    # 本文件：概览、部署/运行说明、9 天计划、约定
├── docs/                        # 每日实验报告（01 起编号）+ 约定文档
│   ├── NN-第N日实验报告.md       # 每日报告（结构对齐指导书 6.1）
│   ├── 04-CUDA故障诊断报告.md    # CUDA 故障根因与修复记录
│   ├── PROJECT_MEMO.md          # 项目备忘（稳定约定 + 当天计划，见课程 03）
│   ├── API_CONTRACT.md          # 接口约定（UDS / JSONL / 评测）
│   └── server-info.md           # 服务器信息（IP/端口，密码不落盘）
├── scripts/                     # 自研脚本（面向 GPU 服务器，Linux/bash）
│   ├── collect_predictions.py   # UDS 采集客户端：逐帧发 Frame 收 Action，落盘 JSONL
│   ├── evaluate.py              # 评测：预测 vs 标注对齐，键盘一致率 + 鼠标皮尔逊
│   ├── 150M_random_test.yaml    # 纯视觉推理配置（null tokenizer，免 gated 下载）
│   ├── day2_setup.sh            # 第 2 天：服务器系统包 + uv + 克隆官方仓库
│   └── day2_server_setup.sh     # 第 2 天：完整服务器初始化脚本
└── .gitignore                   # 忽略规则（依赖/敏感信息/产物/实验数据），逐条说明见第 4 日报告
```

约定：`docs/` 下每日报告按 `NN-标题.md` 编号；`scripts/` 内脚本面向 GPU 服务器（Linux/bash），本地仅维护文档与脚本。

## 课内交付边界（核心）

- 推理与评测：只在 GPU 服务器上完成。
- 课内不演示真机、不搭建本地 Windows 环境、不依赖本地 Recap 工具。
- 主线只用官方 150M 原始预训练权重，不做多模型对比、多游戏混合训练。
- 呈现方式：录屏 + "模型输出 vs 人类标注"逐帧比对。

## 9 天迭代计划（草稿，详见报告附录 B）

| 天 | 内容 | 产出（对齐指导书 2.2） |
|----|------|------|
| 1 | 选题、范围、主路径、验收、风险、计划拆解 | 第 1 日报告（已完成） |
| 2 | 方案组成与技术选型（官方仓库结构、推理脚本、数据接口、uv 环境） | 组成与选型说明 |
| 3 | 主路径数据与调用约定（toy 数据格式、帧/动作约定、假实现边界） | 约定与边界说明 |
| 4 | 工程/环境起步：uv 环境、克隆仓库、toy 数据 + 150M 权重、启动说明 | 环境就绪 + 工程结构审查 |
| 5 | 主路径贯通：离线推理、划 200 帧隔离测试集、算指标、逐帧对照录屏 | 可演示版本 + 对照录屏 |
| 6 | 两块可验证工作自测（重叠校验复验、指标复算抽查） | 两块自测 |
| 7 | 贯通验证与排错 | 通检表与排错记录 |
| 8 | 回归、启动说明与交付准备（他人可跟做 + 对照必做自测表） | 启动说明 + 自测对照表 |
| 9 | 结课大报告（建议 3000 字以上）+ 最终录屏 | 结课大报告 |

## 部署与运行（GPU 服务器）

所有命令在服务器 `/root/workspace/open-p2p`（官方仓库，uv 环境）内执行。依赖由 `uv` 按 `uv.lock` 统一管理（非手动 pip）；`uv` 在 `/root/.local/bin/uv`。

```bash
# 1) 安装依赖（首次；已初始化过系统包与 uv，见 scripts/day2_server_setup.sh）
cd /root/workspace/open-p2p
uv sync

# 2) 下载数据与权重（首次；需 HF_TOKEN）
uv run huggingface-cli login          # 或 export HF_TOKEN=<token>（仅注入环境，不入库）
uv run python scripts/download_data.py --toy          # 仅 toy 子集，绝不下载全量
uv run python scripts/download_checkpoints.py 150M    # 官方 150M 原始权重

# 3) 启动推理服务（UDS 服务，socket /tmp/uds.recap；纯视觉模式）
uv run python elefant/policy_model/inference.py \
  --config scripts/150M_random_test.yaml \
  --checkpoint_path checkpoints/150M/checkpoint-step=00500000.ckpt \
  --no-compile

# 4) 冒烟采集（1 个视频、10 帧，验证主路径通了）
uv run python scripts/collect_predictions.py \
  --dataset dataset --uds-path /tmp/uds.recap \
  --output predictions/smoke.jsonl --max-videos 1 --max-frames 10

# 5) 全量采集 + 评测
uv run python scripts/collect_predictions.py \
  --dataset dataset --uds-path /tmp/uds.recap --output predictions/predictions_full.jsonl
uv run python scripts/evaluate.py \
  --predictions predictions/predictions_full.jsonl \
  --dataset dataset --output metrics/metrics.json --per-video

# 6) 停止推理服务
pkill -f "inference.py"      # 或 kill $(pgrep -f inference.py)
```

- **首跑验证**：冒烟采集输出应含 `"ok": 10`（或等价计数），且 `error` 全为 `null`。
- **纯视觉 vs 文本指令**：默认纯视觉（`150M_random_test.yaml`，`text_tokenizer_name: null`，无需 gated tokenizer）；文本指令模式须启动时加 `--input_text`（需真实 Gemma tokenizer，属扩展 B）。
- **采集容错**：单帧 15s 超时、连续失败 5 次放弃；失败帧以 `error` 字段落盘，不静默丢弃；`--append` 可断点续采，`--seed` 复现顺序。

## 必要环境变量

| 变量 | 用途 | 说明 |
|------|------|------|
| `HF_TOKEN` | 下载 toy 数据与 150M 权重 | 仅首次下载需要；经环境变量注入，**不入库** |
| `CB_SSH_PASS` | 本机 → 服务器 SSH/SFTP 工具链 | 本机临时密码变量，**不入库**（见 `.gitignore`） |

> 密钥类（服务器密码、HF token 真实值）一律不写进仓库与报告；仓库最多保留 `.env.example` 这类不含秘密的示例。

## 快速参考命令（官方，已核实）

```bash
# 克隆 + 进入
git clone https://github.com/elefant-ai/open-p2p.git && cd open-p2p

# 下载 toy 子集（小规模，仅供快速体验与评测）
uv run python scripts/download_data.py --toy

# 下载 150M 权重
uv run python scripts/download_checkpoints.py 150M
```

## 状态追踪

- [x] 第 1 天：选题与范围、主路径与验收、风险与应对、计划拆解（规划层，未实操）
- [x] 第 2 天：方案组成与技术选型（见 `docs/02-第2日实验报告.md`）；本地 Git 仓库初始化并推送远端；环境脚本就绪
  - 关键结论：推理为 UDS 服务（需自研采集客户端）；鼠标位移离散化为 bin 后采样解码（评测对象为解码后位移）；数据源 `elefantai/p2p-toy-examples`、权重源 `guaguaa/open-p2p`
- [x] 第 3 天：UDS 采集客户端 + 服务器环境执行 + 接口约定（见 `docs/03-第3日实验报告.md`、`docs/API_CONTRACT.md`）；真实权重冒烟 300 帧 ok=300
- [ ] 第 4 天：工程起步（README 启动说明、.gitignore、审查纪要、小步提交）
- [ ] 第 5~9 天：见计划表（对照录屏在第 5 天）
