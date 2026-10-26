#!/usr/bin/env python3
"""liuqin firmware preflight: verify the vendor inputs and the board intervals.

Runs before the EDK II build (board.toml [firmware] preflight). Everything checked here
comes from the stock liuqin firmware: Binaries/liuqin/manifest.json is the record of what
was imported from uefi.elf, and MemoryMapLib.c is generated from uefiplat.cfg.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

PLATFORM_RELATIVE = 'Platforms/Xiaomi/liuqinPkg'


def find_uefi():
    env = os.environ.get('UNIXNU_UEFI')
    candidates = [env] if env else []
    here = Path(__file__).resolve()
    # 脚本被复制到 out/<board>/tree/scripts/ 里运行，uefi-liuqin 可能在上面好几层。
    bases = [Path.cwd(), here.parent] + list(here.parents)[:7]
    for base in bases:
        for depth in range(4):
            candidates.append(str(base.parents[depth] / 'uefi-liuqin') if depth < len(base.parents) else '')
            candidates.append(str(base.parents[depth] / 'UniXNU' / 'uefi-liuqin') if depth < len(base.parents) else '')
    for candidate in candidates:
        if candidate and (Path(candidate) / PLATFORM_RELATIVE).is_dir():
            return Path(candidate).resolve()
    return None


def descriptors(source):
    pattern = re.compile(r'\{"([^"]+)"\s*,\s*(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+),([^}]+)\}')
    return [(m[1], int(m[2], 16), int(m[3], 16), m[4]) for m in pattern.finditer(source)]


def main():
    errors, notes = [], []
    uefi = find_uefi()
    if uefi is None:
        print('liuqin preflight: no uefi-liuqin checkout found (pass --uefi / UNIXNU_UEFI); '
              'skipping the vendor input check')
        return 0
    platform = uefi / PLATFORM_RELATIVE
    binaries = uefi / 'Binaries' / 'liuqin'
    manifest_path = binaries / 'manifest.json'
    if not manifest_path.is_file():
        errors.append(f'missing {manifest_path}; run scripts/import-liuqin-uefi.py')
    else:
        manifest = json.loads(manifest_path.read_text())
        for module in manifest['modules']:
            path = binaries / f"Modules/{module['ui']}/{module['ui']}.efi"
            if not path.is_file():
                errors.append(f'missing module {path.name}')
            elif hashlib.sha256(path.read_bytes()).hexdigest() != module['sha256']:
                errors.append(f'module bytes changed: {module["ui"]}')
        for raw in manifest['raw_files']:
            path = binaries / raw['file']
            if not path.is_file():
                errors.append(f'missing raw file {path.name}')
            elif hashlib.sha256(path.read_bytes()).hexdigest() != raw['sha256']:
                errors.append(f'raw bytes changed: {raw["file"]}')
        notes.append(f"{len(manifest['modules'])} modules, {len(manifest['raw_files'])} raw files verified")

    plat = binaries / 'RawFiles/uefiplat.cfg'
    if not plat.is_file():
        errors.append('missing uefiplat.cfg: the memory map cannot be traced to the stock firmware')
    else:
        window = re.search(r'0x([0-9A-Fa-f]+),\s*0x([0-9A-Fa-f]+),\s*"UEFI FD"', plat.read_text())
        if not window:
            errors.append('uefiplat.cfg has no "UEFI FD" row')
        else:
            base, size = int(window.group(1), 16), int(window.group(2), 16)
            notes.append(f'stock UEFI FD window {base:#x} + {size:#x}')
            config = uefi / 'Resources/Configs/liuqin.toml'
            if config.is_file():
                import tomllib
                fd = tomllib.loads(config.read_text())['uefi_fd']
                fd_base, fd_size = int(fd['base'], 0) if isinstance(fd['base'], str) else fd['base'], \
                                   int(fd['size'], 0) if isinstance(fd['size'], str) else fd['size']
                if not (base <= fd_base and fd_base + fd_size <= base + size):
                    errors.append(f'uefi_fd {fd_base:#x}+{fd_size:#x} leaves the stock window '
                                  f'{base:#x}+{size:#x}')

    panel = binaries / 'RawFiles/Panel_M81_42_02_0b_dualdsi_dsc_lcd_video.xml'
    if not panel.is_file():
        errors.append('missing the M81_42_02_0b panel XML')
    else:
        text = panel.read_text()
        width = re.search(r'<HorizontalActive>(\d+)</HorizontalActive>', text)
        height = re.search(r'<VerticalActive>(\d+)</VerticalActive>', text)
        if not width or not height or (width.group(1), height.group(1)) != ('1800', '2880'):
            errors.append('panel XML is not 1800x2880; it is not the liuqin panel')

    source = (platform / 'Library/MemoryMapLib/MemoryMapLib.c').read_text()
    rows = descriptors(source)
    if not rows:
        errors.append('MemoryMapLib.c has no descriptors')
    if len(rows) >= 128:
        errors.append(f'{len(rows)} descriptors exceed the UINT8 counter')
    for name, base, size, _ in rows:
        if not size or base % 4096 or size % 4096:
            errors.append(f'descriptor not 4K aligned: {name} {base:#x} {size:#x}')
    for index, (name, base, size, _) in enumerate(rows):
        for other, other_base, other_size, _ in rows[index + 1:]:
            if max(base, other_base) < min(base + size, other_base + other_size):
                errors.append(f'overlapping descriptors: {name} / {other}')
    notes.append(f'{len(rows)} memory descriptors')

    for note in notes:
        print(f'liuqin preflight: {note}')
    if errors:
        for error in errors:
            print(f'liuqin preflight: FAIL {error}', file=sys.stderr)
        return 1
    print('liuqin preflight: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
