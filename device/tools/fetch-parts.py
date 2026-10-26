#!/usr/bin/env python3
"""Fetch ci-out/kernel/kernel.macho via CI-split parts, with progress."""
import hashlib, json, os, sys, time, urllib.request
TOKEN = os.environ.get("GITHUB_TOKEN") or ""
REPO = "1696108518/UniXNU-liuqin"
PATH_ = "kernel/kernel.macho"
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
            log("  retry", i, type(e).__name__, str(e)[:40])
            time.sleep(1)
    raise RuntimeError(str(last))


def bsha(d):
    return hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest()


tree = api("/repos/%s/git/trees/ci-out?recursive=1" % REPO)
ent = [t for t in tree["tree"] if t["path"] == PATH_][0]
want, size = ent["sha"], ent["size"]
log("want", want, size)

if os.environ.get("DISPATCH_SPLIT"):
    req = urllib.request.Request("https://api.github.com/repos/%s/actions/workflows/split.yml/dispatches" % REPO,
                                 method="POST",
                                 data=json.dumps({"ref": "main", "inputs": {"source": PATH_, "chunk": os.environ["DISPATCH_SPLIT"]}}).encode())
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    log("split dispatch:", urllib.request.urlopen(req, timeout=60).status)

deadline = time.time() + 900
data = None
while time.time() < deadline:
    time.sleep(15)
    try:
        parts = sorted((x for x in api("/repos/%s/git/trees/ci-parts?recursive=1" % REPO)["tree"]
                        if x["path"].startswith("kernel/part-")), key=lambda x: x["path"])
    except Exception as e:
        log("  tree:", type(e).__name__)
        continue
    if not parts or sum(p.get("size", 0) for p in parts) != size:
        log("  parts not ready:", [(p["path"], p.get("size")) for p in parts])
        continue
    log("parts:", [(p["path"], p["size"]) for p in parts])
    buf = b""
    ok = True
    for p in parts:
        for attempt in range(12):
            try:
                chunk = api("/repos/%s/git/blobs/%s" % (REPO, p["sha"]), raw=True)
                if len(chunk) == p["size"]:
                    break
                log("  short", p["path"], len(chunk), p["size"])
            except Exception as e:
                log("  part retry", p["path"], type(e).__name__)
        else:
            ok = False
            break
        buf += chunk
    if not ok:
        continue
    if bsha(buf) == want:
        data = buf
        break
    log("  stitched but sha differs; waiting for a fresh split")

if data is None:
    log("failed")
    sys.exit(1)
open(OUT, "wb").write(data)
log("kernel:", OUT, len(data), bsha(data)[:16])
