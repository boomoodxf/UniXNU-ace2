#!/bin/sh
# Host-side checks for the liuqin USB debug port. No kernel, no Mac needed.
# The driver headers live in the patched XNU work tree, so point XNU_TREE at it:
#   XNU_TREE=~/port/UniXNU/out/liuqin/tree/.cache/xnu-work tests/run-host-test.sh
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
tree="${XNU_TREE:-$here/../UniXNU/out/liuqin/tree/.cache/xnu-work}"
dev="$tree/bsd/dev"
test -f "$dev/liuqin_usb_protocol.h" || {
	echo "no patched xnu tree at $dev (set XNU_TREE to one where zzz-liuqin-usb-debug.patch is applied)" >&2
	exit 1
}
cc="${CC:-cc}"
"$cc" -DLIUQIN_HOST_TEST -I "$dev" -Wall -Wextra -o /tmp/liuqin-usb-host-test tests/liuqin_usb_host_test.c
/tmp/liuqin-usb-host-test
