# liuqin (Xiaomi Pad 6 Pro / SM8475) UniXNU 启动进展

最后更新：2026-10-23 09:05 本地时间

## 目标

让 UniXNU (XNU) 在 liuqin 上启动，并最终枚举出 CDC-ACM USB 调试口（内核参数 `liuqin_usb=1`）。

## 阶段色带（当前进度定位手段）

`liuqin_stage(n)` 除了记 `lq_rec[]`，还通过 identity 映射往 `0xb8000000` 画一条 44 行高的带子，
行号 `1200 + 70*n`、颜色按 8 色循环：绿黄蓝洋红橙白红青。

- 1 `arm_init` 进入 / 2 过了 `PE_init_platform` / 3 即将 `arm_vm_init` / 4 `arm_vm_init` 返回后（不该出现）
- 5 `arm_vm_init` 入口 / 8 内存配置检查后 / 9 取到 bootstrap 页表 / 10 `init_ptpages` 后
- 11 `arm_vm_prot_init` 后 / 12 `arm_vm_physmap_init` 后
- 13 `kva_active = TRUE` 后 / 14 内核镜像段登记前 / 15 `pmap_bootstrap` 前（这三条走「临时 KVA 映射」）
- `bsd_init`：240 行洋红大块（`liuqin_fb_bigband(2400,…)`）+ 原有的青色带

**TTBR0 陷阱**：`arm_vm_init` 里 `set_mmu_ttb(invalid_ttep)` 之后 identity 映射失效，任何往
`0xb8000000` 的写都会 fault（曾把 6/7 号标记放在这里，等于自己把内核打死，且「没出带」完全
不能说明问题）。现在在切换前用一条 2 MiB 块把显存映射到内核窗口的空闲槽
（`gVirtBase + 0xF000000`），把该 KVA 交给标记用，`pmap_bootstrap` 之后立刻 `liuqin_late_unbind()`。

## 当前状态（一句话）

**MMU 已通、C 代码在跑**：`boot-liuqin-2.img` 实拍确认 青黄蓝洋红**橙白**+绿灯（`MSR SCTLR_EL1` 成功、`ret` 完成）。
`boot-liuqin-4.img` 实拍确认阶段带 **1,2,3,5,8,9,10,11,12** 全出：`arm_init` 走到 `arm_vm_init`，
`arm_vm_init` 内部一路走到 `arm_vm_physmap_init()`（第 12 条），之后没有信号 —— 死点在
`arm_vm_physmap_init` 之后到 `pmap_bootstrap` 之前（含 `set_mmu_ttb(invalid_ttep)` 这一段）。

上一版为什么必挂（已修，留档）：手填映射块模板写成 `0x4c1`，`AP[2:1]=11` 只读，MMU 一开第一笔写显存就 fault —— 那一版**不可能**出橙带。

## 已证实的事实（含源码级证据）

1. 顶部绿带是 **DarwinBoot 的 EL1 交接桩**画的（`drivers/DarwinBoot/DarwinBootPkg/Driver/Entry.S`，`DarwinEnter`）。它只证明固件 `br x1` 跳过去了。
2. `DarwinEnter` 在跳转前还会 **`bic SCTLR.M` + `bic SCTLR.C` + `bic SCTLR.I`**，并对整个 owned 窗口 `dc civac` 清到 PoC。所以内核入口处 **cache 全关、MMU 关**，此后所有页表/显存写入都是直写 DRAM（无 cache 一致性问题）。
3. DarwinBoot 的交接摘要实测值（`Print`）：
   - `kernel va=0xfffffff00427c000`（最小段 `__PRELINK_TEXT`）、`pa≈0x84527c000`（注意：进度文档里早先抄成了 9 位，实际是低 DRAM 里的 ~2.2 GiB 处，对应 args/video 都在 `0x8..`-`0xb..` 段）
   - `entry pa≈0x847652000`，entry words `d2b7031a 529ffffb 72bfe01b d2a0003c`（正是我们插入的青色打点代码）
   - `args pa=0x8f516000`（窗口内 +177 MiB）、`window=0x10000000`（256 MiB；ADT 可给 ≥256 MiB，`DarwinWindowSizeValid` 要求 ≥0x10000000 且 2 MiB 对齐）
   - `video base=0xb8000000 1800x2880 row=7200 32bpp`，framebuffer 在加载窗口**外**
   - `tcr=0x20080351b`（固件值，T1SZ=0，XNU 会覆盖）、`sctlr=0x3009193d`、`parange=2`
4. **XNU 自己装的 TCR_EL1 是对的**（从编好的 `kernel.macho` 里读出静态初值）：`sysreg_restore.tcr_el1 = 0x00000022a51a251a` → T0SZ=T1SZ=26、TG0=TG1=4 KiB、IPS=40 位 PA、TBI0=1。不是 TCR 的锅。
5. **XNU 的 bootstrap 块模板 = `0x601`**（`kernel.macho` 反汇编 `mov x11, #0x601`；= `ARM_TTE_BOOT_BLOCK` = valid|block|SH(outer)|AttrIndx(writeback)|AF）。我们之前手填的 `0x4c1` 是 `AP[2:1]=11`（只读），开 MMU 后第一次 `str` 到显存就权限 fault。
6. 打点带（base/7200 = 屏幕行号）：青 `0xb8180000`（`_start`）、黄 `0xb81c0000`（`common_start`）、蓝 `0xb8200000`（MAIR 写完）、洋红 `0xb8240000`（写 SCTLR 前）、**橙 `0xb8280000`（MSR SCTLR + isb 之后）**、白 `0xb82c0000`（`ret` 前）。
   - 历史实测：只到洋红 → 死在开 MMU。
   - 本轮新增 **灯 `0xb8380000`**（洋红之后）：读出 PC 那条 L2 项 → **绿**=有效块且映射的正是这个 2 MiB；**红**=其它。
7. 跨启动 DRAM 不保留（固定地址 probe 读回全 0，且每次启动窗口前 `Used` 被 `ZeroMem`）→ 只能用 framebuffer 当场打点。
8. framebuffer 是 BGRA：`0xFF00FF00`=绿、`0xFF0000FF`=蓝、`0xFFFF0000`=红、`0xFFFFA500`=橙、`0xFFFF00FF`=洋红。

## 本轮的改动（`patches/xnu/zzz-liuqin-usb-debug.patch` 的 start.s 段，已重写）

1. 手填映射改用 **`0x601`**（XNU 自己的 `ARM_TTE_BOOT_BLOCK`）。
2. 覆盖范围：`max(BA_MEM_SIZE, 256 MiB)`，并且**把条数钳在单个 L2 页剩余项内**（`512 - L2索引`）。上一版不钳，遇到大 `BA_MEM_SIZE` 会顺次写穿到后面的 KVA 页表。
3. 辅助函数**不再用栈**（`sp` 还是 KVA，MMU 没开时只能靠地址截断侥幸）。
4. **SCTLR 改成读-改-写**：`mrs x0,SCTLR_EL1; orr x0,x0,#1; msr`，只加 M。`mov x0,#1` 会清掉 RES1（EOS/IESB）和固件给的 `nTWI/nTWE`；`#if !VMAPPLE` 的回读比较同步改成 `mov x1,x0`，不会再 `b.ne .` 自锁。
5. 新增 `0xb8380000` 灯：填完后按 PC 反查 L1→L2，校验 `bits[1:0]==0b01` 且块地址与 PC 的 2 MiB 对齐值相同。
6. 不再调用 `create_bootstrap_mapping` 建显存映射（它会**改写 V=P L1 的整条槽**，把 XNU 建好的窗口 L2 表换掉）；改成同一个 `LiqinFill` 往已有 L2 表里填。

## 下一步（按优先级）

1. 刷阶段色带版，看屏幕 1200/1290/1380/1470/1560/1650/1740 行的七条带**最后一条是哪个颜色**：
   - 绿 `arm_init` 进 / 黄 过了签名设置 / 蓝 `machine_startup` 前 / 洋红 `machine_startup` 后
   - 橙 `arm_vm_init` 进 / 白 `pmap_bootstrap` 前 / 红 `pmap_bootstrap` 后
   - 只有绿 → 死在 arm_init 开头（很可能踩到 `arm_setup_pre_sign`/tunables）
   - 到洋红没了 → 死在 `machine_startup` 里
   - 到白没了 → 死在 `pmap_bootstrap`
   - 到红全齐 → pmap 起来了，接着指望 `kernel_map` + console 镜像滚字
2. 阶段定位后按对应函数继续加带/查寄存器；`panic` 路径也要能上屏（console 镜像 + `liuqin_fb_marker_boot`）
3. 之后回主线：`bsd_init` → console 出字 → DWC3 四道门 → CDC-ACM 枚举

## CI 现状（换过路）

GitHub 上 `1696108518/UniXNU` 这个 fork 的 Actions 被禁用（dispatch 一律 422 `Actions has been disabled for this repository`，`PUT actions/permissions` 也救不回来），所以现在改在**设备仓库** `1696108518/UniXNU-liuqin` 里跑同一条 workflow：它不再 `actions/checkout` 自己，而是匿名 `git clone --depth 1 --branch liuqin-build https://github.com/1696108518/UniXNU.git .` 取固定基线。用 `tools/gh-build-via-device.py` 上传+dispatch。

产物下载有坑：本机网络对单个响应在 ~30 MB 处截断，而 `kernel.macho` 有 51.8 MB，`api.github.com` 又不支持 Range。解法：`.github/workflows/split.yml`（workflow_dispatch）在 runner 上把文件切成 11 MB 分片推到 `ci-parts` 分支，再用 `tools/fetch-liuqin-kernel.py` 拼回来并按 ci-out 的 git blob sha 校验。

## 工具与命令

- 构建：`cd ~/port/UniXNU-liuqin && GITHUB_TOKEN=<PAT> python3 tools/gh-build-liuqin.py --steps kernel --defconfig liuqin_boot_defconfig --timeout 9000`
- 拉内核（artifact 的 302 到 blob 被墙，走 ci-out 分支）：`GET /repos/1696108518/UniXNU/git/trees/ci-out` → `git/blobs/<sha>`
- 重新生成 start.s 段：`python3 /mnt/c/Users/ASUS/Desktop/unixnu-port/gen-start-patch.py`（先用 GitHub API 取 pinned 的 `osfmk/arm64/start.s` 存到 `Desktop/unixnu-port/start_orig.s`）
- 汇编语法自检（不需要 macOS）：把补丁里 start.s 的 `+` 行抽出来加个头，`clang --target=aarch64-none-elf -c` 过一遍
- 打包：`unixnu build payload` → `scripts/wrap-payload-mbr.py` → `unixnu bootimg --uefi ../uefi-liuqin --fd .../SILICIUM_UEFI.fd --dtb ../liuqin-cape.dtb --ramdisk ...`
- 刷机：`C:\Users\ASUS\AppData\Local\PreloadTool\1.0_9daba3050879\fastboot.exe boot <img>`（序列号 `<SERIAL>`）
- 补丁自检：`python3 tools/check-debug-patch.py`；可应用性：`/tmp/sim` 合成树里先打 `architectural-timer-entry.patch`，再 `git apply --check`
- 从编好的内核取常量：`llvm-objdump --macho -d ~/liuqin-gh/kernel.macho`（`_start_first_cpu` 在 `0xfffffff0073ee05c`），`_sysreg_restore` 静态初值在文件偏移可见

## 踩过的坑（务必记住）

1. **补丁上下文要按「已打补丁的树」生成**：`architectural-timer-entry.patch` 把 `#if defined(BCM2837)` 改成带 `&&` 的形式且顶格无 tab；`native-4k-bootstrap-capacity.patch` 在 KVA `create_bootstrap_mapping` 之后插了 `b Lbootstrap_tables_ready` 一段——我们的插入点正好在它前面，必须靠结尾的 `b LiqinFillDone` 跳过辅助函数。
2. 同一文件内相邻 hunk 不能重叠上下文；相邻插入合并成一个 hunk。
3. 手改 patch 后必须 `tools/check-debug-patch.py` + 合成树 `git apply --check`，再花 1 分钟用 clang 汇编自检，否则 16 分钟一轮的 CI 白跑。
4. 块模板 `0x4c1` 是只读（AP[2:1]=11）；要 `0x601`。**这类错误会让「映射对不对」的实验完全失去意义。**
5. 不要相信跨启动内存，也不要相信 C 侧 `lq_rec`（每次启动被 `ZeroMem` 清掉）。
6. `0xFF0000FF` 在这块屏上是蓝色。
7. `x23` 已被 slide 修正过，不能当加载地址用；要读 `[x20, BA_PHYS_BASE]`。
8. 写文档/脚本不要用未加引号的 shell heredoc，也别依赖 `write_file` 写 WSL 路径（会走 bash 失败）——用 `execute_code` 落到 Windows 路径再 `cp`。
9. `bootstrap_pagetables` 只有 `BOOTSTRAP_TABLE_SIZE`（本配置 16 页）可用，`native-4k-bootstrap-capacity.patch` 让超限时原地自锁；自己填表时绝不能越过 L2 页边界。
