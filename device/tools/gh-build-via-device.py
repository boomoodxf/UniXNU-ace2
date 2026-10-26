#!/usr/bin/env python3
"""Build the liuqin kernel in the device repository.

GitHub refuses workflow_dispatch on the build fork ("Actions has been disabled
for this repository") while the device repository still dispatches, and the
device workflow now clones the pinned UniXNU tree instead of checking out the
repository it runs in. This reuses the uploader from gh-build-liuqin.py and
runs the workflow where it is allowed.
"""
import argparse
import base64
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ghb", str(HERE / "tools/gh-build-liuqin.py"))
ghb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ghb)

DEVICE_REPO = "UniXNU-liuqin"
OUT = pathlib.Path.home() / "liuqin-gh"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    ap.add_argument("--steps", default="kernel")
    ap.add_argument("--defconfig", default="liuqin_boot_defconfig")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--no-upload", action="store_true")
    a = ap.parse_args()
    token = a.token.strip()
    if not token:
        sys.exit("no token")

    code, me = ghb.api(token, "GET", "/user")
    if code != 200:
        sys.exit("token rejected: %s %s" % (code, me))
    user = me["login"]
    print("account:", user)

    if not a.no_upload:
        listing = ghb.files()
        total = sum((HERE / p).stat().st_size for p in listing)
        print("device repository: %d files, %.1f MiB" % (len(listing), total / 1048576))
        ghb.upload_tree(token, user, DEVICE_REPO, a.branch, listing)

    payload = {"ref": a.branch, "inputs": {
        "device_repository": "%s/%s" % (user, DEVICE_REPO),
        "device_ref": a.branch,
        "defconfig": a.defconfig,
        "steps": a.steps,
        "ipsw_url": "",
        "pre_build": "",
        "upload_userdata": "false",
        "skip_setup": "false",
        "owner_trust_cache": "false",
    }}
    started = time.time()
    code, prev = ghb.api(token, "GET", "/repos/%s/%s/actions/runs?per_page=30" % (user, DEVICE_REPO))
    before = {r["id"] for r in prev.get("workflow_runs", [])} if code == 200 else set()
    code, res = ghb.api(token, "POST",
                        "/repos/%s/%s/actions/workflows/macos.yml/dispatches" % (user, DEVICE_REPO), payload)
    if code not in (200, 201, 204):
        sys.exit("dispatch failed: %s %s" % (code, res))
    print("dispatched")

    run = None
    while time.time() - started < 240 and not run:
        code, runs = ghb.api(token, "GET", "/repos/%s/%s/actions/runs?per_page=20" % (user, DEVICE_REPO))
        if code == 200:
            for r in runs.get("workflow_runs", []):
                if r["id"] not in before and r.get("head_branch") == a.branch:
                    run = r
                    break
        if not run:
            time.sleep(5)
    if not run:
        sys.exit("run did not appear")
    print("run:", run["html_url"])

    while time.time() - started < a.timeout:
        code, run = ghb.api(token, "GET", "/repos/%s/%s/actions/runs/%d" % (user, DEVICE_REPO, run["id"]))
        if code == 200:
            print("  %s %s   " % (run.get("status"), run.get("conclusion") or ""), end="\r", flush=True)
            if run.get("status") == "completed":
                break
        time.sleep(20)
    print()
    print("conclusion:", run.get("conclusion"))

    # ci-out is written even on failure (the publish step runs always)
    code, tree = ghb.api(token, "GET", "/repos/%s/%s/git/trees/ci-out?recursive=1" % (user, DEVICE_REPO))
    found = {}
    if code == 200:
        found = {t["path"]: t["sha"] for t in tree.get("tree", []) if t["type"] == "blob"}
        print("ci-out:", ", ".join(sorted(found)))
    else:
        print("ci-out unreadable:", code, tree)
    if "kernel/kernel.macho" in found:
        # the blob is ~50 MiB and a single response is cut off on this network,
        # so let the dedicated fetcher retry / split-and-stitch it
        # regenerate the gzip slices, WAIT for that run, then pull them: fetching
        # straight after dispatch downloads the previous build's parts and the sha
        # check fails.
        code, _ = ghb.api(token, "POST", "/repos/%s/%s/actions/workflows/split.yml/dispatches" % (user, DEVICE_REPO),
                          {"ref": "main", "inputs": {"source": "kernel/kernel.macho",
                                                     "chunk": "1000000", "gzip": "true"}})
        print("split dispatch:", code)
        for _ in range(60):
            time.sleep(10)
            code, runs = ghb.api(token, "GET", "/repos/%s/%s/actions/workflows/split.yml/runs?per_page=1"
                                 % (user, DEVICE_REPO))
            if code == 200 and runs.get("workflow_runs"):
                r0 = runs["workflow_runs"][0]
                if r0.get("status") == "completed":
                    print("split:", r0.get("conclusion"))
                    break
        env = dict(os.environ, GITHUB_TOKEN=token)
        r = subprocess.run([sys.executable, str(HERE / "tools/fetch-gz-fast.py")], env=env)
        if r.returncode:
            print("kernel fetch failed; run tools/fetch-gz-fast.py by hand")
    for name in sorted(found):
        if name.startswith("logs/") and name.endswith(".log"):
            code, blob = ghb.api(token, "GET", "/repos/%s/%s/git/blobs/%s"
                                 % (user, DEVICE_REPO, found[name]))
            if code == 200:
                dst = OUT / pathlib.Path(name).name
                dst.write_bytes(base64.b64decode(blob["content"]))
                print("log:", dst, dst.stat().st_size, "bytes")
    return 0 if run.get("conclusion") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
