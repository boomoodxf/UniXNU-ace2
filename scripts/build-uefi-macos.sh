#!/usr/bin/env bash
# Build the Ace 2 UEFI FD on macOS without stuart's host-specific Mu-Basetools
# dependency. The same EDK2 build produced the FD used by boot-highmem.img.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
UEFI=${UEFI:-"$ROOT/../uefi-base"}
CORE=${CORE:-"$ROOT/../UniXNU"}
DARWINBOOT=${DARWINBOOT:-"$CORE/drivers/DarwinBoot"}
PYTHON=${PYTHON:-python3.13}
JOBS=${JOBS:-8}

[[ -d "$UEFI/Mu_Basecore/BaseTools" ]] || {
  echo "UEFI=$UEFI is not a Mu-Silicium/uefi-sheng checkout with Mu_Basecore" >&2
  exit 1
}
[[ -d "$UEFI/Platforms/OnePlus/ace2Pkg" ]] || {
  echo "copy uefi-overlay/ into $UEFI first" >&2
  exit 1
}
[[ -d "$DARWINBOOT/DarwinBootPkg" ]] || {
  echo "DARWINBOOT=$DARWINBOOT is not a DarwinBoot checkout" >&2
  exit 1
}
[[ -d "$CORE/package/UniXNUPkg" ]] || {
  echo "CORE=$CORE has no package/UniXNUPkg" >&2
  exit 1
}

export WORKSPACE="$UEFI"
export EDK_TOOLS_PATH="$UEFI/Mu_Basecore/BaseTools"
export PYTHON_COMMAND="$PYTHON"
export PACKAGES_PATH="$UEFI:$UEFI/Platforms/OnePlus:$UEFI/Platforms/Nothing:$UEFI/Silicon/Qualcomm:$UEFI/Silicon/Silicium:$UEFI/Silicium-ACPI:$UEFI/Silicium-ACPI/Platforms/OnePlus:$UEFI/Silicium-ACPI/Platforms/Nothing:$UEFI/Silicium-ACPI/Silicon/Qualcomm:$UEFI/Common/Mu:$UEFI/Common/Mu_OEM_Sample:$UEFI/Mu_Basecore:$DARWINBOOT:$CORE/package"
export PATH="$UEFI/Mu_Basecore/BaseTools/BinWrappers/PosixLike:/opt/homebrew/opt/llvm/bin:$PATH"

cd "$UEFI"
./Mu_Basecore/BaseTools/BinWrappers/PosixLike/build \
  -p Platforms/OnePlus/ace2Pkg/ace2.dsc \
  -a AARCH64 -t CLANGPDB -b DEBUG -n "$JOBS" \
  -D FD_BASE=0xA7100000 -D FD_SIZE=0x400000 -D FD_BLOCKS=0x400 \
  -D ENABLE_SECUREBOOT=0 -D DEVICE_MODEL=0

echo "FD: $UEFI/Build/ace2Pkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd"
