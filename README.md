# UniXNU on OnePlus Ace 2 / 11R (PHK110, Udon, SM8475)

Backup of the current Ace 2 bring-up, with the exact files that made the
DarwinBoot 4.75 GiB window and XNU entry work on hardware.

This is a **bring-up backup, not a ready-to-use OS**. It never writes a phone
partition. Test with `fastboot boot` only.

## Current result (2026-10-26)

| Stage | State | Evidence |
| --- | --- | --- |
| UEFI (`uefi-ace2`) boots | ✅ | `Project Silicium`, BDS, UniXNU menu |
| UniXNU menu + payload | ✅ | menu shows `ace2 (PHK110) ...` and `xnu` |
| DarwinBoot validates kernel/ADT | ✅ | `Exiting boot services` screen |
| 4.75 GiB DarwinBoot window | ✅ | no `NO WINDOW`; green hand-off bar appears |
| XNU entry code | ✅ | green bar; phone stays on the hand-off screen instead of resetting to Android |
| XNU console / stage beyond entry | ❓ | not captured yet |
| UFS root / launchd / UI | ❌ | not part of this milestone |

The previous blocker was memory: the low 4 GiB had only ~51 MiB of contiguous
free memory, so a 4.75 GiB window could not be allocated. `ShengBootMemoryDxe`
now publishes the same-SoC high bank at `0x840000000 + 5 GiB`; DarwinBoot then
allocates the window and hands off.

Working image (local, not in git because it embeds vendor firmware):

- `~/Downloads/unixnu/out/ace2/boot/boot-highmem.img`
- 68,681,728 bytes
- SHA-256 `8f7dd50414ada439ce88dc630cd2b9df1d0d3a26ab9a173e50581acd1280d455`
- kernel Mach-O SHA-256 `aceb48aca2ac7178bec5cfaca38ce35a58c69524ccb2c20bde9a099fca448cbf`

## Hardware facts used here

| Item | Value |
| --- | --- |
| Device | OnePlus Ace 2 / 11R, PHK110 / Udon |
| SoC | SM8475 (taro / cape), SoC ID 530 |
| DRAM | 12 GiB; low bank below 4 GiB, high bank at `0x840000000` |
| Kernel page size | 4 KiB |
| Panel | 1240 x 2772, stride 4960 |
| Framebuffer | `0xb8000000` |
| GIC | GICD `0x17100000`, GICR `0x17180000`, stride `0x40000` |
| UFS | controller `0x1d84000`, PHY `0x1d80000` |
| UEFI FD | `0xA7100000`, size `0x400000` |

## What is in this repository

```
device/                 copy of the UniXNU-liuqin device repo used for the build
  board.toml            payload, ADT, firmware and the working memory values
  configs/              kernel defconfig
  patches/xnu/          XNU patch series (4K, boot progress, USB debug, ...)
  scripts/              make-liuqin-adt.py, payload/CI helpers
  tools/                kernel fetch/build helpers
  .github/workflows/    kernel build / artifact split

uefi-overlay/           Ace 2 platform files to copy into a Mu-Silicium tree
  Platforms/OnePlus/ace2Pkg/
  Resources/Configs/ace2.toml

core-patches/
  bootimg-v4-verify.patch   fixes Android boot v4 verification in UniXNU core

scripts/
  build-uefi-macos.sh   direct EDK2 build (bypasses stuart host extdeps)
  rebuild-boot.sh       payload + loader injection + PONGFAT + boot image
  pongfat.py            PONGFAT1 wrapper

docs/
  PROJECT_PROGRESS.md   detailed bring-up log and next steps
```

No Apple IPSW, kernelcache, platform seed, vendor firmware blob or built boot
image is committed. The UEFI base repository supplies vendor binaries.

## Reproduce

### 1. Base repositories

```sh
git clone https://github.com/UniXNU/UniXNU.git core
git clone https://github.com/UniXNU/uefi-sheng.git uefi-base
git clone https://github.com/UniXNU/DarwinBoot.git darwinboot
# in uefi-base, initialize the submodules it needs (Common/Mu, Mu_Basecore,
# Silicon/Silicium, Silicium-ACPI, ...)
```

`takasugl/uefi-udon` is the same-device reference UEFI tree; the overlay here is
based on `uefi-sheng` and was built against it.

### 2. Apply the Ace 2 overlay

```sh
cp -R uefi-overlay/. uefi-base/
```

This adds `Platforms/OnePlus/ace2Pkg` and `Resources/Configs/ace2.toml`.

### 3. Build the UEFI FD (macOS, no stuart host extdeps)

```sh
UEFI="$PWD/uefi-base" CORE="$PWD/core" DARWINBOOT="$PWD/darwinboot" \
  ./scripts/build-uefi-macos.sh
```

The FD is `uefi-base/Build/ace2Pkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`
(4 MiB). On Linux the normal `python3 build_uefi.py -d ace2` path also works.

### 4. Build `kernel.macho`

The XNU kernel is not committed. Build it from `device/` with its patch series
and `configs/liuqin_defconfig`, using the device repo's macOS CI workflow
(`.github/workflows/macos.yml`) or your own Xcode 15 runner. The tested kernel
SHA-256 is listed above.

### 5. Build payload and boot image

```sh
UEFI="$PWD/uefi-base" CORE="$PWD/core" \
  ./scripts/rebuild-boot.sh /path/to/kernel.macho <16-hex-platform-seed>
```

The script:

1. applies `core-patches/bootimg-v4-verify.patch` once;
2. builds the payload with `dram_size=0xC0000000` and
   `owned_memory_size=0x130000000`;
3. injects `UniXNU.efi` into `EFI/UniXNU/` of the payload FAT;
4. wraps it as PONGFAT1;
5. builds the Android boot v4 image.

### 6. Boot (never flash)

```sh
fastboot boot out/boot.img
```

Recovery: long-press power. No partition is modified by `fastboot boot`.

## Critical details learned

1. **Payload must contain `EFI/UniXNU/UniXNU.efi`.**
   Without it, `ShengBootMemoryDxe` reports `Image ... start failed: Not Found`
   and BDS prints `Failed to Find an Operating System!`.

2. **Low memory is not enough.**
   The stock low map leaves only ~51 MiB contiguous:
   `NO WINDOW 130000000 BIG RUN 312A000 @ F8000000`.
   Publish the high bank in `ShengBootMemoryDxe`:
   `0x840000000 + 0x140000000` (5 GiB).

3. **The ADT `dram-size` does not set the XNU managed window.**
   The device uses `dram_size = 0xC0000000`; the real managed memory is the
   DarwinBoot window from `owned_memory_size = 0x130000000` (4.75 GiB).

4. **The physmap padding patch is a no-op for this build.**
   The 4K non-`ARM_LARGE_MEMORY` path already had the 16 MiB PTOV padding.

5. **External EFI apps in the payload are blocked.**
   Loading `Ace2MemDiag.efi` from the menu returns `Access Denied`
   (`LoadImage` firmware policy). Diagnostics must live in the FV or inside the
   kernel.

6. **Panel/framebuffer args must be Ace 2's**
   `fb=0xb8000000,1240,2772,4960`, not the Xiaomi Pad 6 Pro geometry.

## Next steps

1. Use the upstream entry probe (`scripts/patch-xnu-entry-probe.py` in current
   UniXNU main) with `entry_probe_reset_delay` to determine whether MMU setup
   completes, or re-enable the kernel's stage bands.
2. Automate `UniXNU.efi` injection in the device repo instead of doing it in a
   shell post-step.
3. After stage 12/MMU is confirmed, add the physical-timer skip, trust cache,
   native UFS root and Data seed in that order.
4. Consider migrating the device repo to UniXNU format 2 once early boot is
   stable. There is no shared SM8475 SoC repo yet.

See `docs/PROJECT_PROGRESS.md` for the full chronological log.
