#!/usr/bin/env python3
"""Add post-TTBR0-switch markers plus a big bsd_init band.

arm_vm_init replaces TTBR0 with an invalid table, so fb writes through the
identity mapping stop working. Before that switch we now install one 2 MiB block
that maps the splash framebuffer into an unused slot of the kernel window and
hand its KVA to the marker, which drops it again right after pmap_bootstrap.
"""
from pathlib import Path

SRC = Path("/mnt/c/Users/ASUS/Desktop/unixnu-port/arm_vm_init.c")
PATCH = Path.home() / "port/UniXNU-liuqin/patches/xnu/zzz-liuqin-usb-debug.patch"
src = SRC.read_text().split("\n")


def find(sub, start=0):
    for i in range(start, len(src)):
        if sub in src[i]:
            return i + 1
    raise SystemExit("anchor missing: %r" % sub)


def stage(n):
    return "\t{ extern void liuqin_stage(unsigned); liuqin_stage(%d); }" % n


bind_block = [
    "\t/* liuqin: map the splash framebuffer into an unused slot of the kernel */",
    "\t/* window so the stage markers survive the TTBR0 switch below. The slot */",
    "\t/* covers physical memory nothing touches yet, and the mapping is dropped */",
    "\t/* again straight after pmap_bootstrap. */",
    "\t{",
    "\t\textern void liuqin_late_bind(uint64_t);",
    "\t\tuint64_t fbva = (gVirtBase + 0x0F000000ULL) & ~0x1FFFFFULL;",
    "\t\ttt_entry_t *l1e = cpu_tte + ((fbva & ARM_TT_L1_INDEX_MASK) >> ARM_TT_L1_SHIFT);",
    "\t\tif ((*l1e & 3) == 3) {",
    "\t\t\ttt_entry_t *l2e = (tt_entry_t *)phystokv(*l1e & ARM_TTE_TABLE_MASK)",
    "\t\t\t    + ((fbva & ARM_TT_L2_INDEX_MASK) >> ARM_TT_L2_SHIFT);",
    "\t\t\t*l2e = (0xb8000000ULL & ARM_TTE_BLOCK_L2_MASK) | ARM_TTE_BOOT_BLOCK;",
    "\t\t\tflush_mmu_tlb();",
    "\t\t\tliuqin_late_bind(fbva);",
    "\t\t}",
    "\t}",
]

# (anchor, insert_before, lines, trailing context)
plan = [
    ("vm_map_address_t dynamic_memory_begin;", False, [stage(5)], 1),
    ("#endif", False, [stage(8)], 2),
    ("boot_ttep = kvtophys((vm_offset_t)boot_tte);", False, [stage(9)], 2),
    ("init_ptpages(cpu_tte, gVirtBase, dynamic_memory_begin, TRUE", False, [stage(10)], 2),
    ("arm_vm_prot_init(args);", False, [stage(11)], 2),
    ("arm_vm_physmap_init(args);", False, bind_block + [stage(12)], 2),
    ("kva_active = TRUE;", False, [stage(13)], 2),
    ("sane_size = mem_size - (avail_start - gPhysBase);", True, [stage(14)], 0),
    ("pmap_bootstrap(dynamic_memory_begin);", True, [stage(15)], 0,
     ["\t{ extern void liuqin_late_unbind(void); liuqin_late_unbind(); }"]),
]

i_panic = find('panic("Unsupported memory configuration %lx", mem_size);')
hunks = []
first = 0
for entry in plan:
    anchor, before, lines, after = entry[:4]
    tail = entry[4] if len(entry) > 4 else []
    i = find(anchor, i_panic if anchor == "#endif" else first)
    first = i
    lo = i - 3
    hi = i + after
    body = []
    if before:
        body += [" " + src[k - 1] for k in range(lo, i)]
        body += ["+" + x for x in lines]
        body += [" " + src[i - 1]]
        body += ["+" + x for x in tail]
        body += [" " + src[k - 1] for k in range(i + 1, hi + 1)]
        old = (i - lo) + 1 + (hi - i)
    else:
        body += [" " + src[k - 1] for k in range(lo, i + 1)]
        body += ["+" + x for x in lines]
        body += ["+" + x for x in tail]
        body += [" " + src[k - 1] for k in range(i + 1, hi + 1)]
        old = (i - lo + 1) + (hi - i)
    new = old + len(lines) + len(tail)
    hunks.append("@@ -%d,%d +%d,%d @@" % (lo, old, lo, new))
    hunks += body

section = ["diff --git a/osfmk/arm64/arm_vm_init.c b/osfmk/arm64/arm_vm_init.c",
           "--- a/osfmk/arm64/arm_vm_init.c",
           "+++ b/osfmk/arm64/arm_vm_init.c"] + hunks

lines = PATCH.read_text().split("\n")
out = []
i = 0
done = False
while i < len(lines):
    if lines[i].startswith("diff --git"):
        start = i
        i += 1
        while i < len(lines) and not lines[i].startswith("diff --git"):
            i += 1
        sec = lines[start:i]
        if "a/osfmk/arm64/arm_vm_init.c" in sec[0]:
            out += section
            done = True
        else:
            out += sec
        continue
    out.append(lines[i])
    i += 1
assert done
txt = "\n".join(out)

# ---- marker: late-bound framebuffer, plus a big band helper ------------------
old = """+static uint32_t *lq_fb;
+static uint32_t lq_fb_width, lq_fb_stride_px;"""
new = """+static uint32_t *lq_fb;
+static uint32_t *lq_fb_late;
+static uint32_t lq_fb_width, lq_fb_stride_px;"""
assert old in txt
txt = txt.replace(old, new)

old = """+\t\tvolatile uint32_t *line = (volatile uint32_t *)(base + row * stride);"""
new = """+\t\tvolatile uint32_t *line = lq_fb_late ? (lq_fb_late + row * 1800) :
+\t\t    (volatile uint32_t *)(base + row * stride);"""
assert old in txt, "marker line"
txt = txt.replace(old, new)

helper = """+void
+liuqin_late_bind(uint64_t va)
+{
+\tlq_fb_late = va ? (uint32_t *)(vm_offset_t)va : 0;
+}
+
+void
+liuqin_late_unbind(void)
+{
+\tlq_fb_late = 0;
+}
+
+/* One unmistakable block, used for milestones reached after pmap_bootstrap
+ * (the per-stage bands need the identity mapping, this needs only lq_fb). */
+void
+liuqin_fb_bigband(unsigned first, unsigned height, uint32_t color)
+{
+\tif (!lq_fb || first + height > 2880) {
+\t\treturn;
+\t}
+\tfor (unsigned row = first; row < first + height; row++) {
+\t\tuint32_t *line = lq_fb + (uint64_t)row * lq_fb_stride_px;
+\t\tfor (unsigned x = 0; x < lq_fb_width; x++) {
+\t\t\tline[x] = color;
+\t\t}
+\t}
+\t__asm__ volatile("dsb sy" ::: "memory");
+}
+
+static const uint32_t lq_stage_color[8] = {"""
old_color = """+static const uint32_t lq_stage_color[8] = {"""
assert old_color in txt
txt = txt.replace(old_color, helper, 1)

# ---- bsd_init signal: a big magenta block at the bottom ----------------------
old = """+\t\tliuqin_fb_band(0, 0xff00ffffu);"""
new = """+\t\tliuqin_fb_band(0, 0xff00ffffu);
+\t\t{ extern void liuqin_fb_bigband(unsigned, unsigned, uint32_t);
+\t\t  liuqin_fb_bigband(2400, 240, 0xffff00ffu); }"""
if old in txt:
    txt = txt.replace(old, new)
else:
    print("WARNING: bsd_init band anchor not found")

# ---- recount ---------------------------------------------------------------
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
print("rebuilt: %d hunks in arm_vm_init.c, patch lines %d" % (len(plan), len(res)))
