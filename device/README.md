# UniXNU-liuqin（骨架 + 已核实的板级数据）

Xiaomi Pad 6 Pro / liuqin / SM8475 的 UniXNU 设备仓库，由 UniXNU-sheng 派生。

状态：**不能构建，不能刷**。但板级关键数值已经从 stock 固件里核实完了，
board.toml 里每个 TODO 都有明确的取值方法和当前状态。

    board.toml                 板级描述（userdata LBA、splash、FD 窗口已填实测值）
    configs/liuqin_defconfig   内核配置（从 sheng 派生，PMGR/Adreno/UUID 标了 TODO）
    docs/liuqin-hardware.md    硬件底账：已核实 / 仍未知，每条带来源
    docs/vendor-inputs.md      stock UEFI 抽出的 154 个厂商输入 + uefiplat.cfg 硬数据
    docs/porting-plan.md       四阶段计划、通过标准、当前阻塞、立刻可做的事
    docs/liuqin-usb-debug.md   内核 USB CDC-ACM 调试口（LIQDBG001）：开关、四道自检门、移植对照表
    patches/xnu/               49 个 UniXNU 基础补丁 + zzz-liuqin-usb-debug.patch（调试口本体）
    tests/liuqin_usb_host_test.c  调试口逻辑的主机侧测试（gcc，不需要内核）
    tools/capture-liuqin-debug.ps1  主机侧抓取脚本（按 VID/PID+序列号定位 COM，置 DTR）

配套（同级目录）
    ../UniXNU-sheng            设备仓库模板
    ../UniXNU                  构建驱动
    ../uefi-liuqin-seed        Mu-Silicium 设备配置种子（Resources/Configs/liuqin.toml）
    ../liuqin-firmware         从 uefi.elf 抽出的 93 个 PE32 + 58 个 Raw
    ../liuqin-nixos            主线 Linux 侧参考（面板/触控/ABL 身份/DTBO 资料）
    ../xiaomipad-6pro-mainline 主线内核与设备脚本参考

下一步：写 uefi-liuqin 的 liuqinPkg（见 docs/porting-plan.md）。
