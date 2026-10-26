#!/usr/bin/env python3
"""Wrap a raw FAT payload image in the PONGFAT1 envelope Ace 2 UEFI expects.

Usage: pongfat.py payload.img payload.ramdisk
"""
import struct
import sys
import zlib
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    fat = Path(sys.argv[1]).read_bytes()
    if len(fat) < 512 or fat[510:512] != b"\x55\xaa":
        raise SystemExit("input is not a FAT image")
    header = bytearray(4096)
    struct.pack_into("<8sIIQII", header, 0, b"PONGFAT1", 1, 4096, len(fat), zlib.crc32(fat), 0)
    Path(sys.argv[2]).write_bytes(bytes(header) + fat)
    print(f"wrote {sys.argv[2]}: {len(fat) + 4096} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
