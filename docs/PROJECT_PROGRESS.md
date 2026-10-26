# UniXNU / OnePlus Ace 2 进度

**更新：2026-10-25｜依据：OpenCode 会话记录及本地移植资料**

- **已完成**：确认目标为 PHK110 / SM8475；准备 Linux ARM64 工具链与 UEFI 环境；接入 DarwinBoot、Ace 2 电源键驱动，修正从 payload FAT 加载 `UniXNU.efi`；liuqin 内核已启动到 XNU entry / stage 标记；提取原厂 UEFI 中 97 个 PE。始终未刷写手机分区。
- **待改重点**：`~/Downloads/uefi-ace2/Platforms/OnePlus/ace2Pkg/Drivers/ShengBootMemoryDxe/ShengBootMemoryDxe.c`（内存映射/高地址）；`~/Downloads/iPadOS-liuqin/shim/`、`tools/mkadt.py`、`tools/mkpayload.py`（评估并适配 Ace 2 启动链）；补齐并验证 PHK110 的 DTB、板级配置及打包流程。OpenCode 的 `~/Downloads/unixnu/package/Build/` 是未跟踪构建产物，不要当作源码提交。
- **待解决**：UniXNU 内核卡在 physmap / stage 12；Ace 2 非连续内存导致现有 ADT 参数调整无效。iPadOS-liuqin 的 shim 尚未适配 Ace 2，且缺少对应 root image。LineageOS Ace 2 源码仓和准确 DTB/驱动资源仍待确认；XNU CI 新内核构建也未打通。
- **下一步**：① 找到匹配的 Ace 2 device/kernel/vendor 源码并核对 DTS、内存布局和驱动；② 对照 ios-sweet 高内存实现，先验证 shim/ADT 与启动链适配；③ 小步构建、记录日志，继续只用 `fastboot boot` 验证。
- **注意**：严禁 `fastboot flash`、擦除或改槽；手机 12GB DRAM 不连续，勿照搬其它设备地址/面板参数；`iPadOS-liuqin` 能启动不代表 Ace 2 已兼容。当前进度记录涉及 Downloads 下独立工作区，本目录中的端口说明可能尚未同步。

## 2026-10-25 同机型 Udon 源码对齐

同机型公开项目：`takasugl/UniXNU-udon` + `takasugl/uefi-udon`（PHK110，已实测到 iPadOS 用户态）。对照后确认此前调 ADT `dram-base/size` 是错的方向，真正决定 XNU 可用内存的是 `/chosen/darwinboot-memory-size`（DarwinBoot 窗口）。

已落盘改动（尚未上机）：

- `~/Downloads/uefi-ace2/.../ShengBootMemoryDxe.c`：改用 Udon 策略，只向 GCD 添加 4GB 以下、上限 1GB 的 DRAM；删除 `ForceHigh(0x800000000)` 和 8GB fallback。
- `~/Downloads/uefi-ace2/.../MemoryMapLib.c`：新增固定 `{"Kernel", 0xA8000000, 0x10000000}`，紧贴 framebuffer 下方。
- `~/Downloads/uefi-ace2/Resources/Configs/ace2.toml`：FD 改为 `0xA7100000 / 0x400000`（4MB）。
- `~/Downloads/UniXNU-liuqin/board.toml`：`dram_size = 0xC0000000`，`owned_memory_size = 0x130000000`（4.75GiB 连续窗口）；firmware 指向 `uefi-ace2` 的 `ace2` 配置/`ace2Pkg`。
- 修正 `~/Downloads/unixnu/scripts/unixnu/bootimg.py` 的 v4 头部校验（原逻辑按 v0 解析，会把 `page` 读成 0）。

已本机构建并验证：

- UEFI：`Build/ace2Pkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`，4MB，构建通过。
- 新 payload ADT：`dram-base=0x80000000`、`dram-size=0xc0000000`、`darwinboot-memory-size=0x130000000`。
- 修正 payload 的 framebuffer 参数为 Ace 2 的 `fb=0xb8000000,1240,2772,4960`（此前误用了 liuqin 的 1800x2880）。
- 可测试镜像：`~/Downloads/unixnu/out/ace2/boot/boot-udon-port.img`，68,681,728 字节，SHA-256 `4cdda78ed200ec5584f8ee7a69aaf1d00aedbbd38feea384272e58bfa0618e31`，`hardware_tested: false`。

只读 ADB 复核（2026-10-25 20:10，手机当前在 Android）：
- `MemTotal 11,485,504 kB`（约 10.95 GiB 可用，符合 12GB 机型）。
- `/proc/zoneinfo` 的 `Normal` zone `spanned 10,485,760` 页（4K 页，40 GiB 地址跨度），`present 3,089,664` 页（11.78 GiB）。这与“高 bank 在 0x800000000（32 GiB）以上、低 bank 在 0xC0000000 以下”一致，也解释了 Udon 的 4.75GiB 连续窗口来源。
- `/proc/iomem`、`/sys/firmware/fdt`、`/proc/cmdline` 对 UID 2000 仍不可读，没有拿到精确 bank 表。

下一步：只 `fastboot boot` 这个镜像，观察是否越过 stage 12；若 DarwinBoot 报 `NO WINDOW`，说明当前 UEFI 没暴露 4.75GiB 连续段，再按 Udon 的内存表逐项比对。

## 2026-10-25 高 bank 打通（本轮终点）

在 `ShengBootMemoryDxe.c` 里删掉原来的 `ForceHigh(0x800000000, 512MiB)` 后，4.75GiB 窗口分配失败；DarwinBoot 屏显示：

```text
NO WINDOW 130000000 BIG RUN 312A000 @ F8000000
FREE 80E00000
FREE A5000000
FREE E5800000 + 3000000
FREE F1400000 + 2C00000
FREE F8000000 + 312A000
```

说明低 4GB 只有约 51MiB 连续空闲，高 bank 没有被发布。随后按同 SoC 8GB 机型的实测段（`0x840000000 + 0x140000000`，5GiB）在 `AddMemory()` 末尾显式发布高 bank；用 `boot-highmem.img` 上机后：

- DarwinBoot 不再报 `NO WINDOW`；
- 屏幕显示 `Exiting boot services. A green bar ...`；
- 顶部出现**绿色横条**，说明 XNU entry 代码已执行；
- 手机不再快速回到 Android，画面保持。

这是首次确认：**4.75GiB DarwinBoot 窗口 + XNU 入口在 Ace 2 上成立**。

镜像：
- `~/Downloads/unixnu/out/ace2/boot/boot-highmem.img`
- 68,681,728 字节，SHA-256 `8f7dd50414ada439ce88dc630cd2b9df1d0d3a26ab9a173e50581acd1280d455`

同时确认的两件事：
1. payload FAT 必须包含 `EFI/UniXNU/UniXNU.efi`；缺它时 UEFI 报 `Image ... start failed: Not Found`，BDS 直接“Failed to Find an Operating System”。当前是手动 `mcopy` 进去的，下一步要固化到打包流程。
2. 从 UniXNU 菜单加载自建 `Ace2MemDiag.efi` 返回 `Access Denied`（`LoadImage` 被固件安全策略拒绝），所以菜单外挂 EFI 诊断这条路不可用；后续诊断应放在 FV 内或以内核打点实现。

下次继续：
1. 先确认 XNU 现在停在 stage 12 之后还是仍在 `arm_vm_physmap_init` 附近。最直接的办法是重新启用 `zzz-liuqin-usb-debug.patch` 里 `liuqin_early_marker()` 的阶段色带（当前被 `return;` 关掉），或把 `liuqin_stage` 的最后一个值以文本/色块画到屏上；需要重编内核（CI）。
2. 把 `UniXNU.efi` 的 payload 注入做成脚本/board.toml 选项，避免每次手动 `mcopy`。
3. 若 stage 12 已过，继续按 Udon 的 `zzzzz-skip-physical-timer.patch`、`native-ufs-root` 和 trust cache 顺序推进。
