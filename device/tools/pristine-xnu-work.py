#!/usr/bin/env python3
"""Make the kernel patch pass deterministic across the two XNU passes.

unixnu build kernel runs a compile-record pass before the real one. That first
pass ends at the link (XNU_BOOTSTRAP=1 links without the device archives), but it
has already applied every patches/xnu/*.patch to .cache/xnu-work. The real pass
then walks the same set, reverses the late observation hooks first and only
re-applies a patch whose reverse check failed.

That round trip is not idempotent for this device repository: zzz-boot-progress
inserts a line inside the block that offline-owner-root-binding-audit adds to
bsd_init.c, and zzz-liuqin-usb-debug inserts two lines inside the hunk context of
zzz-boot-progress, so neither patch can be reversed once the other has touched
the same region. The set is then rejected with

    error: patch failed: bsd/kern/bsd_init.c:987
    error: bsd/kern/bsd_init.c: patch does not apply

The fix is to hand every pass the same starting point: the pristine checkout.
Objects live in build/, not in .cache/xnu-work, so nothing is lost.
"""
from pathlib import Path
import sys

MARKER = "liuqin: pristine xnu-work before the patch loop"
HOOK = "# The optional observation hooks overlap existing root/exec patch context."
INJECT = """# {marker}
# unixnu build kernel runs a compile-record pass before the real one. That pass
# leaves every patch applied, so the real pass cannot reverse hunks another patch
# rewrote in place (boot-progress inside the owner-root audit block) and rejects
# the whole set. Restore the pristine source at the top of every pass instead.
if [ -d .cache/xnu-work/.git ]; then
  git -C .cache/xnu-work reset --hard -q
  git -C .cache/xnu-work clean -qfd
fi

""".format(marker=MARKER)


def main() -> int:
    script = Path(sys.argv[1] if len(sys.argv) > 1 else "scripts/build-xnu-4k-baseline.sh")
    if not script.is_file():
        print("{} missing".format(script), file=sys.stderr)
        return 1
    text = script.read_text()
    if MARKER in text:
        print("build script already patched")
        return 0
    if HOOK not in text:
        print("anchor not found in {}".format(script), file=sys.stderr)
        return 1
    script.write_text(text.replace(HOOK, INJECT + HOOK, 1))
    print("build script patched: pristine xnu-work per pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
