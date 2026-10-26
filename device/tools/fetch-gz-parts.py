#!/usr/bin/env python3
"""Fetch the kernel through ci-parts gz chunks: download, concat, gunzip, verify."""
import gzip, hashlib, json, os, sys, time, urllib.request
TOKEN = os.environ.get("GITHUB_TOKEN") or ""
REPO = "1696108518/UniXNU-liuqin"
OUT = os.path.expanduser("~/liuqin-gh/kernel.macho")


def log(*a):
    print(*a, flush=True)


def api(path, raw=False, tries=4, timeout=25):
    last = None
    for i in range(tries):
        req = urllib.request.Request("https://api.github.com" + path)
        req.add_header("Authorization", "Bearer " + TOKEN)
        if raw:
            req.add_header("Accept", "application/vnd.github.raw")
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            return r.read() if raw else json.loads(r.read())
        except Exception as e:
            last = e
            time.sleep(1)
    raise RuntimeError(str(last))


def bsha(d):
    return hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest()


tree = api("/repos/%s/git/trees/ci-out?recursive=1" % REPO)
ent = [t for t in tree["tree"] if t["path"] == "kernel/kernel.macho"][0]
want, size = ent["sha"], ent["size"]
log("want", want, size)

# wait for the gz split to land
deadline = time.time() + 600
parts = []
while time.time() < deadline:
    runs = api("/repos/%s/actions/workflows/split.yml/runs?per_page=1" % REPO)
    r = (runs.get("workflow_runs") or [None])[0]
    if r and r["status"] == "completed" and r["conclusion"] == "success":
        try:
            t = api("/repos/%s/git/trees/ci-parts?recursive=1" % REPO)
            parts = sorted((x for x in t["tree"] if x["path"].startswith("kernel/gzpart-")),
                           key=lambda x: x["path"])
        except Exception:
            parts = []
        if parts:
            log("gz parts:", [(p["path"], p["size"]) for p in parts])
            break
    time.sleep(10)
if not parts:
    sys.exit("no gz parts")

buf = b""
for p in parts:
    for attempt in range(15):
        try:
            chunk = api("/repos/%s/git/blobs/%s" % (REPO, p["sha"]), raw=True)
            if len(chunk) == p["size"]:
                log("  ok", p["path"], len(chunk))
                break
            log("  short", p["path"], len(chunk), p["size"])
        except Exception as e:
            log("  retry", p["path"], type(e).__name__)
    else:
        sys.exit("part failed: " + p["path"])
    buf += chunk

log("gz bytes", len(buf))
data = gzip.decompress(buf)
if len(data) != size or bsha(data) != want:
    sys.exit("verify failed: %d bytes, sha %s" % (len(data), bsha(data)[:16]))
open(OUT, "wb").write(data)
log("kernel:", OUT, len(data), bsha(data)[:16])
