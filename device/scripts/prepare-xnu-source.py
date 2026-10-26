#!/usr/bin/env python3
"""Restore omitted DriverKit headers from Apple's earlier Darwin 23 source."""
import concurrent.futures
import hashlib
import json
import os
import time
from pathlib import Path
import urllib.request
import urllib.error

# liuqin override: GitHub's unauthenticated API limit is per runner IP and shared
# hosted runners exhaust it (HTTP 403 "rate limit exceeded" killed the first
# builds). The three directory listings this script needs are carried in the
# device repository next to this file; the API is only a fallback, and it uses
# GITHUB_TOKEN when the workflow provides one.
BUNDLED = Path(__file__).resolve().parent
TOKEN = (os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or '').strip()


def api_bytes(url, name):
    bundled = BUNDLED / name
    if bundled.is_file():
        print(f'using bundled listing {name}')
        return bundled.read_bytes()
    last = None
    for attempt in range(4):
        request = urllib.request.Request(url)
        request.add_header('Accept', 'application/vnd.github+json')
        if TOKEN:
            request.add_header('Authorization', 'Bearer ' + TOKEN)
        try:
            return urllib.request.urlopen(request, timeout=60).read()
        except urllib.error.HTTPError as error:
            last = error
            if error.code not in (403, 429, 500, 502, 503):
                raise
            time.sleep(5 * (attempt + 1))
    raise last


def download(url, timeout=60):
    request = urllib.request.Request(url)
    if TOKEN and url.startswith('https://api.github.com/'):
        request.add_header('Authorization', 'Bearer ' + TOKEN)
    return urllib.request.urlopen(request, timeout=timeout).read()

# Tags of the Apple sources that still carry the headers newer xnu omits; feeds.toml sets them for the unixnu driver.
TAG = os.environ.get('UNIXNU_DRIVERKIT_TAG', 'xnu-10063.121.3')
TRUST_TAG = os.environ.get('UNIXNU_TRUSTCACHE_TAG', 'xnu-8796.101.5')
DESTINATION = Path('.cache/xnu-work/iokit/DriverKit')
CACHE = Path(f'.cache/sources/xnu-driverkit-{TAG.removeprefix("xnu-")}.json')
URL = f'https://api.github.com/repos/apple-oss-distributions/xnu/contents/iokit/DriverKit?ref={TAG}'


def restore(entry, destination=DESTINATION, tag=TAG):
    if entry['type'] != 'file' or not entry['name'].endswith('.h'):
        return None
    name = entry.get('relative', entry['name'])
    target = destination / name
    if target.exists():
        return None
    data = download(entry['download_url'], timeout=30)
    digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if digest != entry['sha']:
        raise ValueError(f'Git blob hash mismatch: {entry["name"]}')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {'name': name, 'source_tag': tag, 'git_blob': digest,
            'sha256': hashlib.sha256(data).hexdigest()}


if __name__ == '__main__':
    if not DESTINATION.is_dir():
        raise SystemExit('Create the local XNU work source before preparing headers')
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(api_bytes(URL, CACHE.name))
    entries = json.loads(CACHE.read_text())
    crypto_cache = CACHE.with_name(f'xnu-driverkit-crypto-{TAG.removeprefix("xnu-")}.json')
    if not crypto_cache.exists():
        crypto_url = URL.replace('/DriverKit?', '/DriverKit/crypto?')
        crypto_cache.write_bytes(api_bytes(crypto_url, crypto_cache.name))
    for entry in json.loads(crypto_cache.read_text()):
        entry['relative'] = 'crypto/' + entry['name']
        entries.append(entry)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        restored = [entry for entry in executor.map(restore, entries) if entry]
        trust_tag = TRUST_TAG
        trust_cache = CACHE.with_name(f'xnu-trustcache-{TRUST_TAG.removeprefix("xnu-")}.json')
        if not trust_cache.exists():
            url = ('https://api.github.com/repos/apple-oss-distributions/xnu/'
                   f'contents/EXTERNAL_HEADERS/TrustCache?ref={trust_tag}')
            trust_cache.write_bytes(api_bytes(url, trust_cache.name))
        trust_destination = Path('.cache/xnu-work/EXTERNAL_HEADERS/TrustCache')
        def restore_trust(entry):
            return restore(entry, trust_destination, trust_tag)
        restored.extend(entry for entry in executor.map(
            restore_trust, json.loads(trust_cache.read_text())) if entry)
    previous = Path('.cache/sources/xnu-restored-headers.json')
    existing = json.loads(previous.read_text()) if previous.exists() else []
    by_name = {entry['name']: entry for entry in existing + restored}
    previous.write_text(json.dumps(list(by_name.values()), indent=2) + '\n')
    print(f'Restored {len(restored)} omitted public headers from Apple; blob hashes verified')
