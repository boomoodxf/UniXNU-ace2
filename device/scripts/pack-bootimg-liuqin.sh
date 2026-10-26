#!/usr/bin/env bash
# kernel.macho -> payload -> payload-mbr -> boot.img （WSL 或 Mac 都能跑，不需要 edk2）
# 用法: scripts/pack-bootimg-liuqin.sh [kernel.macho]
#   默认内核 out/liuqin/kernel/kernel.macho（GitHub Actions 产物解压后放到这个位置）
#   固件件默认取 E:\unixnu-mac 里的 prebuilt，可用 UEFI_MIN / UEFI_FD / CAPE_DTB 覆盖
set -euo pipefail
DEV="$(cd "$(dirname "$0")/.." && pwd)"
UNIXNU="${UNIXNU:-$(cd "$DEV/.." && pwd)/UniXNU}"
BUNDLE="${BUNDLE:-/mnt/e/unixnu-mac}"
UEFI_MIN="${UEFI_MIN:-$BUNDLE/uefi-liuqin-min}"
UEFI_FD="${UEFI_FD:-$BUNDLE/prebuilt/SILICIUM_UEFI.fd}"
CAPE_DTB="${CAPE_DTB:-$BUNDLE/liuqin-cape.dtb}"
CHIP="${CHIP:-0x84750A0B0C0D0001}"

cd "$UNIXNU"
KERNEL="${1:-$UNIXNU/out/liuqin/kernel/kernel.macho}"
[ -f "$KERNEL" ] || { echo "找不到内核：$KERNEL" >&2; exit 1; }
for f in "$UEFI_MIN" "$UEFI_FD" "$CAPE_DTB"; do
  [ -e "$f" ] || { echo "缺文件：$f（用 UEFI_MIN/UEFI_FD/CAPE_DTB 指定）" >&2; exit 1; }
done
if ! command -v llvm-objcopy >/dev/null; then
  for d in /usr/lib/llvm-*/bin /opt/homebrew/opt/llvm/bin /usr/local/opt/llvm/bin; do
    [ -x "$d/llvm-objcopy" ] && PATH="$d:$PATH" && break
  done
fi
command -v llvm-objcopy >/dev/null || { echo "缺 llvm-objcopy（apt install llvm / brew install llvm）" >&2; exit 1; }

echo "== tree"
./unixnu tree -D "$DEV" >/dev/null

echo "== payload（内核 + ADT + 启动参数，64 MiB ESP）"
./unixnu build payload --kernel "$KERNEL" --unique-chip-id "$CHIP" -D "$DEV"

echo "== MBR 包装（PartitionDxe 才认得出分区）"
python3 "$DEV/scripts/wrap-payload-mbr.py" out/liuqin/payload/payload.img "$UNIXNU/out/liuqin/payload/payload-mbr.img"

echo "== bootimg"
./unixnu bootimg --uefi "$UEFI_MIN" --fd "$UEFI_FD" --dtb "$CAPE_DTB" \
                 --ramdisk "$UNIXNU/out/liuqin/payload/payload-mbr.img" -D "$DEV"

echo
ls -la out/liuqin/boot/
echo "刷机：fastboot boot $UNIXNU/out/liuqin/boot/boot.img"
