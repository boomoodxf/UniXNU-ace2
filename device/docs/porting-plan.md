# liuqin 移植计划

四阶段，每阶段都有"在屏幕上能看见"的通过标准。前一阶段不过，不进下一阶段。
全部启动都是 `fastboot boot`（内存运行，不写 boot 分区），失败复位就回原系统。

## 阶段 1：UEFI 固件（Windows/WSL 可编译，不需要 Mac）

要做的事
1. fork Mu-Silicium -> uefi-liuqin。底座用 `Silicon/Qualcomm/WaipioPkg`（SM8450）。
   SM8475 的 PMIC 家族（pm8350/8450/...）和 UFS PHY v4-cape 都在这一套里。
2. 新建 `Platforms/Xiaomi/liuqinPkg/`：liuqin.dsc / liuqin.fdf / liuqin.dec /
   DeviceBuild.py / Include/{APRIORI,DXE,RAW}.inc / Library/{ConfigurationMapLib,MemoryMapLib}。
   骨架照 `UniXNU/uefi-sheng` 分支的 shengPkg 抄，数值换 liuqin 的。
3. `Resources/Configs/liuqin.toml`：uefi_fd.base/size（未知，必须先从固件确认）、
   boot_image.*（header v0 / base 0 / kernel_offset 0x8000 / tags_offset 0x1e00000 / pagesize 4096）。
4. 厂商输入：从 HyperOS liuqin 整包抽 DisplayDxe、面板 XML、Clock、TLMM、I2C、PMIC 等，
   用 sheng 的 `extract-sheng-firmware.py` + `import-sheng-uefi.py` 当管线。
5. 补丁：先带 `Resources/MuPatches/Gic-Spurious.patch`。
6. 显示：sheng 的第一版是 `SHENG_VENDOR_HW=0`（只用 Mu 驱动 + SimpleFbDxe 在 ABL
   splash framebuffer 0xb8000000 上发布 GOP），这个思路 liuqin 直接可用 —— 同一块
   framebuffer，同样 45 MiB。

通过标准
- `fastboot boot` 后不复位，屏幕有输出或串口有 UEFI 日志。
- 能枚举 UFS 块设备，能读 FAT 负载卷。

## 阶段 2：UniXNU 启动管理器（不需要 Mac）

    ./unixnu build package           # EDK II，Linux 可编
    ./unixnu bootimg --uefi ../uefi-liuqin --dtb liuqin.dtb --ramdisk none

通过标准：串口出现 `UNIXNU:` 行、菜单出现、配置摘要打印。

## 阶段 3：内核（必须 macOS + Xcode）

- patches/xnu + NativePrelink，iOS 17 / ARM64 / BCM2837 / DEVELOPMENT。
- IPSW 沿用 iPad7,1 17.7.11（board.toml 已填好，与机型无关）。
- 通过标准：`DARWINBOOT:` 交接日志、内核到平台专家、打出 /cpus /arm-io。

## 阶段 4：存储与用户态（macOS）

- `build userdata`（要 hdiutil），窗口 = userdata 分区（96 GiB 或恢复 stock 后 940 GiB）。
- `fastboot flash userdata` 后启动，根卷 UUID 对上，launchd 起来。

## 进度（2026-10-20）

已经写完的东西

| 产物 | 位置 | 状态 |
| --- | --- | --- |
| liuqinPkg 平台包 | uefi-liuqin/Platforms/Xiaomi/liuqinPkg | 16 个文件：dsc/fdf/dec/DeviceBuild.py + Include/{APRIORI,DXE,RAW}.inc + 2 个 Library + 3 个驱动 |
| 厂商模块导入 | UniXNU-liuqin/scripts/import-liuqin-uefi.py | 跑通：93 个 AArch64 模块 + 56 个 raw，带 GUID/DEPEX/sha256 清单 |
| 内存表生成 | UniXNU-liuqin/scripts/gen-liuqin-memory-map.py | 跑通：43 个描述符（来自 uefiplat.cfg，一个重叠已按先到先得拆成 gap） |
| 配置表生成 | 同上 | 38 个数值项 + 单核 headless 覆盖 |
| 预检 | UniXNU-liuqin/scripts/check-liuqin.py | 跑通：93+56 个文件 sha256 校验、FD 窗口校验、面板 1800x2880 校验、描述符对齐/重叠校验 |
| 设备配置 | uefi-liuqin/Resources/Configs/liuqin.toml | uefi_fd = 0xA7100000 / 0x300000 |

从 sheng 改过来的地方（都有据可查）
- `!include KailuaPkg/KailuaPkg.dsc.inc` → `WaipioPkg/WaipioPkg.dsc.inc`（SM8475 的 PMIC/UFS PHY 属于 waipio 家族）
- 删掉 SOC_TYPE（那是 Kailua 的 AB/AC 区分）
- FrameBuffer 3048x2032 → 1800x2880
- SMBIOS 型号 sheng → liuqin
- 板级驱动改名 Liqin{BootMemory,DisplayDepex,GopLog}Dxe
- 52 条 vendor INF 从 `Binaries/sheng/QcomPkg/Drivers/...` 映射到 `Binaries/liuqin/Modules/<UI>/<UI>.inf`
  （TLMMDxe→DALTLMM、SPMIDxe→SPMI、I2CDxe→I2C、SPIDxe→SPI 这类按 UI 名对齐；全部 52 条都能落地）
- SecParti.cfg 的 FFS GUID 双向核对通过：liuqin 与 sheng 都是 A1E235DE-E825-4591-9623-C43175811826

## 还差什么才能出 boot.img

1. 整棵 Mu-Silicium 树（Silicon/、BootShim、Resources/Scripts/mkbootimg.py）+ 子模块
   Common/Mu、Common/Mu_OEM_Sample、Silicium-ACPI；以及 Mu_Basecore（edk2）。
2. 构建工具：clang / lld / make（WSL 里还没有，正在装）。
3. EDK II BaseTools 自举（unixnu 会自动做）。
4. 然后 `./unixnu build firmware --uefi ../uefi-liuqin` 出 SILICIUM_UEFI.fd，
   `./unixnu bootimg --uefi ../uefi-liuqin --dtb <liuqin.dtb>`（DTB 可以先从
   vendor_boot.img 里那个 Cape DTB 取，ABL 会自己套 dtbo）。

## 上机风险（静态无法排除的）

1. ABL 可能不接受 header v0（stock boot.img 是 v4）。失败就改打包 v4。
2. 单核 headless 配置下 SEC/DXE 是否接受 43 个描述符（sheng 是 72 个，硬件验证过）。
3. ~~DisplayDxe 的 DEPEX 依赖~~ —— 已核实：liuqin 的 DisplayDxe.depex（180B）推 10 个
   GUID，其中正好包含 sheng 胶水驱动装的那两个孤儿 GUID，所以 LiqinDisplayDepexDxe 照搬正确。
4. 3 MiB 的 FD 是否装得下 93 个厂商模块（PE32 合计 6.29 MiB，FV 是 LZMA 压缩的；
   sheng 的 107 个 FFS 能压进 3 MiB）。放不下就把窗口扩到 0xA7000000 / 0x600000。

## 已知的坑（从 sheng 抄来的经验）

- 缺 `splash_region` 节点 → ABL 直接 `DisableDisplay()` 关屏。liuqin 的节点已确认：0xb8000000 / 0x2b00000。
- SEC 必须先选 SP_ELx（上一级用 SPSel=0 进来，否则异常全跑在失效的 SP_EL1 上）。
- GIC 有未处理的 IPCC 中断（INTID 0x105）会死循环，Gic-Spurious.patch 要带。
- sheng 的 stock DisplayDxe 依赖两个全镜像找不到的协议 GUID，它用
  ShengDisplayDepexDxe 装空 flag 协议绕过。liuqin 的 DisplayDxe 依赖可能不同，
  要照这个办法重做一遍。
