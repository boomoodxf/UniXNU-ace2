# liuqin 硬件底账

设备：Xiaomi Pad 6 Pro，代号 liuqin，SoC SM8475（骁龙 8+ Gen 1，Qualcomm 内部代号 cape），
1TB UFS（SK Hynix HN8T35DZHKX079），4096 字节逻辑/物理扇区。
本文件只写核实过的值，每条带来源。"未核实"另列。

## A. 已核实（可直接用）

| 项 | 值 | 来源 |
| --- | --- | --- |
| SoC | SM8475 / cape；compatible = "xiaomi,liuqin","qcom,sm8450" | liuqin-nixos sm8450-xiaomi-liuqin.dts |
| 主线归类 | 归到 sm8450 家族（含 alsa-ucm2 路径 Qualcomm/sm8450/Xiaomi-Pad-6-Pro） | liuqin-nixos |
| vendor_boot 里的 base DTB | 9 个 SoC 的 DTB，其中 Cape = 第 2 个（msm-id 0x212=530、0x21C? 见下） | 本地解包，见 D 节 |
| msm-id / board-id | msm-id = 531/540/530 各带 0x10000；board-id = <0x10008 0>；xiaomi,miboard-id = <0x10 0>（hwid.project=16 → 第 15 个 stock DTBO 条目） | liuqin-abl-boot-overlay.dts |
| 面板 | DSI `xiaomi,pipa-nt36532`，CSOT 模组 m81_42_02_0b，1800x2880，video mode，双 DSI | PORTING-NOTES |
| 背光 | KTZ8866 | PORTING-NOTES |
| 触控 | Novatek NT36532（笔、磁吸键盘、触控板） | PORTING-NOTES |
| ABL splash framebuffer | 0xb8000000，长 0x2b00000（45 MiB），1800x2880，a8r8g8b8，stride 1800*4 | sm8450-xiaomi-liuqin.dts chosen/framebuffer + reserved-memory/splash_region |
| ramoops | 0xa7000000，长 0x400000（4 MiB，console 2M + pmsg 2M） | 同上 |
| xbl_ramdump / xbl_sc | 0xa6b80000 +0x280000 / 0xa6e00000 +0x40000 | 同上 |
| adsp | 0x9fd00000 +0x3100000 | 同上 |
| PMIC 家族 | pm8350 / pm8350b / pm8350c / pm8450 / pmk8350 / pmr735a（= SM8450 waipio 那套，不是 SM8550 的） | 同上 include 列表 |
| UFS PHY | 0x1d80000（SM8450 是 0x1d87000），qcom,ufs-phy-qmp-v4-cape，v6 窗口 COM0/PCS 0x400/TX 0x1000/RX 0x1200 | 同上注释（对着 stock bootloader DTB 核过） |
| 按键 | 音量上、音量下、电源（无其它物理键） | golden 三键，BOOT-ARCHITECTURE |
| 音频 | 4 扬声器 CS35L41，mic WCD9385；vendor 无 AP 可见 DMIC | PORTING-NOTES |
| 指纹 | FPC1264 | PORTING-NOTES |
| 存储 | UFS，root ext4 | PORTING-NOTES（verified） |
| 现存系统 | Android 12 基线 + HyperOS（fingerprint liuqin:12/OS3.0.7.0.VMYCNXM），并已装 KernelSU + Ubuntu 双系统 | vendor_boot cmdline + E:\liuqin |
| 磁盘布局 | 见 E 节（userdata 起点 0x2A1600，被缩到 96 GiB，后面有 linux_root/linux_home） | E:\liuqin 备份 |
| stock 备份 | boot_a.img / boot_b.img（各 201MB）、vendor_boot_stock.img（100.6MB）、persist.img、GPT 头尾 | E:\liuqin-backup, ...\resize-backup-20261009 |

## B. 已核实（2026-10-20 第二轮，从 stock 固件抽出）

| 项 | 值 | 来源 |
| --- | --- | --- |
| UEFI FD 窗口 | 0xA7000000 +0x400000 "UEFI FD"，紧跟 0xA7400000 +0x200000 "UEFI FD Reserved" | uefi.elf → uefiplat.cfg |
| 固件内存表 | MaxMemoryRegions = 74，UnusableDDR 0x80000000+0x600000 | 同上 |
| ABL splash | 0xB8000000 +0x2B00000（Display Reserved） | uefiplat.cfg + 主线 DTS |
| Kernel 预留 | 0xA8000000 +0x10000000 | uefiplat.cfg |
| DXE Heap | 0xF8000000 +0x7C00000 | uefiplat.cfg |
| NumCpus | 8 / NumActiveCores 8，SecPagePoolCount 0x800 | uefiplat.cfg |
| UFS | EnableUfsIOC = 1，UfsSmmuConfigForOtherBootDev = 1 | uefiplat.cfg |
| 共享 IMEM | 0x146AA000，UefiMemUseThreshold 0x1900 | uefiplat.cfg |
| 面板模块 XML | Panel_M81_42_02_0b_dualdsi_dsc_lcd_video.xml（1800x2880，双 DSI，DSC，video） | uefi.elf RawFiles |
| 厂商 UEFI 模块 | 154 个文件（93 个 AArch64 PE32 + 58 个 Raw），含 DisplayDxe/UFSDxe/ClockDxe/PmicDxe/QcomBds | uefi.elf 递归解包 |
| DisplayDxe | 有效 PE32，machine 0xAA64，372,736 B | 直接校验 |
| stock boot.img | header_version = 4，header_size 1584，kernel 46.8 MB，ramdisk 1.38 MB | images/boot.img |

细节见 docs/vendor-inputs.md。

## B2. 仍然未知（上机才能定）

- SMEM chip_id（sheng=207 只对 SM8550 有效）与 SMEM RAM 表（dram_size）。
- ABL 是否接受 header v0 包装（stock 是 v4）。这是唯一"静态看不出来、必须试一次"的项。
- 触控 NT36532 的 I2C 地址/中断号（写 Native 触控驱动要用；主线 touchscreen@0 节点可参考）。
- stock 内存表 74 个区间与主线 DTS reserved-memory 的完整对齐（sheng 做了 72 个描述符，liuqin 还没做）。

## C. 关键结论

SM8475 与 SM8450 在 PMIC、UFS PHY 版本、整体内存布局上高度同族，
Mu-Silicium 的 `Silicon/Qualcomm/WaipioPkg` 是正确底座；
但 Mu-Silicium 上游没有 liuqin 平台包、没有 SM8475 设备配置，平台层全部要新写。

## D. 我已经做过的解包（可复现）

vendor_boot_stock.img：header v4，page 4096，vendor_ramdisk 23615663 B，
dtb 段在偏移 23621632，长 6443739 B，里面是 9 个拼接 FDT：

    00 Qualcomm Technologies, Inc. Cape LTE Only SoC
    01 Qualcomm Technologies, Inc. Cape SoC          <- liuqin 的底座
    02 Qualcomm Technologies, Inc. CapeP SoC
    03-06 Diwali 系列                                  (不是这台)
    07 Ukee SoC                                        (不是这台)
    08 Waipio LE                                       (不是这台)

Cape 那个 DTB 里 memory 节点是空的（reg = 0,0,0,0），reserved-memory 只有通用区，
板级区（splash、ramoops 等）由 dtbo 分区在 ABL 阶段叠加 —— 所以 splash 地址只能从
dtbo 或主线 DTS 里拿，不能从这个 DTB 里拿。

## E. 磁盘布局（实测）

```
# 当前布局（2026-10，userdata 已缩小）
 34 rescue       2725376 .. 2758143   0.12 GiB
 35 userdata     2758144 .. 27924479  96.00 GiB   0x2A1600 .. 0x1AA17FF
 36 linux_root  27924480 .. 36313087  32.00 GiB
 37 linux_home  36313088 .. 249179130 812.00 GiB

# stock 布局（GPT 备份 sda-head.bin）
 35 userdata     2758144 .. 249179130 940.02 GiB  0x2A1600 .. 0xEDA2BFA
```
