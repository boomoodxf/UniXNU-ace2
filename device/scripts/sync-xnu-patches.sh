#!/bin/sh
# Re-sync the device patches/xnu module from the base UniXNU checkout.
# Device repositories override module directories, so the whole base set must be
# present here next to our own patch. Run after updating the base repository.
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
base="${1:-$here/../UniXNU}/patches/xnu"
test -d "$base" || { echo "base patches not found: $base" >&2; exit 1; }
ours="$here/patches/xnu/zzz-liuqin-usb-debug.patch"
test -f "$ours" || { echo "missing $ours" >&2; exit 1; }
tmp=$(mktemp -d)
cp "$ours" "$tmp/"
rm -f "$here"/patches/xnu/*.patch
cp "$base"/*.patch "$here/patches/xnu/"
cp "$tmp"/zzz-liuqin-usb-debug.patch "$here/patches/xnu/"
rm -rf "$tmp"
echo "synced $(ls "$here"/patches/xnu/*.patch | wc -l) patches from $base"
