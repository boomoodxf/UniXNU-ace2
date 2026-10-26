#!/usr/bin/env python3
"""Wrap a superfloppy FAT image into a one-partition MBR image.

mformat writes a FAT boot sector at LBA 0, which is fine for a Linux initrd but leaves
PartitionDxe with nothing to bind: no MBR, no GPT, so no child handle, so the FAT driver
is never offered the volume. This writes a normal MBR with a single type 0x0C partition
covering the FAT image, so the stock DiskIo -> PartitionDxe -> Fat chain reaches it.

usage: wrap-payload-mbr.py INPUT.img OUTPUT.img [--reserved-sectors N]
"""
import struct
import sys


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip())
        return 2
    source, target = argv[1], argv[2]
    reserved = 2048
    if '--reserved-sectors' in argv:
        reserved = int(argv[argv.index('--reserved-sectors') + 1])

    fat = open(source, 'rb').read()
    if len(fat) % 512:
        raise SystemExit('the FAT image is not a whole number of sectors')
    sectors = len(fat) // 512

    mbr = bytearray(reserved * 512)
    entry = 446
    mbr[entry + 0] = 0x00          # not bootable: nothing here boots, it is a data volume
    mbr[entry + 1:entry + 4] = bytes((0x00, 0x02, 0x00))     # CHS start (unused)
    mbr[entry + 4] = 0x0C          # FAT32 LBA
    mbr[entry + 5:entry + 8] = bytes((0xFE, 0xFF, 0xFF))     # CHS end (unused)
    struct.pack_into('<II', mbr, entry + 8, reserved, sectors)
    mbr[510:512] = b'\x55\xaa'

    with open(target, 'wb') as image:
        image.write(mbr)
        image.write(fat)
    print(f'{target}: MBR partition {reserved}+{sectors} sectors, {reserved + sectors} sectors total')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
