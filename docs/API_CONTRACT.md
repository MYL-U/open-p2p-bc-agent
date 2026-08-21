# 接口约定（API Contract）

> 供脚本与服务共同遵守。**未写明的行为不得各自猜测。**
> 状态：**已定稿**（2026-08-21 依据官方源码 `unix_socket_server.py` / `action_mapping.py` / `inference.py` 核实，并已同步实现到 `scripts/collect_predictions.py`）。
> 与项目备忘的关系：本文档相对稳定（字段与调用形态）；当天计划见 `PROJECT_MEMO.md` 末节，两者分开放置。

## 1. 推理接口（Unix Domain Socket）

**调用形态**：服务端启动 `inference.py`（UDS 服务，监听 `/tmp/uds.recap`），客户端 `collect_predictions.py` 连接后逐帧发送 `Frame`、接收 `Action`。

**线协议**（已核实 `unix_socket_server.py`）：`[uint32 小端长度][protobuf 消息体]`。请求 `Frame{id, width, height, data}`，`data` 为 **raw RGB HWC 字节**（非 JPEG）；响应 `Action{keys[], id, mouse_action}`，`mouse_action = MouseAction{mouse_delta_px: Vec2Int, scroll_delta_px: Vec2Int, buttons_down[]}`。服务端对非 192×192 的帧自动 resize 到 192×192。

**采集客户端参数**（`scripts/collect_predictions.py`）：

| 参数 | 说明 |
|------|------|
| `--dataset` | toy 数据根目录（递归找 `*.proto` + 同级视频） |
| `--uds-path` | 默认 `/tmp/uds.recap` |
| `--output` | 默认 `predictions/predictions.jsonl` |
| `--video-name` | 默认 `192x192.mp4` |
| `--max-videos` / `--max-frames` | 测试截断 |
| `--frame-timeout` | 单帧接收超时（默认 15s） |
| `--reconnect-max` | 连续失败上限（默认 5） |
| `--seed` | 打乱视频顺序的可复现种子 |
| `--append` | 追加续跑，不覆盖输出 |

**启动参数**：

| 参数 | 说明 |
|------|------|
| `--config` | 模型配置，主线用 `checkpoints/150M/model_config.yaml`（192×192 输入，10 层 ×1024 维 ×16 头） |
| `--checkpoint_path` | 150M 权重 `.ckpt` 路径 |
| `--use_random_weights` | 假实现：随机权重跑通链路 |
| `--model_records_path` | 服务端旁路 JSONL，交叉验证用 |
| `--input_text` | 文本指令模式，仅启动时生效、运行中不可切换（主线暂不用） |

**动作空间口径**（已按 `action_mapping.py` 核实）：键盘 20 类字符串（`_no_key`、`Space`、`1`–`4`、`a/d/e/f/q/w/s/z`、`DownArrow`/`UpArrow`/`LeftArrow`/`RightArrow`、`LeftShift`/`RightShift`）；鼠标按钮 4 类（`_no_button`、`0`、`1`、`2`）；鼠标 x/y 离散 **23/17 bin**（x=24 边界、y=16 边界 → **y 为 17 而非 16**）；推理默认 `truncated_normal` 采样解码（X_STD=96、Y_STD=22）；`max_keys=4`、`max_mouse_keys=2`。

**成功一例**：客户端发送一帧 `Frame` → 服务端返回 `Action`（`keyboard.keys` + `mouse` 的 x/y/buttons）→ 客户端连同帧号写入预测 JSONL 一行。

**失败一例**：通道断开或超时（无响应）→ 客户端记录该帧为失败（`error` 字段），继续下一帧，不中断整批；进程退出码非 0 时视为运行失败。

## 2. 数据文件（人类标注）

**来源**：toy 子集 `VideoAnnotation`（protobuf），逐帧含 `user_action`：`keyboard.keys`、`mouse.delta/scroll/buttons`、`is_known`。

**读取口径**：`is_known=false` 的帧为 unknown action，评测与对照时按无效帧跳过，不参与指标。

## 3. 预测记录文件（JSONL）

**路径约定**：`predictions/predictions.jsonl`（目录随脚本生成）。

**字段（已定稿）**：

| 字段 | 类型 | 含义 |
|------|------|------|
| `video_id` | string | 来源视频标识（标注 metadata.id，缺省用目录名） |
| `frame_index` | int | 视频内帧序号（0 起） |
| `frame_ts` | int\|null | 标注帧时间戳（帧数超出标注时为 null） |
| `pred_keyboard` | list[string]\|null | 预测按键字符串集合 |
| `pred_mouse` | object\|null | `{delta_x, delta_y, scroll_x, scroll_y, buttons[]}`（像素位移 + 按钮字符串） |
| `is_known` | bool | 该帧标注是否已知动作（false 帧评测跳过） |
| `error` | string\|null | 失败帧的非空错误描述；成功帧为 null |

**成功一例**：一行一帧，`pred_keyboard` 与 `pred_mouse` 齐全、`error: null`。
**失败一例**：该帧发送/接收超时或断连 → 仍写一行、`error` 非空（记录错误类型与信息）、`pred_*` 为 null，评测时跳过；客户端对连续失败有限度重连，超出 `--reconnect-max` 后退出并返回非 0 退出码。

## 4. 评测接口（输入/输出）

**输入**：预测 JSONL + 对应 toy 标注文件。
**输出**：`metrics/` 下指标 JSON——按键一致率（按键集合完全相等判定）、鼠标皮尔逊相关系数（解码后位移）。参考水平：≈55% / ≈0.5，测到多少如实记录。

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-08-21 | 初稿（草案） |
| 2026-08-21 | 定稿：按官方源码核实线协议与动作空间（鼠标 y 修正为 **17** bin）；新增线协议说明与采集客户端参数表；JSONL 字段定稿并同步 `scripts/collect_predictions.py` |
