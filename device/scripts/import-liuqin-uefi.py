#!/usr/bin/env python3
"""Import the genuine liuqin UEFI binary modules and generate EDK II INF wrappers.

Reads the stock uefi.elf of the Xiaomi Pad 6 Pro (liuqin, SM8475) fastboot package,
walks every firmware volume, and writes one INF wrapper per AArch64 PE32/TE module
plus the raw files (uefiplat.cfg, panel XMLs, logo) that the platform needs.

Vendor bytes stay outside git: the output directory is Binaries/liuqin.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import uefi_firmware
from uefi_firmware import uefi as U

TYPES = {'DXE driver': 'DXE_DRIVER', 'UEFI application': 'UEFI_APPLICATION',
         'DXE core': 'DXE_CORE', 'SEC core': 'SEC', 'PEI core': 'PEI_CORE',
         'PEI module': 'PEIM', 'Combined SMM/DXE': 'DXE_SMM_DRIVER'}
# FFS file type -> EDK II MODULE_TYPE, used when the UI subtype is not conclusive
FFS_TYPE = {0x01: 'SEC', 0x02: 'PEIM', 0x03: 'DXE_DRIVER', 0x04: 'DXE_CORE',
            0x05: 'DXE_CORE', 0x06: 'PEIM', 0x07: 'DXE_DRIVER', 0x08: 'DXE_DRIVER',
            0x09: 'UEFI_APPLICATION', 0x0A: 'MM_STANDALONE', 0x0B: 'DXE_DRIVER',
            0x0C: 'SMM_CORE'}
SECTION_UI = 0x15
SECTION_PE32 = 0x10
SECTION_TE = 0x12
SECTION_DEPEX = 0x13
SECTION_RAW = 0x19
SECTION_FVIMAGE = 0x17
SECTION_GUID = 0x02


def kids(obj):
    for attr in ('objects', 'children', 'firmware_filesystems'):
        value = getattr(obj, attr, None)
        if isinstance(value, list) and value:
            return value
    return []


def walk(obj, entries, raws, order):
    for child in kids(obj):
        kind = type(child).__name__
        if kind == 'FirmwareVolume':
            child.process()
            walk(child, entries, raws, order)
        elif kind == 'FirmwareFileSystem':
            walk(child, entries, raws, order)
        elif kind == 'FirmwareFile':
            try:
                child.process()
            except Exception:
                pass
            record(child, entries, raws, order)
            for section in (getattr(child, 'sections', []) or []):
                if getattr(section, 'type', None) == SECTION_GUID:
                    walk(section, entries, raws, order)
        elif kind in ('GuidDefinedSection', 'CompressedSection',
                      'FirmwareFileSystemSection', 'EfiSection'):
            try:
                child.process()
            except Exception:
                pass
            walk(child, entries, raws, order)
        else:
            walk(child, entries, raws, order)


def record(ffs, entries, raws, order):
    ui = None
    sections = {}
    for section in (getattr(ffs, 'sections', []) or []):
        kind = getattr(section, 'type', None)
        data = getattr(section, 'data', None)
        if kind == SECTION_UI and data:
            ui = data.decode('utf-16-le', 'replace').rstrip('\x00')
        elif kind is not None and data is not None:
            sections.setdefault(kind, data)
    if not ui:
        return
    # 同一个模块可能同时出现在两个 FV 里（liuqin 的 IPCCDxe / GlinkDxe 就是这样）：
    # GUID 相同、字节相同就是同一个模块，只导一次。
    digest_any = hashlib.sha256(sections.get(SECTION_PE32) or sections.get(SECTION_TE) or b'').hexdigest()
    if (ffs.guid.hex(), digest_any) in SEEN:
        return
    SEEN.add((ffs.guid.hex(), digest_any))
    if SECTION_RAW in sections and SECTION_PE32 not in sections and SECTION_TE not in sections:
        raws.append({'ui': ui, 'guid': ffs.guid.hex(), 'bytes': len(sections[SECTION_RAW]),
                     'sha256': hashlib.sha256(sections[SECTION_RAW]).hexdigest(), 'data': sections[SECTION_RAW]})
        return
    code_kind = SECTION_PE32 if SECTION_PE32 in sections else SECTION_TE if SECTION_TE in sections else None
    if code_kind is None:
        return
    code = sections[code_kind]
    if code_kind == SECTION_PE32:
        pe = struct.unpack_from('<I', code, 0x3c)[0]
        if code[pe:pe + 4] != b'PE\0\0':
            raise SystemExit(f'{ui}: not a PE image')
        machine = struct.unpack_from('<H', code, pe + 4)[0]
    else:
        machine = struct.unpack_from('<H', code, 2)[0]
    if machine != 0xaa64:
        raise SystemExit(f'{ui}: not AArch64 (machine {machine:#x})')
    module_type = FFS_TYPE.get(ffs.type, 'DXE_DRIVER')
    CODES[hashlib.sha256(code).hexdigest()] = code
    entries.append({'ui': ui, 'guid': ffs.guid.hex(), 'ffs_type': ffs.type,
                    'module_type': module_type, 'binary': 'PE32' if code_kind == SECTION_PE32 else 'TE',
                    'bytes': len(code), 'sha256': hashlib.sha256(code).hexdigest(),
                    'depex': sections.get(SECTION_DEPEX),
                    'order': len(order)})
    order.append(ui)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uefi-file', required=True, help='stock uefi.elf of the device')
    parser.add_argument('--out', required=True, help='target Binaries/<device> directory')
    parser.add_argument('--version', default='unknown', help='firmware version string for the manifest')
    args = parser.parse_args()

    image = Path(args.uefi_file)
    data = image.read_bytes()
    base = data.find(b'_FVH')
    if base < 40:
        raise SystemExit('no firmware volume signature in the image')
    start = base - 40
    length = struct.unpack_from('<Q', data, start + 32)[0]
    volume = U.FirmwareVolume(data[start:start + length], length)
    volume.process()

    entries, raws, order = [], [], []
    walk(volume, entries, raws, order)

    out = Path(args.out)
    modules = out / 'Modules'
    rawdir = out / 'RawFiles'
    modules.mkdir(parents=True, exist_ok=True)
    rawdir.mkdir(parents=True, exist_ok=True)

    manifest = {'source': image.name, 'source_version': args.version,
                'source_sha256': hashlib.sha256(data).hexdigest(),
                'fv_offset': f'0x{start:X}', 'fv_size': f'0x{length:X}',
                'modules': [], 'raw_files': []}

    for entry in entries:
        name = entry['ui'].replace('/', '_')
        folder = modules / name
        folder.mkdir(exist_ok=True)
        code = CODES[entry['sha256']]
        (folder / f'{name}.efi').write_bytes(code)
        text = ('# Generated from the verified liuqin UEFI; vendor bytes stay outside git.\n'
                '[Defines]\n  INF_VERSION = 0x0001001B\n'
                f'  BASE_NAME = {name}\n  FILE_GUID = {entry["guid"]}\n'
                f'  MODULE_TYPE = {entry["module_type"]}\n  VERSION_STRING = 1.0\n\n'
                f'[Binaries.AARCH64]\n  {entry["binary"]}|{name}.efi|*\n')
        if entry['depex'] is not None:
            (folder / f'{name}.depex').write_bytes(entry['depex'])
            text += f'  DXE_DEPEX|{name}.depex|*\n'
        (folder / f'{name}.inf').write_text(text)
        manifest['modules'].append({
            'ui': entry['ui'], 'guid': entry['guid'],
            'ffs_type': f'0x{entry["ffs_type"]:02X}', 'module_type': entry['module_type'],
            'inf': f'Modules/{name}/{name}.inf', 'order': entry['order'],
            'bytes': entry['bytes'], 'sha256': entry['sha256'],
            'depex_sha256': hashlib.sha256(entry['depex']).hexdigest() if entry['depex'] else None})

    for raw in raws:
        name = raw['ui'].replace('\\', '/').split('/')[-1].replace(' ', '_')
        (rawdir / name).write_bytes(raw['data'])
        manifest['raw_files'].append({'file': f'RawFiles/{name}', 'ui': raw['ui'],
                                      'guid': raw['guid'], 'bytes': raw['bytes'],
                                      'sha256': raw['sha256']})

    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(f'{len(manifest["modules"])} AArch64 modules, {len(manifest["raw_files"])} raw files')


CODES = {}
SEEN = set()


if __name__ == '__main__':
    main()
