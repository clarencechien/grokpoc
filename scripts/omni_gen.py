#!/usr/bin/env python3
"""Gemini Omni 1.1 Flash — one clip per call, first frame / first+last frame / text.

Key from env `gemini_key` (or GEMINI_API_KEY). Stdlib only. Skips outputs that exist.

  python3 scripts/omni_gen.py OUT.mp4 --first a.jpg [--last b.jpg] --prompt "..." [--res 720p]

Writes OUT.mp4 and OUT.json (the response with any base64 payload stripped).
API: POST /v1beta/interactions (https://ai.google.dev/gemini-api/docs/omni).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-omni-1.1-flash"


def key() -> str:
    k = os.environ.get("gemini_key") or os.environ.get("GEMINI_API_KEY")
    if not k:
        sys.exit("no gemini_key / GEMINI_API_KEY in env")
    return k


def call(method: str, url: str, body: dict | None = None, timeout: int = 900) -> bytes:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"x-goog-api-key": key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def image_part(p: Path) -> dict:
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return {"type": "image", "data": base64.b64encode(p.read_bytes()).decode(), "mime_type": mime}


def strip(o):
    if isinstance(o, dict):
        return {k: (f"<{len(v)} chars>" if k in ("data", "signature") and isinstance(v, str) else strip(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o


def videos(resp: dict):
    for step in resp.get("steps", []) or []:
        for c in step.get("content", []) or []:
            if c.get("type") == "video":
                yield c
    for c in resp.get("outputs", []) or []:          # tolerate the other response shape
        if c.get("type") == "video":
            yield c


def generate(out: Path, prompt: str, first: Path | None, last: Path | None, res: str) -> bool:
    if out.exists() and out.stat().st_size > 100_000:
        print(f"skip {out} (exists)")
        return True
    parts = [image_part(p) for p in (first, last) if p]
    body = {"model": MODEL, "input": parts + [{"type": "text", "text": prompt}],
            "response_format": {"type": "video", "resolution": res, "aspect_ratio": "16:9", "delivery": "uri"}}
    t0 = time.time()
    try:
        raw = call("POST", f"{API}/interactions", body)
    except urllib.error.HTTPError as e:
        print(f"FAIL {out.name}: HTTP {e.code} {e.read().decode()[:600]}")
        return False
    resp = json.loads(raw)
    # long-running form: poll the interaction until it is done
    while resp.get("status") not in (None, "completed", "failed", "cancelled") and resp.get("id"):
        time.sleep(10)
        resp = json.loads(call("GET", f"{API}/interactions/{resp['id']}"))
    out.with_suffix(".json").write_text(json.dumps(strip(resp), indent=1), encoding="utf-8")
    vids = list(videos(resp))
    if not vids:
        print(f"FAIL {out.name}: no video in response (status={resp.get('status')}); see {out.with_suffix('.json')}")
        return False
    v = vids[0]
    if v.get("data"):
        out.write_bytes(base64.b64decode(v["data"]))
    else:
        uri = v["uri"]
        name = uri.split("/files/")[1].split(":")[0] if "/files/" in uri else None
        if name:                                        # wait until the file is ACTIVE
            for _ in range(90):
                st = json.loads(call("GET", f"{API}/files/{name}")).get("state", "ACTIVE")
                if st == "ACTIVE":
                    break
                time.sleep(5)
        out.write_bytes(call("GET", uri, timeout=300))
    print(f"ok   {out.name}  {out.stat().st_size // 1024} KB  {time.time() - t0:.0f}s")
    return out.stat().st_size > 100_000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--first", type=Path)
    ap.add_argument("--last", type=Path)
    ap.add_argument("--res", default="720p")
    a = ap.parse_args()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    return 0 if generate(a.out, a.prompt, a.first, a.last, a.res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
