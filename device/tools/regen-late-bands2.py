#!/usr/bin/env python3
"""Insert the late-stage markers into arm_vm_init.c and let git write the hunk.

Line numbers from the pristine xnu file drift by ~25 lines once the other
patches are applied, which made hand-built hunk headers land in the wrong place.
So build the file the way the CI sees it (pristine + non-apple-cache-monitor),
insert by content, and take the diff git produces.
"""
import subprocess
import sys
from pathlib import Path

SIM = Path("/tmp/sim3")
FILE = SIM / "osfmk/arm64/arm_vm_init.c"
PRISTINE = Path("/mnt/c/Users/ASUS/Desktop/unixnu-port/arm_vm_init.c")
CM = Path.home() / "port/UniXNU-liuqin/patches/xnu/non-apple-cache-monitor.patch"
PATCH = Path.home() / "port/UniXNU-liuqin/patches/xnu/zzz-liuqin-usb-debug.patch"


def run(*cmd, **kw):
    return subprocess.run(cmd, cwd=str(SIM), capture_output=True, text=True, **kw)


# pre-image = pristine + the one other patch that touches this file
SIM.mkdir(parents=True, exist_ok=True)
(SIM / "osfmk/arm64").mkdir(parents=True, exist_ok=True)
if not (SIM / ".git").exists():
    run("git", "init", "-q", ".")
FILE = SIM / "osfmk/arm64/arm_vm_init.c"
FILE.write_text(PRISTINE.read_text(), newline="\n")
lines = CM.read_text().split("\n")
sec, on = [], False
for l in lines:
    if l.startswith("diff --git"):
        on = "arm_vm_init.c" in l
        if on:
            sec.append(l)
        continue
    if on:
        sec.append(l)
cmsec = Path("/tmp/cmsec2.patch")
cmsec.write_text("\n".join(sec) + "\n", newline="\n")
r = run("git", "apply", str(cmsec))
if r.returncode:
    sys.exit("cache-monitor hunk did not apply: " + r.stderr)
# commit the pre-image so git diff below shows only our insertions
run("git", "add", "osfmk/arm64/arm_vm_init.c")
run("git", "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "pre-image")

text = FILE.read_text()
src = text.split("\n")


def insert_after(anchor, block, before=False, occurrence=0):
    hits = [i for i, l in enumerate(src) if anchor in l]
    if len(hits) <= occurrence:
        sys.exit("anchor not found: %r" % anchor)
    i = hits[occurrence]
    if before:
        src[i:i] = block
    else:
        src[i + 1:i + 1] = block


def stage(n):
    return "\t{ extern void liuqin_stage(unsigned); liuqin_stage(%d); }" % n


bind = []

# do the edits bottom-up so earlier anchors keep their indices
# pmap_bootstrap now runs with TTBR0 still pointing at the V=P table
insert_after("pmap_bootstrap(dynamic_memory_begin);", [stage(15)], before=True)
insert_after("pmap_bootstrap(dynamic_memory_begin);", [stage(7)])
insert_after("sane_size = mem_size - (avail_start - gPhysBase);", [stage(14)], before=True)
insert_after("kva_active = TRUE;", [stage(13)])
insert_after("arm_vm_physmap_init(args);", [stage(12)])
# keep the boot V=P table in TTBR0 instead of the invalid one: the panel stays
# writable, so stage bands and kprintf/panic text keep working after the switch
src = [l.replace("set_mmu_ttb(invalid_ttep & TTBR_BADDR_MASK);",
                 "set_mmu_ttb(boot_ttep & TTBR_BADDR_MASK);"
                 "\t/* liuqin: keep the V=P map so the panel stays writable */")
       if "set_mmu_ttb(invalid_ttep & TTBR_BADDR_MASK);" in l else l for l in src]
insert_after("arm_vm_prot_init(args);", [stage(11)])
insert_after("init_ptpages(cpu_tte, gVirtBase, dynamic_memory_begin, TRUE", [stage(10)])
insert_after("boot_ttep = kvtophys((vm_offset_t)boot_tte);", [stage(9)])
# the #endif that closes the unsupported-memory check
pi = [i for i, l in enumerate(src) if 'panic("Unsupported memory configuration' in l][0]
hi = [i for i in range(pi, len(src)) if src[i].strip() == "#endif"][0]
src[hi + 1:hi + 1] = [stage(8)]
insert_after("vm_map_address_t dynamic_memory_begin;", [stage(5)])

FILE.write_text("\n".join(src), newline="\n")

diff = run("git", "diff", "--", "osfmk/arm64/arm_vm_init.c").stdout
if not diff.strip():
    sys.exit("git produced no diff")
print(diff[:400])
print("... diff lines:", len(diff.split("\n")))

# splice into the big patch
plines = PATCH.read_text().split("\n")
out, i, done = [], 0, False
while i < len(plines):
    if plines[i].startswith("diff --git"):
        start = i
        i += 1
        while i < len(plines) and not plines[i].startswith("diff --git"):
            i += 1
        sec2 = plines[start:i]
        if "a/osfmk/arm64/arm_vm_init.c" in sec2[0]:
            out += diff.rstrip("\n").split("\n")
            done = True
        else:
            out += sec2
        continue
    out.append(plines[i])
    i += 1
assert done
while out and out[-1] == "":
    out.pop()
PATCH.write_text("\n".join(out) + "\n", newline="\n")
print("spliced")
