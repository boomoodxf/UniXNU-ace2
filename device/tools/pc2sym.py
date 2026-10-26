#!/usr/bin/env python3
"""Resolve an address in kernel.macho to a symbol (nm-like, no llvm needed)."""
import struct, sys

PATH = "/home/ubuntu/liuqin-gh/kernel.macho"


def symbols(path=PATH):
    d = open(path, "rb").read()
    magic, cputype, cpusub, ftype, ncmds, sizeofcmds, flags, _ = struct.unpack_from("<IiiIIIII", d, 0)
    assert magic == 0xfeedfacf, hex(magic)
    off = 32
    syms = []
    base = 0
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", d, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            name = d[off + 8:off + 24].rstrip(b"\0").decode()
            vmaddr, vmsize = struct.unpack_from("<QQ", d, off + 24)
            if name == "__TEXT":
                base = vmaddr
        if cmd == 0x2:  # LC_SYMTAB
            symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", d, off + 8)
            for i in range(nsyms):
                n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from("<IBBhQ", d, symoff + i * 16)
                if (n_type & 0x0e) == 0x0e and n_value:
                    s = d[stroff + n_strx:d.find(b"\0", stroff + n_strx)].decode("utf-8", "replace")
                    syms.append((n_value, s))
        off += cmdsize
    syms.sort()
    return syms, base


def resolve(addr):
    syms, _ = symbols()
    lo, hi = 0, len(syms) - 1
    best = None
    for a, s in syms:
        if a <= addr:
            best = (a, s)
        else:
            break
    return best


if __name__ == "__main__":
    syms, base = symbols()
    print("symbols", len(syms), "text base", hex(base))
    for arg in sys.argv[1:]:
        a = int(arg, 16)
        hit = None
        for sa, s in syms:
            if sa <= a:
                hit = (sa, s)
            else:
                break
        if hit:
            print("%#x -> %s + %#x" % (a, hit[1], a - hit[0]))
        else:
            print("%#x -> below the first symbol" % a)
