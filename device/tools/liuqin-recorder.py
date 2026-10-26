#!/usr/bin/env python3
"""Point DarwinBoot at the kernel's lq_rec[] for the current kernel build.

The boot black box lives in an ordinary kernel global, so its address moves with
every kernel build. DarwinBoot reads it by physical address, which is

    load address + (lq_rec vmaddr - kernel base)

so patch the offset into DarwinBoot.c and rebuild the firmware image.

    python3 tools/liuqin-recorder.py --kernel ~/liuqin-gh/kernel.macho         --darwinboot ~/port/UniXNU/drivers/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c
"""
import argparse
import pathlib
import re
import struct
import sys

SYMBOL = "_lq_rec"
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2


def parse(path):
    data = pathlib.Path(path).read_bytes()
    if struct.unpack_from("<I", data, 0)[0] != 0xFEEDFACF:
        raise SystemExit("%s: not a 64-bit Mach-O" % path)
    ncmds = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    base = None
    symtab = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, offset)
        if cmd == LC_SEGMENT_64:
            vmaddr, vmsize = struct.unpack_from("<2Q", data, offset + 24)
            if vmsize:
                base = vmaddr if base is None else min(base, vmaddr)
        elif cmd == LC_SYMTAB:
            symtab = struct.unpack_from("<4I", data, offset + 8)
        offset += size
    if base is None or symtab is None:
        raise SystemExit("no segments or no symbol table")
    symoff, nsyms, stroff, _ = symtab
    found = None
    for index in range(nsyms):
        strx, ntype, _sect, _desc, value = struct.unpack_from("<IBBHQ", data, symoff + index * 16)
        end = data.index(b"\0", stroff + strx)
        if data[stroff + strx:end].decode("utf-8", "replace") != SYMBOL:
            continue
        # N_SECT (0x0e) in the upper nibble of N_TYPE; N_UNDF records have value 0.
        if value and (ntype // 2) % 8 == 7:
            found = value
        # The table also carries an undefined record (N_UNDF, value 0) for the
        # symbol; only the N_SECT entry with a real address is the definition.
            found = value
    if found is None:
        raise SystemExit("%s has no defined address in the symbol table" % SYMBOL)
    return base, found
    raise SystemExit("%s not found in the symbol table" % SYMBOL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--darwinboot", required=True)
    args = ap.parse_args()

    base, value = parse(args.kernel)
    offset = value - base
    if offset <= 0 or offset % 0x4000:
        print("warning: offset 0x%x is not 16 KiB aligned" % offset)
    target = pathlib.Path(args.darwinboot)
    text = target.read_text()
    new, count = re.subn(r"#define LQ_RECORDER_OFFSET[^\n]*",
                         "#define LQ_RECORDER_OFFSET 0x%x" % offset, text, count=1)
    if count != 1:
        raise SystemExit("LQ_RECORDER_OFFSET not found in %s" % target)
    target.write_text(new)
    print("lq_rec vmaddr 0x%x base 0x%x offset 0x%x -> %s" % (value, base, offset, target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
