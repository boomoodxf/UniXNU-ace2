#!/usr/bin/env python3
"""Robust fetch: retry the raw read, else split on a runner and stitch."""
import hashlib, json, os, sys, time, urllib.request
TOKEN = os.environ.get("GITHUB_TOKEN") or ""
if not TOKEN:
    sys.exit("set GITHUB_TOKEN")
REPO = "1696108518/UniXNU-liuqin"
PATH = "kernel/kernel.macho"
OUT = os.path.expanduser("~/liuqin-gh/kernel.macho")

def api(path, raw=False, tries=5, timeout=300):
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
            print("  retry %d: %s %s" % (i, type(e).__name__, str(e)[:50]))
            time.sleep(3)
    raise RuntimeError("api failed: %s (%s)" % (path, last))

def bsha(d):
    return hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest()

tree = api("/repos/%s/git/trees/ci-out?recursive=1" % REPO)
ent = [t for t in tree["tree"] if t["path"] == PATH][0]
want, size = ent["sha"], ent["size"]
print("want", want, size)

data = None
for attempt in range(6):
    try:
        d = api("/repos/%s/git/blobs/%s" % (REPO, want), raw=True, tries=1)
        if bsha(d) == want:
            data = d
            print("direct read ok on attempt", attempt)
            break
        print("  attempt %d short (%d/%d)" % (attempt, len(d), size))
    except Exception as e:
        print("  attempt %d failed: %s" % (attempt, type(e).__name__))

if data is None:
    print("falling back to the split workflow")
    req = urllib.request.Request("https://api.github.com/repos/%s/actions/workflows/split.yml/dispatches" % REPO,
                                 method="POST", data=json.dumps({"ref": "main", "inputs": {"source": PATH, "chunk": "11000000"}}).encode())
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    print("dispatch:", urllib.request.urlopen(req, timeout=60).status)
    # wait for the split workflow to finish
    deadline = time.time() + 600
    while time.time() < deadline:
        runs = api("/repos/%s/actions/workflows/split.yml/runs?per_page=1" % REPO)
        r = (runs.get("workflow_runs") or [None])[0]
        if r and r["status"] == "completed":
            print("split run:", r["conclusion"], r["created_at"])
            break
        time.sleep(10)
    parts = None
    for _ in range(30):
        try:
            t = api("/repos/%s/git/trees/ci-parts?recursive=1" % REPO, tries=1)
        except Exception:
            time.sleep(10); continue
        parts = sorted((x for x in t["tree"] if x["path"].startswith("kernel/part-")), key=lambda x: x["path"])
        if parts and sum(p.get("size", 0) for p in parts) == size:
            buf = b""
            for p in parts:
                buf += api("/repos/%s/git/blobs/%s" % (REPO, p["sha"]), raw=True)
            if bsha(buf) == want:
                data = buf
                print("stitched parts verified")
                break
            print("  parts stale (%d bytes), waiting" % len(buf))
        time.sleep(10)

if data is None:
    sys.exit("could not fetch the kernel")
open(OUT, "wb").write(data)
print("kernel:", OUT, len(data), bsha(data)[:16])
