# Ace 2（PHK110）当前进度

更新：2026-10-26

## 已完成

- UEFI 能启动到 Project Silicium BDS。
- UniXNU 菜单出现，payload 从 PONGFAT1 卷读取成功。
- DarwinBoot 能校验内核/ADT 并退出 boot services。
- **4.75 GiB DarwinBoot 窗口分配成功**，不再报 `NO WINDOW`。
- **XNU entry 代码已执行**：屏幕顶部出现绿色交接条，手机保持在该画面，不再快速回到 Android。

关键修复：低 4 GiB 只有约 51 MiB 连续空闲，必须由 `ShengBootMemoryDxe` 发布高 bank：

```text
0x840000000 + 5 GiB
```

工作镜像（本机，不含在 git 中，因为包含厂商固件）：

```text
~/Downloads/unixnu/out/ace2/boot/boot-highmem.img
bytes   68681728
sha256  8f7dd50414ada439ce88dc630cd2b9df1d0d3a26ab9a173e50581acd1280d455
```

## 还没完成

- 当前死点已定位到 `kernel_startup_bootstrap()` 内部，早于 `arm_vm_init`（不是 stage 12）。
- XNU 进入 entry 之后的可见 console / stage 标记仍待打通。
- UFS root、launchd、iPadOS 用户态。
- 触控、显示驱动、GPU、Wi-Fi、音频、电源管理等。

## 下次第一步

在 `kernel_startup_bootstrap()` 内部做 startup 函数级 PSCI 复位探针，
定位具体子系统；同时保留 nofb 修复（跳过 post-MMU 橙色/白色条 store）。

## 复刻

见 [`README.md`](README.md) 和 [`docs/PROJECT_PROGRESS.md`](docs/PROJECT_PROGRESS.md)。

只允许 `fastboot boot`，不要 `fastboot flash`、擦除或改槽。
