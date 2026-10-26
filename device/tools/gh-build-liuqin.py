#!/usr/bin/env python3
"""Build the liuqin kernel on the UniXNU macOS GitHub Actions runner.

Everything runs over api.github.com (no github.com, no git push, no gh CLI):
  1. create the device repository and upload its files with the Git Data API,
  2. fork UniXNU and point a branch at the exact commit the device patches were
     validated against,
  3. dispatch .github/workflows/macos.yml on that branch,
  4. wait for the run and download the kernel artifact.

Token: classic PAT with repo + workflow, or fine-grained with
Contents r/w, Actions r/w, Workflows r/w (and Administration r/w if the fork
needs its Actions enabled over the API).

  GITHUB_TOKEN=... python3 tools/gh-build-liuqin.py --dry-run
  GITHUB_TOKEN=... python3 tools/gh-build-liuqin.py --steps kernel
  # then, on the WSL side: payload + boot.img from out/liuqin/kernel/kernel.macho
"""
import argparse
import base64
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("LIUQIN_GH_API", "https://api.github.com")
PIN = "926639cdd43b4372f9369d5d1e0e08122ce4281d"   # UniXNU main as documented on unixnu.com (2026-10-22)
PINNED_BRANCH = "liuqin-build"
DEVICE_REPO = "UniXNU-liuqin"
UPSTREAM = "UniXNU/UniXNU"
HERE = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path.home() / "liuqin-gh"


def api(token, method, path, body=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    # this link truncates larger responses, so retry the read a few times
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, data=data, timeout=90) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"raw": raw[:400].decode("utf-8", "replace")}
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last

def files():
    r = subprocess.run(["git", "ls-files"], cwd=str(HERE), capture_output=True, text=True)
    if r.returncode:
        sys.exit("%s is not a git repository" % HERE)
    return [p for p in r.stdout.splitlines() if p]


def upload_tree(token, user, repo, branch, listing):
    tree = []
    for i, rel in enumerate(listing, 1):
        data = (HERE / rel).read_bytes()
        code, blob = api(token, "POST", "/repos/%s/%s/git/blobs" % (user, repo),
                         {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        if code not in (201, 200):
            sys.exit("blob %s failed: %s %s" % (rel, code, blob))
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        if i % 10 == 0:
            print("  %d/%d files" % (i, len(listing)), end="\r", flush=True)
    print("  %d/%d files" % (len(listing), len(listing)))
    code, t = api(token, "POST", "/repos/%s/%s/git/trees" % (user, repo), {"tree": tree})
    if code not in (201, 200):
        sys.exit("tree failed: %s %s" % (code, t))
    code, c = api(token, "POST", "/repos/%s/%s/git/commits" % (user, repo), {
        "message": "liuqin device repository: kernel USB CDC-ACM debug port\n\n"
                   "patches/xnu keeps the 49 base UniXNU patches plus zzz-liuqin-usb-debug.patch;\n"
                   "board.toml enables it with liuqin_usb=1. See docs/liuqin-usb-debug.md",
        "tree": t["sha"],
    })
    if code not in (201, 200):
        sys.exit("commit failed: %s %s" % (code, c))
    ref = "refs/heads/" + branch
    code, res = api(token, "POST", "/repos/%s/%s/git/refs" % (user, repo), {"ref": ref, "sha": c["sha"]})
    if code == 422:
        code, res = api(token, "PATCH", ("/repos/%s/%s/git/" + ref) % (user, repo),
                        {"sha": c["sha"], "force": True})
    if code not in (201, 200):
        sys.exit("ref failed: %s %s" % (code, res))
    print("  device commit:", c["sha"][:9])
    return c["sha"]



def ensure_initialized(token, user, repo):
    """A brand new repository has no git database: Git Data blobs return 409.
    Create one placeholder file through the contents API first."""
    code, info = api(token, "GET", "/repos/%s/%s" % (user, repo))
    if code != 200:
        return
    if info.get("size", 0) > 0:
        return
    code, res = api(token, "PUT", "/repos/%s/%s/contents/.init" % (user, repo), {
        "message": "initialize repository",
        "content": base64.b64encode(b"liuqin device repository\n").decode(),
    })
    print("  initialized empty repository:", code)


def ensure_workflow(token, user, branch, default_branch, path=".github/workflows/macos.yml"):
    """workflow_dispatch only resolves when the workflow file exists on the ref we
    dispatch. The pinned branch predates the workflow in some upstream trees, so
    copy it over from the fork's default branch."""
    # Prefer the copy carried by the device repository: pinning the branch to an
    # older commit wipes whatever was added to it, so the override must be re-applied
    # on every dispatch from a file we control.
    local = HERE / path
    if local.is_file():
        import base64 as _b64
        sha = None
        code, cur = api(token, "GET", "/repos/%s/UniXNU/contents/%s?ref=%s" % (user, path, branch))
        if code == 200:
            if cur.get("content") and _b64.b64decode(cur["content"]) == local.read_bytes():
                return True
            sha = cur["sha"]
        body = {"message": "ci: apply the liuqin workflow overrides",
                "content": _b64.b64encode(local.read_bytes()).decode(),
                "branch": branch}
        if sha:
            body["sha"] = sha
        code, res = api(token, "PUT", "/repos/%s/UniXNU/contents/%s" % (user, path), body)
        if code in (200, 201):
            print("  applied %s onto %s from the device repository" % (path, branch))
            return True
        print("WARNING: cannot apply %s: %s %s" % (path, code, res))
        return False
    code, _ = api(token, "GET", "/repos/%s/UniXNU/contents/%s?ref=%s" % (user, path, branch))
    if code == 200:
        return True
    code, src = api(token, "GET", "/repos/%s/UniXNU/contents/%s?ref=%s" % (user, path, default_branch))
    if code != 200:
        print("WARNING: %s missing on %s too (%s)" % (path, default_branch, code))
        return False
    code, res = api(token, "PUT", "/repos/%s/UniXNU/contents/%s" % (user, path), {
        "message": "ci: add the macOS build workflow to the pinned branch",
        "content": src["content"].replace("\n", ""),
        "branch": branch,
    })
    if code in (200, 201):
        print("  copied %s onto %s" % (path, branch))
        return True
    print("WARNING: cannot copy %s onto %s: %s %s" % (path, branch, code, res))
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    ap.add_argument("--user", default="")
    ap.add_argument("--steps", default="kernel")
    ap.add_argument("--defconfig", default="liuqin_defconfig")
    ap.add_argument("--device-branch", default="main")
    ap.add_argument("--run-branch", default=PINNED_BRANCH)
    ap.add_argument("--pin", default=PIN, help="UniXNU commit to run the workflow on")
    ap.add_argument("--no-pin", action="store_true", help="use the fork branch as it is")
    ap.add_argument("--private-device", action="store_true",
                    help="keep the device repository private (then set the UNIXNU_DEVICE_TOKEN secret)")
    ap.add_argument("--timeout", type=int, default=7200)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    token = a.token.strip()
    if not token:
        sys.exit("no token: set GITHUB_TOKEN (repo + workflow scopes)")
    listing = files()
    total = sum((HERE / p).stat().st_size for p in listing)
    print("device repository: %d files, %.1f MiB" % (len(listing), total / 1048576))

    code, me = api(token, "GET", "/user")
    if code != 200:
        sys.exit("token rejected by /user: %s %s" % (code, me))
    user = a.user or me["login"]
    print("account:", user)

    if a.dry_run:
        print("[dry-run] would create %s/%s (%s) and upload %d files"
              % (user, DEVICE_REPO, "private" if a.private_device else "public", len(listing)))
        print("[dry-run] would fork %s and dispatch macos.yml on %s at %s"
              % (UPSTREAM, a.run_branch, a.pin[:9]))
        print("[dry-run] inputs: device_repository=%s/%s device_ref=%s defconfig=%s steps=%s"
              % (user, DEVICE_REPO, a.device_branch, a.defconfig, a.steps))
        return 0

    # 1) device repository + files
    code, info = api(token, "GET", "/repos/%s/%s" % (user, DEVICE_REPO))
    if code == 404:
        code, info = api(token, "POST", "/user/repos", {
            "name": DEVICE_REPO, "private": bool(a.private_device),
            "description": "Xiaomi Pad 6 Pro (liuqin/SM8475) UniXNU device repository, kernel USB debug port",
        })
        if code not in (201, 200):
            sys.exit("cannot create %s: %s %s" % (DEVICE_REPO, code, info))
        print("created", info["full_name"], "(public)" if not a.private_device else "(private)")
    elif code == 200:
        print("device repository exists:", info["full_name"], "- updating branch", a.device_branch)
    else:
        sys.exit("cannot read device repository: %s %s" % (code, info))
    ensure_initialized(token, user, DEVICE_REPO)
    upload_tree(token, user, DEVICE_REPO, a.device_branch, listing)

    # 2) fork + pinned branch
    code, fork = api(token, "GET", "/repos/%s/UniXNU" % user)
    if code == 404:
        print("forking", UPSTREAM)
        code, fork = api(token, "POST", "/repos/%s/forks" % UPSTREAM, {"default_branch_only": False})
        if code not in (202, 200):
            sys.exit("cannot fork: %s %s" % (code, fork))
        for _ in range(90):
            time.sleep(5)
            code, fork = api(token, "GET", "/repos/%s/UniXNU" % user)
            if code == 200:
                break
        print("fork ready" if code == 200 else "fork still not visible")
    # Actions must be enabled on forks
    api(token, "PUT", "/repos/%s/UniXNU/actions/permissions" % user,
        {"enabled": True, "allowed_actions": "all"})
    # point a branch at the pinned commit (objects already exist server side)
    ref = "refs/heads/" + a.run_branch
    code, res = (0, {"skipped": "no-pin"}) if a.no_pin else api(
        token, "POST", "/repos/%s/UniXNU/git/refs" % user, {"ref": ref, "sha": a.pin})
    if a.no_pin:
        print("leaving branch %s as it is (--no-pin)" % a.run_branch)
        code = 200
    if code == 422:
        code, res = api(token, "PATCH", ("/repos/%s/UniXNU/git/" + ref) % user,
                        {"sha": a.pin, "force": True})
    if code in (201, 200):
        print("pinned branch %s -> %s" % (a.run_branch, a.pin[:9]))
    else:
        print("WARNING: cannot pin %s (%s %s); using the fork default branch %s"
              % (a.run_branch, code, res, fork.get("default_branch", "main")))
        a.run_branch = fork.get("default_branch", "main")

    ensure_workflow(token, user, a.run_branch, fork.get("default_branch", "main"))

    # 3) dispatch
    payload = {"ref": a.run_branch, "inputs": {
        "device_repository": "%s/%s" % (user, DEVICE_REPO),
        "device_ref": a.device_branch,
        "defconfig": a.defconfig,
        "steps": a.steps,
        "ipsw_url": "",
        "pre_build": "",
        "upload_userdata": "false",
        "skip_setup": "false",
        "owner_trust_cache": "false",
    }}
    started = time.time()
    before = set()
    code, prev = api(token, "GET", "/repos/%s/UniXNU/actions/runs?per_page=30" % user)
    if code == 200:
        before = {r["id"] for r in prev.get("workflow_runs", [])}
    code, res = api(token, "POST",
                    "/repos/%s/UniXNU/actions/workflows/macos.yml/dispatches" % user, payload)
    if code not in (204, 201):
        sys.exit("dispatch failed: %s %s\n"
                 "If this says 'workflows are disabled', open https://github.com/%s/UniXNU/actions "
                 "and click the enable button once." % (code, res, user))
    print("dispatched; waiting for the run ...")

    run = None
    while time.time() - started < 180 and not run:
        code, runs = api(token, "GET", "/repos/%s/UniXNU/actions/runs?event=workflow_dispatch&per_page=20" % user)
        if code == 200:
            for r in runs.get("workflow_runs", []):
                if r["id"] not in before and r.get("head_branch") == a.run_branch:
                    run = r
                    break
        if not run:
            time.sleep(5)
    if not run:
        sys.exit("run did not appear; check https://github.com/%s/UniXNU/actions" % user)
    print("run:", run["html_url"])

    while time.time() - started < a.timeout:
        code, run = api(token, "GET", "/repos/%s/UniXNU/actions/runs/%d" % (user, run["id"]))
        if code == 200:
            print("  %s %s   " % (run.get("status"), run.get("conclusion") or ""), end="\r", flush=True)
            if run.get("status") == "completed":
                break
        time.sleep(20)
    print()
    print("conclusion:", run.get("conclusion"))
    if run.get("conclusion") != "success":
        print("see", run["html_url"])
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    code, arts = api(token, "GET", "/repos/%s/UniXNU/actions/runs/%d/artifacts" % (user, run["id"]))
    if code != 200:
        sys.exit("cannot list artifacts: %s %s" % (code, arts))
    for art in arts.get("artifacts", []):
        target = OUT / (art["name"] + ".zip")
        req = urllib.request.Request(art["archive_download_url"])
        req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=900) as r, open(target, "wb") as f:
                f.write(r.read())
        except OSError as error:
            # The artifact URL redirects to blob storage, which some networks reset.
            # The workflow also publishes kernel/ and logs/ on the ci-out branch.
            print("artifact %s not downloadable here (%s)" % (art["name"], error))
            print("fetch it from ci-out instead: /repos/%s/UniXNU/contents/kernel/kernel.macho?ref=ci-out" % user)
            continue
        print("artifact:", target, "%.1f MiB" % (target.stat().st_size / 1048576))
    return 0


if __name__ == "__main__":
    sys.exit(main())
