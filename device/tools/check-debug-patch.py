#!/usr/bin/env python3
"""Structural check for patches/xnu/zzz-liuqin-usb-debug.patch.

Editing a patch by hand (or by script) is how a 16 minute runner cycle gets
thrown away on "error: corrupt patch at <file>:<line>". This checks, without a
macOS host and without the XNU tree:

  * every hunk header count matches the hunk body,
  * every line inside a hunk starts with ' ', '+' or '-',
  * the added C files have balanced braces and parentheses,
  * the console mirror and the marker calls are actually wired.
"""
from pathlib import Path
import sys

PATCH = Path(__file__).resolve().parents[1] / "patches/xnu/zzz-liuqin-usb-debug.patch"


def main() -> int:
    lines = PATCH.read_text().split("\n")
    problems = []
    files = {}
    current = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("+++ b/"):
            current = line[6:]
            files.setdefault(current, [])
            i += 1
            continue
        if line.startswith("@@"):
            head = line.split("@@")[1].strip().split()
            try:
                want_old = int(head[0].split(",")[1])
                want_new = int(head[1].split(",")[1])
            except (IndexError, ValueError):
                problems.append("line %d: unreadable hunk header" % (i + 1))
                i += 1
                continue
            old = new = 0
            j = i + 1
            while j < len(lines) and not lines[j].startswith(("@@", "diff --git")):
                body = lines[j]
                if body.startswith(" "):
                    old += 1
                    new += 1
                elif body.startswith("-"):
                    old += 1
                elif body.startswith("+"):
                    new += 1
                    if current:
                        files[current].append(body[1:])
                elif body == "" and j == len(lines) - 1:
                    break
                else:
                    problems.append("line %d: %r is not a hunk body line" % (j + 1, body[:40]))
                j += 1
            if (old, new) != (want_old, want_new):
                problems.append("line %d: header says -%d +%d, body has -%d +%d"
                                % (i + 1, want_old, want_new, old, new))
            i = j
            continue
        i += 1

    for name in ("bsd/dev/liuqin_debug.c", "bsd/dev/liuqin_usb_debug.c"):
        body = "\n".join(files.get(name, []))
        if not body:
            problems.append("%s: no added content" % name)
            continue
        for open_c, close_c, what in (("{", "}", "braces"), ("(", ")", "parentheses")):
            if body.count(open_c) != body.count(close_c):
                problems.append("%s: unbalanced %s (%d vs %d)"
                                % (name, what, body.count(open_c), body.count(close_c)))

    debug = "\n".join(files.get("bsd/dev/liuqin_debug.c", []))
    usb = "\n".join(files.get("bsd/dev/liuqin_usb_debug.c", []))
    for needle, where, name in (
            ("liuqin_fb_putc(c);", debug, "console mirror call"),
            ("liuqin_fb_band(0, 0xff00ffffu);", usb, "band 0 (bsd_init reached)"),
            ("liuqin_fb_band(5, 0xffff00ffu);", usb, "band 5 (port running)"),
            ("liuqin_fb_marker_boot(void)", usb, "boot marker definition"),
            ("liuqin_fb_marker_boot();", "\n".join(files.get("bsd/kern/bsd_init.c", [])), "bsd_init hook"),
    ):
        if needle not in where:
            problems.append("%s: %r missing" % (name, needle))

    if problems:
        print("\n".join(problems))
        return 1
    print("debug patch ok: %d files, %d lines" % (len(files), len(lines)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
