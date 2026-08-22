# 服务器 CUDA 故障诊断报告

> 日期：2026-08-21　服务器：a100-1（10.14.3.52:56271，root）
> 性质：**环境级故障，非项目代码问题**。容器内无法修复，需宿主机管理员处理。

## 1. 问题摘要

容器内一切 CPU / 文件 / SSH 操作正常，GPU 能被系统枚举到，但 **CUDA 无法创建任何计算上下文**：

- 所有真实 GPU 运算（矩阵乘、显存分配、torch 张量）报 `CUDA error: operation not supported`
- `cuDevicePrimaryCtxRetain` 返回 **801 = CUDA_ERROR_NOT_SUPPORTED**
- 用系统 CUDA 13.2 工具链编译的**最小 kernel 同样失败** → 证明与 torch / 项目代码 / Python 无关

## 2. 环境信息（证据 A–H）

| 项 | 值 |
|----|----|
| GPU | NVIDIA A100 80GB PCIe（0 MiB 使用，31°C，P0，MIG Disabled） |
| 驱动 | NVIDIA **Open Kernel Module 595.84**（2026-06-10 构建） |
| 内核 | 7.0.0-30-generic（Ubuntu） |
| CUDA 工具链 | /usr/local/cuda 13.2（libcudart 13.2.75） |
| torch | 2.9.1+cu128（`torch.cuda.is_available()` = True） |
| 运行环境 | **Docker 容器**（`/.dockerenv` 存在，2026-08-19 21:42 创建） |
| 设备节点 | /dev/nvidia{0,ctl,modeset,uvm,uvm-tools} 齐全 + /dev/nvidia-caps |
| 内核模块 | nvidia / nvidia_uvm / nvidia_modeset / nvidia_drm 均 Live 加载 |
| GPU Addressing Mode | **HMM**（Heterogeneous Memory Management） |
| `RmLogonRC` | **1**（正常应为 0；驱动资源管理器对 GPU 的初始化登录失败） |

## 3. 诊断证据链（逐层测试，证据 J）

```
cuInit = 0                          ✅ 用户态库加载、驱动版本匹配检查通过
cuDeviceGet = 0                     ✅ 设备枚举通过（所以 nvidia-smi 正常）
cuDevicePrimaryCtxRetain = 801 ❌   CUDA_ERROR_NOT_SUPPORTED —— context 创建失败
```

| 层 | 结果 | 说明 |
|----|------|------|
| nvidia-smi | ✅ | 用户态工具，只读驱动信息，不创建 context |
| 底层 driver API（cuInit/cuDeviceGet） | ✅ | 只做库初始化与设备枚举 |
| **context 创建（cuDevicePrimaryCtxRetain）** | ❌ 801 | 需要与内核 RM 建立会话，此步失败 |
| cudaSetDevice / cudaMalloc | ❌ | runtime 依赖 context |
| torch CUDA 张量 / matmul | ❌ | 同上 |
| 系统 CUDA 13.2 最小 kernel（nvcc 编译） | ❌ | **排除 torch/项目代码** |

## 4. 关键新证据：容器是"手动透传 GPU"，非标准 nvidia-container-runtime（2026-08-21 下午补充）

管理员反馈"宿主机一切正常"后，容器内深挖得到决定性证据：

| 检查项 | 容器内实际 | 标准 nvidia-container-runtime 应为 |
|--------|-----------|-----------------------------------|
| `NVIDIA_VISIBLE_DEVICES` 等环境变量 | **全部为空** | 有（=all 或 GPU UUID） |
| `NVIDIA_DRIVER_CAPABILITIES` | 为空 | 有（=compute,utility） |
| mountinfo | 仅 bind mount 了 `nvidia-smi`、`nvidia-persistenced`、`nvidia-cuda-mps-*`、`nvidia-debugdump`、OpenCL/Vulkan ICD | 还应有 nvidia-container-runtime hook |
| `/dev/nvidia-uvm` ioctl | 打开 OK 但请求返回 **ENOSYS** | 正常响应 |
| `RmLogonRC` | **1** | 0 |
| GPU `Active Sessions` | **0** | — |
| GPU UUID | GPU-56018363-1d22-5cac-2704-a6d31100de58 | — |

**解读**：这台容器很可能是用 `docker run --device=/dev/nvidia0 --device=/dev/nvidiactl ...`（或手动 bind mount 设备节点）的方式透传 GPU，**没有走 nvidia-container-runtime**。这种方式下：
- `nvidia-smi` 能跑（工具二进制被 bind mount 进来，读 /proc/driver 只需底层 API）
- 但 **CUDA 完整上下文创建需要容器运行时注入的驱动组件与正确设备初始化**，缺失 → `cuDevicePrimaryCtxRetain` 801

宿主机 `nvidia-smi` 正常（管理员视角），恰恰因为 **GPU 本身、驱动模块、设备都在宿主机/容器里正常枚举**；故障发生在"容器内用户态 → 内核驱动 → GPU"的**透传链路末端**，宿主机看不到这一层。

## 4.1 宿主机验证命令（给管理员，5 分钟定位）

在**宿主机**（非容器内）执行以下命令，即可区分"GPU 本身坏" vs "容器透传坏"：

```bash
# ① 宿主机真实 CUDA 上下文测试（最关键）
cat > /tmp/ctx_test.cu <<'EOF'
#include <cuda_runtime.h>
#include <stdio.h>
int main(){ float *d; cudaError_t e = cudaMalloc(&d, 1024);
  printf("cudaMalloc=%d %s\n", (int)e, cudaGetErrorString(e)); return 0; }
EOF
nvcc /tmp/ctx_test.cu -o /tmp/ctx_test && /tmp/ctx_test   # 期望: cudaMalloc=0 success

# ② 宿主机 RmLogonRC（应为 0）
cat /proc/driver/nvidia/params | grep RmLogonRC

# ③ 容器是如何创建的（关键）
docker inspect <容器ID或名> --format '{{.HostConfig.Runtime}} | devices={{json .HostConfig.Devices}} | env={{json .Config.Env}}'
docker ps | grep <hostname 或容器名>
```

- 若宿主机 ① 成功、② 为 0 → **100% 是容器透传问题**，按第 5 节方式重建容器即可
- 若宿主机 ① 也失败 → 是宿主机驱动问题（重装/换版本）
- ③ 的输出请一并提供，可精确判断透传方式

## 4.2 根因分析

故障特征组合指向**宿主机驱动 ↔ 容器 GPU 透传层**：

1. **`RmLogonRC: 1` 是核心异常信号**：RM（Resource Manager）在驱动初始化时对 GPU 的登录调用返回失败。正常加载的驱动该值为 0。RM 登录失败 → 后续所有需要 RM 会话的 CUDA 操作（即 context 创建）全部不可用。
2. **GPU Addressing Mode = HMM**：Open Kernel Module 在 HMM 模式下有已知兼容性问题，可能与驱动 595.84 组合不当。
3. **非标准容器透传**（见 4.1）：无 NVIDIA_* 环境变量、工具二进制 bind mount、UVM ioctl ENOSYS——强烈提示容器创建时未使用 nvidia-container-runtime，导致上下文层组件缺失。

**结论**：问题在容器创建时的 GPU 透传配置或宿主机驱动状态，**不是**：
- ❌ torch / Python 版本（系统 CUDA 最小 kernel 也失败）
- ❌ 项目代码 / 配置 / 数据
- ❌ 磁盘、内存、网络（均正常）

## 5. 修复建议（宿主机管理员侧）

按优先级尝试：

1. **重启宿主机 / 重新加载驱动**：`nvidia-smi --gpu-reset` 或完整重启，观察 `RmLogonRC` 是否归 0。
2. **重建容器 GPU 透传**：删除并重建容器，用标准 **nvidia-container-runtime**（`--gpus all` 或 NVIDIA_VISIBLE_DEVICES=all + NVIDIA_DRIVER_CAPABILITIES=compute,utility）重新创建，避免手动 mknod 挂载设备导致 context 层不可用。
3. **检查驱动模块与 GSP 固件**：确认宿主机 `enable_gsp_firmware` 参数与 595.84 匹配；尝试 `modprobe -r nvidia_uvm nvidia_drm nvidia_modeset nvidia && modprobe nvidia`。
4. **降级/更换驱动版本**：若 595.84 + HMM 组合异常，换官方推荐的稳定版（如 535/550/560 LTS 分支），或在宿主机禁用 HMM（`NVreg_EnableHMM=0`）。
5. **若宿主机多 GPU 共享**：确认该容器未被其他任务的 GPU 进程占满/锁定。

## 6. 容器内可用的替代路径（已就绪）

管理员修复 GPU 前，以下工作**已完成且已验证**，GPU 一旦可用即可直接继续：

| 资源 | 状态 |
|------|------|
| uv 环境（Python 3.13.2 / torch 2.9.1+cu128 / 642 依赖） | ✅ |
| toy 数据（3 样本，43176 标注帧） | ✅ |
| `collect_predictions.py`（UDS 采集客户端） | ✅ |
| `150M_random_test.yaml`（去 gemma tokenizer 测试配置） | ✅ |
| `evaluate.py`（评测脚本，按键一致率 + 鼠标皮尔逊 r） | ✅ 冒烟测试通过（1.0/1.0） |
| 150M 真实权重 2.05GB（SHA256 校验一致） | ✅ |
| GPU 计算 | ❌ 待管理员修复 |
