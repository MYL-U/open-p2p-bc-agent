# 项目备忘（Project Memo）

> 用途：记录相对稳定的约定，供交接与 AI 助手协作。每次下达新任务前，先让助手阅读本文件。
> 维护规则：过时条目立即删除或标注「已失效」，只保留与当前阶段相关的约定，不粘贴长对话与无关旧结论。

## 技术栈

| 项 | 约定 |
|----|------|
| 依赖管理 | 官方仓库 `elefant-ai/open-p2p` 使用 **uv + uv.lock** 统一管理（非手动 pip），Python 版本由 uv 按锁文件解析 |
| 运行环境 | 服务器 **a100-1**（Ubuntu 24.04.4 / A100 80GB / 内存 247G），`uv sync` 完成（Python 3.13.2、torch 2.9.1+cu128，CUDA 已验证） |
| 本机侧 | Windows 命令行；经 OpenSSH/paramiko 访问服务器；命令走本地文件传递避免引号转义 |
| 模型权重 | 主线只用官方 **150M 原始预训练权重**（`guaguaa/open-p2p` 的 `150M/*` → `checkpoints/150M/`） |
| 数据 | 只用 `--toy` 子集（`elefantai/p2p-toy-examples`，约 1GB，已上传 `/root/workspace/open-p2p/dataset/`），**绝不下载全量 `p2p-full-data`** |
| 资源获取通道 | 服务器对 HF 生态全站不可达（DNS 污染）→ 一律「本机 hf-mirror 下载 → SFTP 上传服务器」 |

## 主路径接口索引

主路径：toy 数据 → 150M 权重 → UDS 推理 → 预测采集 → 评测 → 逐帧对照。

| 步骤 | 承担模块 | 接口约定 |
|------|----------|----------|
| 1. 数据加载 | toy 子集 `VideoAnnotation`（protobuf） | 见《接口约定》§2 |
| 2. 推理服务 | `elefant/policy_model/inference.py`（Unix Domain Socket 服务） | 见《接口约定》§1 |
| 3. 预测采集 | 自研 `scripts/collect_predictions.py`（UDS 客户端） | 见《接口约定》§1、§3 |
| 4. 评测 | 自研 `scripts/evaluate.py` | 见《接口约定》§4 |
| 5. 对照呈现 | 读 toy 标注 + 预测逐帧对齐（不用官方 playback：不支持 unknown action） | 指标口径见第 1 日报告 |

## 临时假实现边界

| 假实现 | 用途 | 替换计划 |
|--------|------|----------|
| `--use_random_weights`（随机权重推理） | 打通 UDS 采集链路，不依赖真实权重 | 链路验证通过后替换为 150M 真权重（计划第 4~5 天） |
| `--model_records_path`（服务端旁路 JSONL） | 交叉验证客户端采集结果 | 保留，与客户端输出比对使用 |

> 标注原则：凡仍在使用的假实现，必须在本文档与《接口约定》中保持标明；替换真实实现后即删除对应条目。

## 待决问题列表

1. gated tokenizer（Gemma）加载 smoke 测试：token 已获，tokenizer 文件已下载完整（`.hf_dl/embeddinggemma-300M/`），待服务器加载验证（需先重建连接参数，见 4）。
2. ~~采集客户端 ↔ 评测脚本的 JSONL 字段名~~：**已定稿**（2026-08-21），见《接口约定》§3，已同步 `scripts/collect_predictions.py`。
3. 200 帧隔离测试集的具体划分规则与重叠校验方式：待第 4 天落地。
4. `docs/server-info.md`（服务器连接参数）当前**缺失，需重建**，重建后才能进行服务器端 smoke 测试与后续部署。

## 当天计划（2026-08-21）

**今日已完成**：
1. 《接口约定》**定稿**：按官方源码核实 UDS 线协议（`/tmp/uds.recap`、`[4B LE len][proto]`）、动作空间口径（键盘 20 类 / 鼠标 **23/17 bin**，y 由 16 修正为 17）、`Frame.data` 为 raw RGB HWC；新增客户端参数表；JSONL 字段定稿。
2. 编写 `scripts/collect_predictions.py`（UDS 采集客户端）：读取 toy proto + 同级 `192x192.mp4` → 逐帧发 `Frame` 收 `Action` → 写 `predictions.jsonl`；含单帧超时、断连重连、失败帧 `error` 记录、`--seed` 可复现；本机语法校验通过。
3. 150M 权重（2.05GB）与 Gemma tokenizer 均已下载完整（`.hf_dl/` 中转）。

**待完成（需服务器连接参数）**：
4. 重建 `docs/server-info.md`，上传客户端与权重到 a100-1，以 `--use_random_weights` 跑通采集链路；完成 tokenizer 加载 smoke 测试。
5. 更新本备忘并推送仓库。

**验收标准**：随机权重下完整跑通「toy 数据 → Frame → Action → JSONL」链路；JSONL 字段与《接口约定》§3 一致；tokenizer 加载无报错。

> 本小节仅服务当日，过期即清理。
