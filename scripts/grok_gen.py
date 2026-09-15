#!/usr/bin/env python3
"""Drive the xAI Grok Imagine API to render the assets for the 3D pop-up book.

Images : POST https://api.x.ai/v1/images/generations   (grok-imagine-image-2.0)
Videos : POST https://api.x.ai/v1/videos/generations   (grok-imagine-video-1.5)
         then poll GET https://api.x.ai/v1/videos/{request_id}

Only the Python standard library is used, so there is nothing to install.
Requests honour HTTPS_PROXY, which this sandbox needs for outbound traffic.

Usage
  export XAI_API_KEY=xai-...
  python3 scripts/grok_gen.py --check            # verify credentials only
  python3 scripts/grok_gen.py --dry-run          # show every planned call
  python3 scripts/grok_gen.py --pages p1,p2      # render two pages
  python3 scripts/grok_gen.py                    # render everything (resumable)
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.x.ai/v1"
IMAGE_MODEL = os.environ.get("XAI_IMAGE_MODEL", "grok-imagine-image-2.0")
VIDEO_MODEL = os.environ.get("XAI_VIDEO_MODEL", "grok-imagine-video-1.5")

ROOT = Path(__file__).resolve().parent.parent
STORY = ROOT / "story" / "three-little-pigs.json"
ASSETS = ROOT / "book" / "assets"


# ---------------------------------------------------------------- transport

def _key() -> str:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        sys.exit(
            "XAI_API_KEY is not set.\n"
            "Create a key at https://console.x.ai and expose it to this session as an\n"
            "environment variable (do not paste it into the chat transcript)."
        )
    return key


def call(method: str, path: str, payload: dict | None = None, timeout: int = 300) -> dict:
    """One JSON request against the xAI API. Raises RuntimeError with the body on failure."""
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:800]
        raise RuntimeError(f"HTTP {e.code} {method} {path}\n{detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error {method} {path}: {e.reason}") from None


def fetch_bytes(url: str, timeout: int = 300) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- prompts

def build_prompt(story: dict, layer_prompt: str) -> str:
    return f"{layer_prompt}. Style: {story['style']}. {story['cast']}"


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


# ---------------------------------------------------------------- generation

def gen_image(prompt: str, out: Path, aspect: str, dry: bool) -> str:
    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "response_format": "b64_json",
        "size": aspect,
    }
    if dry:
        print(f"    DRY POST /images/generations -> {out.name}")
        print(f"        prompt: {prompt[:150]}...")
        return "dry"

    res = call("POST", "/images/generations", payload)
    items = res.get("data") or []
    if not items:
        raise RuntimeError(f"no image in response: {json.dumps(res)[:400]}")
    item = items[0]
    if item.get("b64_json"):
        blob = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        blob = fetch_bytes(item["url"])
    else:
        raise RuntimeError(f"unexpected image item keys: {list(item)}")
    out.write_bytes(blob)
    revised = item.get("revised_prompt", "")
    print(f"    ok {out.name} ({len(blob) // 1024} KB)")
    return revised


def gen_video(prompt: str, source: Path, out: Path, duration: int, dry: bool,
              poll_every: int = 10, poll_max: int = 90) -> None:
    payload = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "image": {"url": data_uri(source)} if source.exists() else None,
        "duration": duration,
    }
    if payload["image"] is None:
        payload.pop("image")
    if dry:
        shown = dict(payload)
        shown["image"] = f"<data URI of {source.name}>" if source.exists() else "<absent>"
        print(f"    DRY POST /videos/generations -> {out.name}")
        print(f"        prompt: {prompt[:150]}...")
        print(f"        duration: {duration}s  image: {shown['image']}")
        return

    res = call("POST", "/videos/generations", payload)
    rid = res.get("request_id") or res.get("id")
    if not rid:
        raise RuntimeError(f"no request_id in response: {json.dumps(res)[:400]}")
    print(f"    queued {out.name} request_id={rid}")

    for attempt in range(poll_max):
        time.sleep(poll_every)
        st = call("GET", f"/videos/{rid}")
        status = (st.get("status") or "").lower()
        if status in {"done", "succeeded", "completed"}:
            url = (st.get("video") or {}).get("url") or st.get("url")
            if not url:
                raise RuntimeError(f"done but no video url: {json.dumps(st)[:400]}")
            blob = fetch_bytes(url)
            out.write_bytes(blob)
            print(f"    ok {out.name} ({len(blob) // 1024} KB)")
            return
        if status in {"failed", "expired", "error"}:
            raise RuntimeError(f"video {status}: {json.dumps(st)[:400]}")
        print(f"    .. {status or 'pending'} ({(attempt + 1) * poll_every}s)")
    raise RuntimeError(f"video {rid} still pending after {poll_every * poll_max}s")


# ---------------------------------------------------------------- driver

def main() -> int:
    ap = argparse.ArgumentParser(description="Render pop-up book assets with Grok Imagine.")
    ap.add_argument("--check", action="store_true", help="verify credentials and exit")
    ap.add_argument("--dry-run", action="store_true", help="print planned calls, contact nothing")
    ap.add_argument("--pages", default="", help="comma separated page ids, e.g. p1,p5")
    ap.add_argument("--layers", default="bg,mid,fg", help="which layers to render")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--video-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-render assets that already exist")
    ap.add_argument("--aspect", default="1536x1024", help="image size passed to the API")
    args = ap.parse_args()

    if args.check:
        try:
            res = call("GET", "/models", timeout=60)
            names = [m.get("id") for m in res.get("data", [])]
            print(f"credentials ok - {len(names)} models visible")
            for want in (IMAGE_MODEL, VIDEO_MODEL):
                print(f"  {'found  ' if want in names else 'MISSING'} {want}")
            return 0
        except RuntimeError as e:
            print(f"credential check failed:\n{e}", file=sys.stderr)
            return 1

    story = json.loads(STORY.read_text(encoding="utf-8"))
    ASSETS.mkdir(parents=True, exist_ok=True)
    wanted_pages = {p for p in args.pages.split(",") if p}
    wanted_layers = {l for l in args.layers.split(",") if l}

    manifest_path = ASSETS / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("images", {})
    manifest.setdefault("videos", {})

    failures: list[str] = []

    for page in story["pages"]:
        pid = page["id"]
        if wanted_pages and pid not in wanted_pages:
            continue
        print(f"\n[{pid}] {page['title']}")

        if not args.video_only:
            for layer in page["layers"]:
                if layer["id"] not in wanted_layers:
                    continue
                out = ASSETS / f"{pid}_{layer['id']}.jpg"
                if out.exists() and not args.force:
                    print(f"    skip {out.name} (exists)")
                    manifest["images"][f"{pid}_{layer['id']}"] = out.name
                    continue
                try:
                    gen_image(build_prompt(story, layer["prompt"]), out, args.aspect, args.dry_run)
                    if not args.dry_run:
                        manifest["images"][f"{pid}_{layer['id']}"] = out.name
                except RuntimeError as e:
                    print(f"    FAIL {out.name}: {e}", file=sys.stderr)
                    failures.append(f"{pid}/{layer['id']}")

        if not args.no_video and page.get("video"):
            out = ASSETS / f"{pid}.mp4"
            src = ASSETS / f"{pid}_{page['video'].get('from', 'bg')}.jpg"
            if out.exists() and not args.force:
                print(f"    skip {out.name} (exists)")
                manifest["videos"][pid] = out.name
            elif not src.exists() and not args.dry_run:
                print(f"    skip {out.name} (source {src.name} missing - render images first)")
            else:
                try:
                    gen_video(build_prompt(story, page["video"]["prompt"]), src, out,
                              int(page["video"].get("duration", 6)), args.dry_run)
                    if not args.dry_run:
                        manifest["videos"][pid] = out.name
                except RuntimeError as e:
                    print(f"    FAIL {out.name}: {e}", file=sys.stderr)
                    failures.append(f"{pid}/video")

    if not args.dry_run:
        manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest["models"] = {"image": IMAGE_MODEL, "video": VIDEO_MODEL}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        print(f"\nmanifest: {len(manifest['images'])} images, {len(manifest['videos'])} videos"
              f" -> {manifest_path.relative_to(ROOT)}")
        print("next: python3 scripts/build_book.py")

    if failures:
        print(f"\n{len(failures)} asset(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
