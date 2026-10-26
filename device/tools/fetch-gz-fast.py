#!/usr/bin/env python3
"""Aggressive gz-part fetcher: short timeouts, many retries, per-part completion."""
import gzip, hashlib, json, os, sys, time, urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN") or ""
REPO = "1696108518/UniXNU-liuqin"
OUT = os.path.expanduser("~/liuqin-gh/kernel.macho")


def log(*a):
    print(*a, flush=True)


def get(path, raw=False, timeout=12):
    req = urllib.request.Request("https://api.github.com" + path)
    req.add_header("Authorization", "Bearer " + TOKEN)
    if raw:
        req.add_header("Accept", "application/vnd.github.raw")
    r = urllib.request.urlopen(req, timeout=timeout)
    d = r.read()
    return d if raw else json.loads(d)


def bsha(d):
    return hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest()


tree = None
for _ in range(20):
    try:
        tree = get("/repos/%s/git/trees/ci-out?recursive=1" % REPO)
        break
    except Exception as e:
        log("tree retry", type(e).__name__)
        time.sleep(2)
ent = [t for t in tree["tree"] if t["path"] == "kernel/kernel.macho"][0]
want, size = ent["sha"], ent["size"]
log("want", want, size)

parts = None
for _ in range(30):
    try:
        t = get("/repos/%s/git/trees/ci-parts?recursive=1" % REPO)
        parts = sorted((x for x in t["tree"] if x["path"].startswith("kernel/gzpart-")),
                       key=lambda x: x["path"])
        if parts and sum(p.get("size", 0) for p in parts) > 1000000:
            break
    except Exception as e:
        log("parts retry", type(e).__name__)
    time.sleep(3)
log("parts", [(p["path"], p["size"]) for p in parts])

buf = b""
for p in parts:
    got = None
    for attempt in range(120):
        try:
            d = get("/repos/%s/git/blobs/%s" % (REPO, p["sha"]), raw=True)
            if len(d) == p["size"]:
                got = d
                log("  ok", p["path"], len(d), "attempt", attempt)
                break
            log("  short", p["path"], len(d), p["size"], "attempt", attempt)
        except Exception as e:
            if attempt % 10 == 0:
                log("  retry", p["path"], attempt, type(e).__name__)
    if got is None:
        sys.exit("failed " + p["path"])
    buf += got

data = gzip.decompress(buf)
if len(data) != size or bsha(data) != want:
    sys.exit("verify failed %s" % bsha(data)[:16])
open(OUT, "wb").write(data)
log("kernel:", OUT, len(data), bsha(data)[:16])
