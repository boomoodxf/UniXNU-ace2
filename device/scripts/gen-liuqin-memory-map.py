#!/usr/bin/env python3
"""Generate liuqinPkg MemoryMapLib.c and ConfigurationMapLib.c from stock uefiplat.cfg.

The stock configuration is the authority: every row of [MemoryMap] and [RegisterMap]
becomes one EFI_MEMORY_REGION_DESCRIPTOR, and the numeric entries of [ConfigParameters]
become the configuration descriptor table. Single-core headless bring-up overrides are
applied on top, exactly like the sheng port does.
"""
import argparse
import csv
import io
from pathlib import Path

HOB_MAP = {'AddMem': 'AddMem', 'NoHob': 'NoHob', 'AddDev': 'AddDev',
           # MemoryMapLib has no dynamic-reservation type; reserve statically and say so.
           'AddDynamicMem': 'AddMem'}

BRINGUP_OVERRIDES = {
    'EarlyInitCoreCnt': 1,
    'NumActiveCores': 1,
    'EnableMultiThreading': 0,
    'EnableMultiCoreFvDecompression': 0,
    'EnableDisplayThread': 0,
    'EnableDisplayImageFv': 0,
    'EnableLogFsSyncInRetail': 0,
}


def rows(text, section, stop):
    body = text.split(section, 1)[1].split(stop, 1)[0]
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('0x'):
            continue
        fields = next(csv.reader(io.StringIO(line), skipinitialspace=True))
        label = fields[2].strip().strip('"')
        yield label, int(fields[0], 16), int(fields[1], 16), [f.strip() for f in fields[3:]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uefiplat', required=True)
    parser.add_argument('--platform-dir', required=True, help='target Platforms/<Vendor>/<device>Pkg')
    parser.add_argument('--source-version', default='unknown')
    args = parser.parse_args()

    text = Path(args.uefiplat).read_text()
    platform = Path(args.platform_dir)
    lib = platform / 'Library' / 'MemoryMapLib'
    cfg = platform / 'Library' / 'ConfigurationMapLib'
    lib.mkdir(parents=True, exist_ok=True)
    cfg.mkdir(parents=True, exist_ok=True)

    regions = []
    for label, base, size, attributes in rows(text, '[MemoryMap]', '[RegisterMap]'):
        regions.append((label, base, size, attributes))
    for label, base, size, attributes in rows(text, '[RegisterMap]', '[ConfigParameters]'):
        regions.append((label, base, size, attributes))

    # 厂商的 stock 表内部是有重叠的（例如 PIL Reserved 压住 Display Demura 的开头）。
    # 按表的顺序"先到先得"，后面的行只保留未被覆盖的部分，命名加 gapN —— 与 sheng 的
    # reconcile 步骤同样的处理，最后得到一张不重叠的描述符表。
    covered = []
    lines = []
    names = set()
    for label, base, size, attributes in regions:
        build = HOB_MAP[attributes[0]]
        pieces = [(base, base + size)]
        for cover_lo, cover_hi in covered:
            nxt = []
            for lo, hi in pieces:
                if cover_hi <= lo or cover_lo >= hi:
                    nxt.append((lo, hi))
                else:
                    if lo < cover_lo:
                        nxt.append((lo, cover_lo))
                    if cover_hi < hi:
                        nxt.append((cover_hi, hi))
            pieces = nxt
        covered.append((base, base + size))
        for index, (lo, hi) in enumerate(pieces):
            name = label if len(pieces) == 1 and (lo, hi) == (base, base + size) else f'{label} gap{index}'
            name = name.replace('"', '').replace(',', '')[:31]
            if name in names:
                raise SystemExit(f'duplicate region name: {name}')
            names.add(name)
            if lo % 4096 or (hi - lo) % 4096:
                raise SystemExit(f'region not 4K aligned: {name} {lo:#x} {hi - lo:#x}')
            lines.append(f'  {{"{name}", 0x{lo:08X}, 0x{hi - lo:08X}, {build}, '
                         f'{attributes[1]}, {attributes[2]}, {attributes[3]}, {attributes[4]}}},')

    if len(lines) >= 128:
        raise SystemExit('descriptor count exceeds the UINT8 counter')

    header = (f'// SPDX-License-Identifier: BSD-3-Clause\n'
              f'// Generated from the stock liuqin uefiplat.cfg ({args.source_version}).\n'
              f'// Every row of [MemoryMap] and [RegisterMap] is one descriptor; AddDynamicMem is\n'
              f'// reserved statically because MemoryMapLib has no dynamic-reservation type.\n'
              f'#include <Library/MemoryMapLib.h>\n\n'
              f'STATIC EFI_MEMORY_REGION_DESCRIPTOR gMemoryDescriptor[] = {{\n')
    footer = ('};\n\nVOID\nGetMemoryMap (\n  OUT EFI_MEMORY_REGION_DESCRIPTOR **MemoryDescriptor,\n'
              '  OUT UINT8                         *MemoryDescriptorCount)\n{\n'
              '  *MemoryDescriptor      = gMemoryDescriptor;\n'
              '  *MemoryDescriptorCount = ARRAY_SIZE (gMemoryDescriptor);\n}\n')
    (lib / 'MemoryMapLib.c').write_text(header + '\n'.join(lines) + '\n' + footer)

    # ---- configuration table ----
    params = text.split('[ConfigParameters]', 1)[1]
    numeric, strings = {}, {}
    for line in params.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = [p.strip() for p in line.split('=', 1)]
        if not key.replace('_', '').isalnum():
            continue
        try:
            numeric[key] = int(value, 0)
        except ValueError:
            strings[key] = value.strip('"')
    numeric.pop('ConfigParameterCount', None)
    numeric.update({k: v for k, v in BRINGUP_OVERRIDES.items() if k in numeric or True})
    entries = '\n'.join(f'  {{"{k}", 0x{v:X}}},' for k, v in sorted(numeric.items()))
    (cfg / 'ConfigurationMapLib.c').write_text(
        f'// SPDX-License-Identifier: BSD-3-Clause\n'
        f'// Generated from the stock liuqin uefiplat.cfg ({args.source_version}).\n'
        f'// Numeric [ConfigParameters] plus single-core headless bring-up overrides.\n'
        f'#include <Library/ConfigurationMapLib.h>\n\n'
        f'STATIC\nEFI_CONFIGURATION_ENTRY_DESCRIPTOR\ngConfigurationDescriptor[] = {{\n{entries}\n}};\n\n'
        f'VOID\nGetConfigurationMap (\n  OUT EFI_CONFIGURATION_ENTRY_DESCRIPTOR **ConfigurationDescriptor,\n'
        f'  OUT UINT8                               *ConfigurationDescriptorCount)\n{{\n'
        f'  *ConfigurationDescriptor      = gConfigurationDescriptor;\n'
        f'  *ConfigurationDescriptorCount = ARRAY_SIZE (gConfigurationDescriptor);\n}}\n')

    print(f'{len(lines)} memory descriptors, {len(numeric)} configuration entries')
    if strings:
        print('string parameters not representable (kept out):', ', '.join(sorted(strings)))


if __name__ == '__main__':
    main()
