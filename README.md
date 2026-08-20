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
├── README.md                    # 本文件：项目概览、9 天计划、约定
├── docs/                        # 每日实验报告（01 起编号）
│   └── 01-第1日实验报告.md
└── scripts/                     # 服务器端脚本（第 2 天起逐步补齐）
    └── day2_setup.sh            # 第 2 天：环境初始化 + toy 数据 + 150M 权重
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

## 快速参考命令（已按官方 README 核实）

```bash
# 克隆 + 进入
git clone https://github.com/elefant-ai/open-p2p.git && cd open-p2p

# 登录 HF（Gemma tokenizer 需要）
uv run huggingface-cli login

# 下载 toy 子集（小规模，仅供快速体验与评测）
uv run python scripts/download_data.py --toy

# 下载 150M 权重
uv run python scripts/download_checkpoints.py 150M

# 离线推理（150M 权重）
uv run elefant/policy_model/inference.py \
  --config checkpoints/150M/model_config.yaml \
  --checkpoint_path checkpoints/150M/checkpoint-step=00500000.ckpt
```

> 注意：官方依赖由 `uv` 统一管理（非手动 pip），Python 版本由 uv 按锁文件解析；文本指令模式须启动时加 `--input_text`。

## 状态追踪

- [x] 第 1 天：选题与范围、主路径与验收、风险与应对、计划拆解（规划层，未实操）
- [x] 第 2 天：方案组成与技术选型（见 `docs/02-第2日实验报告.md`）；本地 Git 仓库初始化；环境脚本就绪
  - 关键结论：推理为 UDS 服务（需自研采集客户端）；鼠标位移离散化为 bin 后采样解码（评测对象为解码后位移）；数据源 `elefantai/p2p-toy-examples`、权重源 `guaguaa/open-p2p`
- [ ] 第 3 天：UDS 采集客户端 + 服务器环境执行
- [ ] 第 4~9 天：见计划表（对照录屏在第 5 天）
