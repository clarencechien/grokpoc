#!/usr/bin/env python3
"""Render the 草船借箭 pop-up book through OpenRouter.

Images : Nano Banana 2 (google/gemini-3.1-flash-image) via /chat/completions.
         Multi-image reference input keeps the book, camera and cast locked.
Video  : Veo 3.1 Lite (google/veo-3.1-lite) via /videos, pinned with BOTH
         first_frame and last_frame — so the page turn starts and ends where
         we say it does instead of being re-imagined every run.

Why this exists: the Grok CLI's image_to_video only accepts a first frame, so a
"turn the page all the way over" motion could never be pinned shut. Every model
listed here supports last_frame.

  export or_key=sk-or-v1-...
  python3 scripts/or_gen.py --check
  python3 scripts/or_gen.py --dry-run --ids cover,c1
  python3 scripts/or_gen.py --ids cover,c1
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

API = "https://openrouter.ai/api/v1"
IMAGE_MODEL = os.environ.get("OR_IMAGE_MODEL", "google/gemini-3.1-flash-image")
VIDEO_MODEL = os.environ.get("OR_VIDEO_MODEL", "google/veo-3.1-lite")

ROOT = Path(__file__).resolve().parent.parent
STORY = ROOT / "story" / "red-cliff-arrows.json"
ASSETS = ROOT / "arrows" / "assets"
MIN_IMG, MIN_VID = 20_000, 100_000


def key() -> str:
    # An explicit key file wins: the environment may still carry a stale key.
    kf = os.environ.get("OR_KEY_FILE", "")
    if kf and Path(kf).exists():
        return Path(kf).read_text().strip()
    for var in ("or_key", "OR_KEY", "OPENROUTER_API_KEY"):
        v = os.environ.get(var, "").strip()
        if v:
            return v
    sys.exit("no OpenRouter key: set or_key, or OR_KEY_FILE to a file holding it")


def call(path: str, payload: dict | None = None, method: str = "POST", timeout: int = 300) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=body, method=method, headers={
        "Authorization": f"Bearer {key()}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {e.read().decode(errors='replace')[:500]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error {method} {path}: {e.reason}") from None


def data_uri(p: Path) -> str:
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


# ---------------------------------------------------------------- images

def gen_image(prompt: str, refs: list[Path], out: Path, dry: bool, force: bool) -> bool:
    if out.exists() and out.stat().st_size > MIN_IMG and not force:
        print(f"    skip {out.name} ({out.stat().st_size//1024} KB)")
        return True
    missing = [r for r in refs if not r.exists()]
    if missing and not dry:
        print(f"    skip {out.name} (missing refs: {', '.join(m.name for m in missing)})")
        return False
    if dry:
        print(f"    DRY image [{', '.join(r.name for r in refs) or 'no refs'}] -> {out.name}")
        print(f"        {prompt[:130]}...")
        return True

    content: list[dict] = [{"type": "text", "text": prompt}]
    for r in refs:
        content.append({"type": "image_url", "image_url": {"url": data_uri(r)}})
    res = call("/chat/completions", {
        "model": IMAGE_MODEL,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],
    })
    if "error" in res:
        print(f"    FAIL {out.name}: {json.dumps(res['error'])[:250]}")
        return False
    imgs = (res["choices"][0]["message"] or {}).get("images") or []
    if not imgs:
        print(f"    FAIL {out.name}: no image returned")
        return False
    url = imgs[0]["image_url"]["url"]
    blob = base64.b64decode(url.split(",", 1)[1]) if url.startswith("data:") else fetch(url)
    out.write_bytes(blob)
    cost = (res.get("usage") or {}).get("cost", 0)
    print(f"    ok  {out.name} ({len(blob)//1024} KB, ${cost:.4f})")
    return True


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key()}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


# ---------------------------------------------------------------- video

def gen_video(prompt: str, first: Path, last: Path | None, out: Path,
              duration: int, dry: bool, force: bool, seed: int | None = None) -> bool:
    if out.exists() and out.stat().st_size > MIN_VID and not force:
        print(f"    skip {out.name} ({out.stat().st_size//1024} KB)")
        return True
    if not first.exists() and not dry:
        print(f"    skip {out.name} (missing first frame {first.name})")
        return False
    if dry:
        ends = f"{first.name} -> {last.name}" if last else f"{first.name} -> (open)"
        print(f"    DRY video {ends} [{duration}s 720p] -> {out.name}")
        print(f"        {prompt[:130]}...")
        return True

    frames = [{"type": "image_url", "image_url": {"url": data_uri(first)}, "frame_type": "first_frame"}]
    if last and last.exists():
        frames.append({"type": "image_url", "image_url": {"url": data_uri(last)}, "frame_type": "last_frame"})
    payload = {
        "model": VIDEO_MODEL,
        "prompt": prompt,
        "duration": duration,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "generate_audio": False,
        "frame_images": frames,
    }
    if seed is not None:
        payload["seed"] = seed

    job = call("/videos", payload)
    jid = job.get("id")
    if not jid:
        print(f"    FAIL {out.name}: no job id — {json.dumps(job)[:250]}")
        return False
    print(f"    queued {out.name} job={jid}")

    for i in range(80):
        time.sleep(15)
        st = call(f"/videos/{jid}", method="GET", timeout=120)
        status = (st.get("status") or "").lower()
        if status in {"completed", "succeeded", "done"}:
            urls = st.get("unsigned_urls") or []
            url = urls[0] if urls else f"{API}/videos/{jid}/content?index=0"
            blob = fetch(url)
            out.write_bytes(blob)
            cost = (st.get("usage") or {}).get("cost", 0)
            print(f"    ok  {out.name} ({len(blob)//1024} KB, ${cost:.4f})")
            return True
        if status in {"failed", "error", "cancelled"}:
            print(f"    FAIL {out.name}: {json.dumps(st.get('error') or st)[:300]}")
            return False
        print(f"    .. {status or 'pending'} ({(i+1)*15}s)")
    print(f"    FAIL {out.name}: still pending after 20 min")
    return False


# ---------------------------------------------------------------- driver

def units(story: dict):
    cov = story["cover"]
    yield "cover", cov["prompt"], (cov.get("video") or {}).get("beat"), cov.get("only", "")
    for ch in story["chapters"]:
        yield ch["id"], ch["prompt"], (ch.get("video") or {}).get("beat"), ch.get("only", "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render 草船借箭 through OpenRouter.")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ids", default="")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--videos", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--duration", type=int, default=6, choices=[4, 6, 8])
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if args.check:
        info = call("/key", method="GET", timeout=60).get("data", {})
        print(f"key ok — limit ${info.get('limit')}, used ${info.get('usage')}, "
              f"remaining ${info.get('limit_remaining')}")
        print(f"image model: {IMAGE_MODEL}\nvideo model: {VIDEO_MODEL}")
        return 0

    story = json.loads(STORY.read_text(encoding="utf-8"))
    ASSETS.mkdir(parents=True, exist_ok=True)
    wanted = {x for x in args.ids.split(",") if x}
    do_img = args.stills or not args.videos
    do_vid = args.videos or not args.stills
    ref_book = ASSETS / story["refs"]["book"]["file"]
    ref_cast = ASSETS / story["refs"]["cast"]["file"]
    failures: list[str] = []

    for uid, scene, beat, only in units(story):
        if wanted and uid not in wanted:
            continue
        title = next((c["title"] for c in story["chapters"] if c["id"] == uid), "主視覺")
        print(f"\n[{uid}] {title}")
        up = ASSETS / f"{uid}_up.jpg"      # first frame: right page standing
        down = ASSETS / f"{uid}_down.jpg"  # last frame: same page lying flat
        clip = ASSETS / f"{uid}.mp4"

        if do_img:
            # Order matters. Models render an open pop-up book reliably but refuse to
            # compose one with a page already mid-turn, so build the open spread first
            # and then raise the page with a single-change edit.
            limit = f"Only these characters appear: {only}. No other named characters." if only else ""
            if not gen_image(story["or_page_down"].format(scene=scene, only=limit),
                             [ref_book, ref_cast], down, args.dry_run, args.force):
                failures.append(f"{uid}/down")
            if not gen_image(story["or_page_up"], [down], up, args.dry_run, args.force):
                failures.append(f"{uid}/up")

        if do_vid:
            motion = f"{story['or_turn_motion']} {beat}." if beat else story["or_turn_motion"]
            if not gen_video(motion, up, down, clip, args.duration,
                             args.dry_run, args.force, args.seed):
                failures.append(f"{uid}/clip")

    if failures:
        print(f"\n{len(failures)} failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\ndone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
