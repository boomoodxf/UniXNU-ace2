#!/usr/bin/env bash
# Rebuild payload + boot image from an already-built kernel.macho and UEFI FD.
# Usage: rebuild-boot.sh KERNEL.macho UNIQUE_CHIP_ID_HEX
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CORE=${CORE:-"$ROOT/../UniXNU"}
UEFI=${UEFI:-"$ROOT/../uefi-base"}
OUT=${OUT:-"$ROOT/out"}
PYTHON=${PYTHON:-python3.13}
KERNEL=${1:-${KERNEL:-}}
CHIP=${2:-${UNIXNU_UNIQUE_CHIP_ID:-}}

[[ -f "$KERNEL" ]] || { echo "usage: $0 KERNEL.macho UNIQUE_CHIP_ID_HEX" >&2; exit 2; }
[[ -n "$CHIP" ]] || { echo "unique chip id is required" >&2; exit 2; }
[[ -f "$UEFI/Build/ace2Pkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd" ]] || {
  echo "build the UEFI FD first (scripts/build-uefi-macos.sh)" >&2; exit 1;
}

# Android boot v4 verification fix for the core build driver.
PATCH="$ROOT/core-patches/bootimg-v4-verify.patch"
if ! git -C "$CORE" apply --reverse --check "$PATCH" >/dev/null 2>&1; then
  git -C "$CORE" apply --check "$PATCH"
  git -C "$CORE" apply "$PATCH"
  echo "applied $PATCH to $CORE"
fi

mkdir -p "$OUT"
"$PYTHON" "$CORE/unixnu" build payload \
  -D "$ROOT/device" \
  --kernel "$KERNEL" \
  --unique-chip-id "$CHIP" \
  --out "$OUT"

PAYLOAD="$OUT/liuqin/payload/payload.img"
LOADER="$UEFI/Platforms/OnePlus/ace2Pkg/Ramdisk/unixnu.efi"
[[ -f "$PAYLOAD" ]] || { echo "payload not found: $PAYLOAD" >&2; exit 1; }
[[ -f "$LOADER" ]] || { echo "loader not found: $LOADER" >&2; exit 1; }

# The Ace 2 UEFI driver loads \EFI\UniXNU\UniXNU.efi from the payload volume.
mcopy -o -i "$PAYLOAD" -Q "$LOADER" ::/EFI/UniXNU/UniXNU.efi
"$PYTHON" "$ROOT/scripts/pongfat.py" "$PAYLOAD" "$OUT/payload.ramdisk"

"$PYTHON" "$CORE/unixnu" bootimg \
  -D "$ROOT/device" \
  --uefi "$UEFI" \
  --fd "$UEFI/Build/ace2Pkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd" \
  --dtb "$UEFI/Platforms/OnePlus/ace2Pkg/FdtBlob/sm8475-oneplus-ace2.dtb" \
  --ramdisk "$OUT/payload.ramdisk" \
  --out "$OUT" \
  -o "$OUT/boot.img"

echo "boot image: $OUT/boot.img"
echo "fastboot boot $OUT/boot.img   # never flash"
