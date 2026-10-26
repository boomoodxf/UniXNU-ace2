# liuqin stock UEFI 厂商输入（已抽出）

来源：`E:\5555\liuqin_images_OS3.0.7.0.VMYCNXM_20260514.0000.00_15.0_cn_f57d372b08\...\images\uefi.elf`
（2,760,024 B，sha256 47785680513a7da753344dc86d3267a9…，固件版本 OS3.0.7.0.VMYCNXM）

抽法：ELF 里只有一个 FV（`_FVH` 在 0x1000，长 0x2A0000）→ 5 个 FFS → 其中 2 个是
GUID 定义压缩段（解出两个嵌套 FV，3.87 MB 和 3.10 MB）→ 递归展开后 159 个 FFS 文件。
其中 151 个带 UI 名。共抽出 **154 个文件**：58 个 Raw、93 个 PE32 模块。

产物：
- `liuqin-firmware/RawFiles/`（58 个：cfg、bmp、面板 XML）
- `liuqin-firmware/Modules/`（93 个 AArch64 PE32：DXE 驱动与应用）
- `liuqin-firmware/manifest.json`（每个文件的 GUID / FFS 类型 / sha256）
- `liuqin-modules.json`、`liuqin-uefi-tree.txt`（结构清单）

## 关键文件

| 文件 | 字节 | 段 | sha256 前 16 |
| --- | --- | --- | --- |
| RawFiles/uefiplat.cfg | 8050 | 0x19 | `5116faca4329b3b9…` |
| Modules/DxeCore | 196608 | 0x10 | `3ba8ead12f3ae067…` |
| Modules/ArmCpuDxe | 53248 | 0x10 | `32cd8b783aa72d6c…` |
| Modules/ArmGicDxe | 36864 | 0x10 | `7adc78a950e91a40…` |
| Modules/ChipInfo | 49152 | 0x10 | `a5e82f79034ac268…` |
| Modules/IPCCDxe | 45056 | 0x10 | `e91f717f5a3a3e73…` |
| Modules/GlinkDxe | 61440 | 0x10 | `9fbbf72bc75995c0…` |
| Modules/PlatformInfoDxeDriver | 32768 | 0x10 | `3f145b99b08d5181…` |
| Modules/ProjectInfoDxe | 57344 | 0x10 | `88121f2f5e4b99d6…` |
| Modules/HWIODxeDriver | 36864 | 0x10 | `32cbee375305035e…` |
| Modules/I2C | 49152 | 0x10 | `3b2904198c63bfce…` |
| Modules/DALTLMM | 49152 | 0x10 | `9233f83a9c8756bf…` |
| Modules/PmicDxe | 204800 | 0x10 | `44f40a685f7ce7f7…` |
| Modules/DiskIoDxe | 45056 | 0x10 | `be382ac80d1cd1d2…` |
| Modules/PartitionDxe | 53248 | 0x10 | `f421503ce47c2542…` |
| Modules/Fat | 65536 | 0x10 | `39af831ac8692db7…` |
| Modules/FvSimpleFileSystem | 45056 | 0x10 | `39d7888e0dd2432a…` |
| Modules/UFSDxe | 131072 | 0x10 | `c76d6f7522dcf69c…` |
| Modules/CmdDbDxe | 32768 | 0x10 | `8adac8f156c67da8…` |
| Modules/RpmhDxe | 65536 | 0x10 | `7f917c9e9c64ba11…` |
| Modules/NpaDxe | 81920 | 0x10 | `9ced898ce160f69a…` |
| Modules/ULogDxe | 77824 | 0x10 | `7472b6fca3e979dc…` |
| Modules/VcsDxe | 49152 | 0x10 | `bbf9e0e6e3534a2d…` |
| Modules/ClockDxe | 200704 | 0x10 | `f855406a63e42546…` |
| Modules/SmemDxe | 40960 | 0x10 | `b0843f6a7b918bd6…` |
| Modules/QcomBds | 122880 | 0x10 | `d3cffcba15a68731…` |
| RawFiles/BDS_Menu.cfg | 2944 | 0x19 | `1786bfcb2616efed…` |
| RawFiles/SecParti.cfg | 5150 | 0x19 | `fec3e97db6b6ffcc…` |
| Modules/GraphicsConsoleDxe | 49152 | 0x10 | `610bede37c247e86…` |
| Modules/SPI | 57344 | 0x10 | `59ecebb5a662aedc…` |
| Modules/FeatureEnablerDxe | 32768 | 0x10 | `ef9effb68f191eb7…` |
| Modules/DisplayDxe | 372736 | 0x10 | `d6a934cc70f37310…` |
| Modules/ButtonsDxe | 40960 | 0x10 | `4393f4a580ae5abd…` |
| Modules/IPCCDxe | 45056 | 0x10 | `e91f717f5a3a3e73…` |
| Modules/GlinkDxe | 61440 | 0x10 | `9fbbf72bc75995c0…` |
| Modules/PmicGlinkDxe | 49152 | 0x10 | `666af3296312ba9c…` |
| Modules/TsensDxe | 32768 | 0x10 | `8b1d6d0aa58ddea5…` |
| Modules/DDRInfoDxe | 45056 | 0x10 | `3964e347fe39369b…` |
| Modules/UsbfnDwc3Dxe | 98304 | 0x10 | `696a6a9065fec315…` |
| Modules/XhciDxe | 94208 | 0x10 | `39f5f0e90ae1da68…` |
| Modules/PILDxe | 118784 | 0x10 | `1cac0e5c3e73c2dd…` |
| RawFiles/logo1.bmp | 31318 | 0x19 | `abc0de5542c46d0d…` |
| RawFiles/PanelSimConfig.csv | 3081 | 0x19 | `71fe6237584883fd…` |
| RawFiles/Panel_M81_36_02_0a_dualdsi_dsc_lcd_video.xml | 6434 | 0x19 | `d8fb21cb7452966b…` |
| RawFiles/Panel_M81_42_02_0b_dualdsi_dsc_lcd_video.xml | 6195 | 0x19 | `a3e7649ab12793d1…` |
| RawFiles/uefipil.cfg | 5263 | 0x19 | `dfa8b53c737ef54d…` |
| RawFiles/QcomChargerCfg.cfg | 21075 | 0x19 | `c3b10d1bb9766dae…` |

## uefiplat.cfg 里的硬数据

```
MaxMemoryRegions = 74         UnusableDDRMemory 0x80000000 +0x600000
0x80000000 0x00600000  HYP
0x85200000 0x1DC00000  PIL Reserved
0xA1400000 0x02B00000  Display Demura
0xA7000000 0x00400000  UEFI FD            <-- 我们的固件卷窗口
0xA7400000 0x00200000  UEFI FD Reserved
0xA7AD9000 0x00400000  FV Region
0xA8000000 0x10000000  Kernel
0xB8000000 0x02B00000  Display Reserved  <-- ABL 连续 splash framebuffer
0xF8000000 0x07C00000  DXE Heap
NumCpus = 8   NumActiveCores = 8   SecPagePoolCount = 0x800
SharedIMEMBaseAddr = 0x146AA000   UefiMemUseThreshold = 0x1900
EnableUfsIOC = 1  UfsSmmuConfigForOtherBootDev = 1
```

## 面板

liuqin 的面板模块 XML 就在固件里，名字是
`Panel_M81_42_02_0b_dualdsi_dsc_lcd_video.xml`（正是主线记录的 CSOT 模组 m81_42_02_0b）：
HorizontalActive = 1800、VerticalActive = 2880、双 DSI、DSC、video mode。
（同族 `Panel_M81_36_02_0a_...` 是另一块屏，别选错。）

## DisplayDxe 已核验

`Modules/DisplayDxe` 是有效 PE32，machine = 0xAA64（AArch64），372,736 B。
这是后面接 GOP / 点屏的关键模块，sheng 的做法是把它的 DEPEX 依赖补齐
（它 original DEPEX 要求 9 个协议，其中 7 个由厂商驱动提供，另外 2 个
全镜像里找不到，就用一个自建 Dxe 装空 flag 协议绕过）。liuqin 要走同一条路。
