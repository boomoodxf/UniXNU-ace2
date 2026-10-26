#!/usr/bin/env python3
"""Rewrite the arm_vm_init.c section: bisecting stage bands before the TTBR0 switch.

Facts that drove this: arm_vm_init switches TTBR0 to an invalid table at
`set_mmu_ttb(invalid_ttep ...)`, so any marker that writes the framebuffer
through the identity mapping after that point faults. Stages 6 and 7 sat after
that line, so their absence proved nothing and their presence would have killed
the boot. They are replaced by bands 8..13 placed between arm_vm_init entry and
the switch, and the marker is extended to 16 bands.
"""
import re
from pathlib import Path

SRC = Path("/mnt/c/Users/ASUS/Desktop/unixnu-port/arm_vm_init.c")
DEBUG_SRC = Path("/mnt/c/Users/ASUS/Desktop/unixnu-port/liuqin_debug_stub.txt")
PATCH = Path.home() / "port/UniXNU-liuqin/patches/xnu/zzz-liuqin-usb-debug.patch"

src = SRC.read_text().split("\n")


def find(sub, start=0):
    for i in range(start, len(src)):
        if sub in src[i]:
            return i + 1
    raise SystemExit("anchor missing: %r" % sub)


def stage(n):
    return "\t{ extern void liuqin_stage(unsigned); liuqin_stage(%d); }" % n


# insertion points, each (anchor substring, stage number, trailing context lines)
plan = [
    ("vm_map_address_t dynamic_memory_begin;", 5, 1),   # arm_vm_init entered
    ("#endif", 8, 2),   # the guard that closes the unsupported-memory check
    ("boot_ttep = kvtophys((vm_offset_t)boot_tte);", 9, 2),
    ("init_ptpages(cpu_tte, gVirtBase, dynamic_memory_begin, TRUE", 10, 2),
    ("arm_vm_prot_init(args);", 11, 2),
    ("arm_vm_physmap_init(args);", 12, 2),
]

hunks = []
first = 0
i_panic = find('panic("Unsupported memory configuration %lx", mem_size);')
for anchor, n, after in plan:
    i = find(anchor, i_panic if n == 8 else first)
    first = i
    lo, hi = i - 3, i + after
    body = [" " + src[k - 1] for k in range(lo, i + 1)]
    body.append("+" + stage(n))
    body.append(" " + src[i])            # the anchor again? no: src[i] is line i+1
    # fix: lines after i
    body = [" " + src[k - 1] for k in range(lo, i + 1)] + ["+" + stage(n)]
    body += [" " + src[k - 1] for k in range(i + 1, hi + 1)]
    old = (i - lo + 1) + (hi - i)
    new = old + 1
    hunks.append("@@ -%d,%d +%d,%d @@" % (lo, old, lo, new))
    hunks += body

section = ["diff --git a/osfmk/arm64/arm_vm_init.c b/osfmk/arm64/arm_vm_init.c",
           "--- a/osfmk/arm64/arm_vm_init.c",
           "+++ b/osfmk/arm64/arm_vm_init.c"] + hunks

# ---- splice into the patch --------------------------------------------------
lines = PATCH.read_text().split("\n")
out = []
i = 0
replaced = False
while i < len(lines):
    if lines[i].startswith("diff --git"):
        start = i
        i += 1
        while i < len(lines) and not lines[i].startswith("diff --git"):
            i += 1
        sec = lines[start:i]
        if "a/osfmk/arm64/arm_vm_init.c" in sec[0]:
            out += section
            replaced = True
        else:
            out += sec
        continue
    out.append(lines[i])
    i += 1
assert replaced, "arm_vm_init section not found"

# ---- marker: 16 bands, 70 rows apart ---------------------------------------
txt = "\n".join(out)
old_fn = """+void
+liuqin_early_marker(unsigned band)
+{
+\tconst uint64_t base = 0xb8000000ULL, stride = 7200;
+\tuint64_t first;
+\tuint32_t color;
+
+\tif (band > 7) {
+\t\treturn;
+\t}
+\tfirst = 1200 + (uint64_t)band * 90;
+\tcolor = lq_stage_color[band];
+\tfor (uint64_t row = first; row < first + 50; row++) {"""
new_fn = """+void
+liuqin_early_marker(unsigned band)
+{
+\tconst uint64_t base = 0xb8000000ULL, stride = 7200;
+\tuint64_t first;
+\tuint32_t color;
+
+\t/* Only valid while TTBR0 still holds the identity table: arm_vm_init
+\t * replaces it with an invalid one before pmap_bootstrap, so nothing below
+\t * that point may use this. */
+\tif (band > 15) {
+\t\treturn;
+\t}
+\tfirst = 1200 + (uint64_t)band * 70;
+\tcolor = lq_stage_color[band & 7];
+\tfor (uint64_t row = first; row < first + 44; row++) {"""
if old_fn in txt:
    txt = txt.replace(old_fn, new_fn)
elif "if (band > 15)" not in txt:
    raise SystemExit("marker body not recognised")
else:
    print("marker already carries 16 bands")
txt = txt.replace("+\\tlq_dcache_flush(base + first * stride, 50 * stride);",
                  "+\\tlq_dcache_flush(base + first * stride, 44 * stride);")

# ---- recount every hunk header ---------------------------------------------
lines = txt.split("\n")
res = []
i = 0
while i < len(lines):
    l = lines[i]
    if l.startswith("@@"):
        head = l.split("@@")[1].strip().split()
        os_ = int(head[0].lstrip("+-").split(",")[0])
        ns_ = int(head[1].lstrip("+-").split(",")[0])
        o = n = 0
        j = i + 1
        while j < len(lines) and not lines[j].startswith(("@@", "diff --git")):
            c = lines[j][:1]
            if c == " ":
                o += 1; n += 1
            elif c == "-":
                o += 1
            elif c == "+":
                n += 1
            j += 1
        res.append("@@ -%d,%d +%d,%d @@" % (os_, o, ns_, n))
        i += 1
        continue
    res.append(l)
    i += 1
while res and res[-1] == "":
    res.pop()
PATCH.write_text("\n".join(res) + "\n", newline="\n")
print("arm_vm_init section rebuilt, %d hunks, patch lines %d" % (len(plan), len(res)))
