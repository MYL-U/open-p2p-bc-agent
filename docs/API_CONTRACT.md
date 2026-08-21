# 接口约定（API Contract）

> 供脚本与服务共同遵守。**未写明的行为不得各自猜测。**
> 状态：**草案**——字段名待第 3 天定稿，定稿后此处同步更新并标为「已定稿」。
> 与项目备忘的关系：本文档相对稳定（字段与调用形态）；当天计划见 `PROJECT_MEMO.md` 末节，两者分开放置。

## 1. 推理接口（Unix Domain Socket）

**调用形态**：服务端启动 `inference.py`（UDS 服务），客户端 `collect_predictions.py` 连接后逐帧发送 `Frame`、接收 `Action`。

**启动参数**：

| 参数 | 说明 |
|------|------|
| `--config` | 模型配置，主线用 `checkpoints/150M/model_config.yaml`（192×192 输入，10 层 ×1024 维 ×16 头） |
| `--checkpoint_path` | 150M 权重 `.ckpt` 路径 |
| `--use_random_weights` | 假实现：随机权重跑通链路 |
| `--model_records_path` | 服务端旁路 JSONL，交叉验证用 |
| `--input_text` | 文本指令模式，仅启动时生效、运行中不可切换（主线暂不用） |

**动作空间口径**（按 `action_mapping.py` 核实）：键盘 20 类（`_no_key=0`）、鼠标按钮 4 类、鼠标 x/y 离散 **23/16 bin**；推理默认 `truncated_normal` 采样解码（X_STD=96、Y_STD=22）；`max_keys=4`、`max_mouse_keys=2`。

**成功一例**：客户端发送一帧 `Frame` → 服务端返回 `Action`（`keyboard.keys` + `mouse` 的 x/y/buttons）→ 客户端连同帧号写入预测 JSONL 一行。

**失败一例**：通道断开或超时（无响应）→ 客户端记录该帧为失败（`error` 字段），继续下一帧，不中断整批；进程退出码非 0 时视为运行失败。

## 2. 数据文件（人类标注）

**来源**：toy 子集 `VideoAnnotation`（protobuf），逐帧含 `user_action`：`keyboard.keys`、`mouse.delta/scroll/buttons`、`is_known`。

**读取口径**：`is_known=false` 的帧为 unknown action，评测与对照时按无效帧跳过，不参与指标。

## 3. 预测记录文件（JSONL）

**路径约定**：`predictions/predictions.jsonl`（目录随脚本生成）。

**字段草案**（待定稿）：

| 字段 | 含义 |
|------|------|
| `frame_index` | 批内帧序号（0 起） |
| `video_id` + `frame_ts` | 来源视频与帧时间戳，用于与标注对齐 |
| `pred_keyboard` | 预测按键集合（按 20 类枚举值） |
| `pred_mouse` | 预测鼠标 x/y（解码后像素位移）与 buttons |
| `is_known` | 该帧是否参与评测 |
| `error` | 失败帧的非空错误描述（成功帧为 null） |

**成功一例**：一行一帧、字段齐全、`error: null`。
**失败一例**：该帧采集失败 → 仍写一行、`error` 非空，`is_known: false`，评测时跳过。

## 4. 评测接口（输入/输出）

**输入**：预测 JSONL + 对应 toy 标注文件。
**输出**：`metrics/` 下指标 JSON——按键一致率（按键集合完全相等判定）、鼠标皮尔逊相关系数（解码后位移）。参考水平：≈55% / ≈0.5，测到多少如实记录。

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-08-21 | 初稿（草案） |
