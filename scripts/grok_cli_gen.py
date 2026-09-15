#!/usr/bin/env python3
"""Render the pop-up book assets with the **Grok Build CLI agent** instead of the
raw Imagine API — so no XAI_API_KEY is needed, just a `grok login` session.

The logged-in agent exposes media tools (`image_gen`, `image_edit`,
`image_to_video`, `reference_to_video`). We drive it headlessly, one asset per
`grok --always-approve -p "..."` call, telling it to save to an exact path.

Same story file and same manifest.json format as scripts/grok_gen.py, so
scripts/build_book.py consumes the output unchanged. Existing assets are
skipped, so a crashed run just re-runs.

Usage
  grok login                                   # once
  python3 scripts/grok_cli_gen.py --check      # confirm the agent has media tools
  python3 scripts/grok_cli_gen.py --dry-run    # print planned calls, run nothing
  python3 scripts/grok_cli_gen.py --images     # 24 layer images + cover
  python3 scripts/grok_cli_gen.py --videos     # image-to-video for each page + cover
  python3 scripts/grok_cli_gen.py --pages p1   # just one page (images + video)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORY = ROOT / "story" / "three-little-pigs.json"
ASSETS = ROOT / "book" / "assets"
GROK = "grok"

# a freshly saved asset must clear this many bytes to count as real
MIN_IMAGE_BYTES = 8 * 1024
MIN_VIDEO_BYTES = 24 * 1024


# ---------------------------------------------------------------- agent driver

def run_agent(instruction: str, timeout: int) -> tuple[bool, str]:
    """One headless agent turn. Returns (ok, tail-of-output)."""
    try:
        p = subprocess.run(
            [GROK, "--always-approve", "-p", instruction],
            cwd=ROOT, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except FileNotFoundError:
        sys.exit("`grok` not found on PATH. Install it and run `grok login` first.")
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, out.strip()[-600:]


def build_prompt(story: dict, layer_prompt: str) -> str:
    return f"{layer_prompt}. Style: {story['style']}. {story['cast']}"


def image_instruction(prompt: str, out: Path, aspect: str) -> str:
    return (
        f"Use your image_gen tool to generate ONE image and save it to {out} as JPEG. "
        f"Overwrite if it exists. Aspect ratio {aspect}. "
        f"Do not ask questions; just generate and save.\n\nPrompt: {prompt}\n\n"
        f"When finished, print only: SAVED {out}"
    )


def video_instruction(prompt: str, source: Path, out: Path, duration: int) -> str:
    return (
        f"Use your image_to_video tool with the input image {source} to animate it, "
        f"and save the resulting MP4 to {out}. Overwrite if it exists. "
        f"Target duration about {duration} seconds, seamless gentle loop, keep the "
        f"same composition as the input image. Do not ask questions; just generate and save.\n\n"
        f"Motion prompt: {prompt}\n\nWhen finished, print only: SAVED {out}"
    )


# ---------------------------------------------------------------- asset units

def want_image(out: Path, min_bytes: int, force: bool) -> bool:
    if out.exists() and out.stat().st_size >= min_bytes and not force:
        print(f"    skip {out.name} (exists, {out.stat().st_size // 1024} KB)")
        return False
    return True


def make_image(story, prompt, out: Path, aspect, dry, force, timeout) -> bool:
    if not want_image(out, MIN_IMAGE_BYTES, force):
        return True
    if dry:
        print(f"    DRY image_gen -> {out.name}  [{aspect}]  {prompt[:90]}...")
        return True
    ok, tail = run_agent(image_instruction(prompt, out, aspect), timeout)
    if out.exists() and out.stat().st_size >= MIN_IMAGE_BYTES:
        print(f"    ok  {out.name} ({out.stat().st_size // 1024} KB)")
        return True
    print(f"    FAIL {out.name}: {'agent error' if not ok else 'no/tiny file'}\n      {tail}",
          file=sys.stderr)
    return False


def make_video(story, prompt, source: Path, out: Path, duration, dry, force, timeout) -> bool:
    if out.exists() and out.stat().st_size >= MIN_VIDEO_BYTES and not force:
        print(f"    skip {out.name} (exists, {out.stat().st_size // 1024} KB)")
        return True
    if not source.exists():
        print(f"    skip {out.name} (source {source.name} missing — render images first)")
        return False
    if dry:
        print(f"    DRY image_to_video {source.name} -> {out.name}  ~{duration}s  {prompt[:70]}...")
        return True
    ok, tail = run_agent(video_instruction(prompt, source, out, duration), timeout)
    if out.exists() and out.stat().st_size >= MIN_VIDEO_BYTES:
        print(f"    ok  {out.name} ({out.stat().st_size // 1024} KB)")
        return True
    print(f"    FAIL {out.name}: {'agent error' if not ok else 'no/tiny file'}\n      {tail}",
          file=sys.stderr)
    return False


# ---------------------------------------------------------------- driver

def load_manifest() -> dict:
    mp = ASSETS / "manifest.json"
    m = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    m.setdefault("images", {}); m.setdefault("videos", {})
    return m


def save_manifest(m: dict) -> None:
    m["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    m["models"] = {"image": "grok image_gen (cli)", "video": "grok image_to_video (cli)"}
    (ASSETS / "manifest.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render pop-up book assets via the Grok Build CLI agent.")
    ap.add_argument("--check", action="store_true", help="confirm the agent exposes media tools")
    ap.add_argument("--dry-run", action="store_true", help="print planned calls, run nothing")
    ap.add_argument("--images", action="store_true", help="only images")
    ap.add_argument("--videos", action="store_true", help="only videos")
    ap.add_argument("--pages", default="", help="comma separated ids, e.g. cover,p1")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--aspect", default="3:2")
    ap.add_argument("--img-timeout", type=int, default=420)
    ap.add_argument("--vid-timeout", type=int, default=900)
    args = ap.parse_args()

    if args.check:
        ok, tail = run_agent(
            "List exactly which media tools you have (image_gen, image_edit, "
            "image_to_video, reference_to_video). One line, names only. Generate nothing.", 120)
        print(tail if tail else "(no output)")
        return 0 if ok else 1

    story = json.loads(STORY.read_text(encoding="utf-8"))
    ASSETS.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    wanted = {p for p in args.pages.split(",") if p}
    do_img = args.images or not args.videos       # default: both
    do_vid = args.videos or not args.images
    failures: list[str] = []

    # cover / main visual
    cover = story.get("cover")
    if cover and (not wanted or "cover" in wanted):
        print("\n[cover] 主視覺")
        out = ASSETS / "cover.jpg"
        if do_img:
            if make_image(story, build_prompt(story, cover["prompt"]), out, args.aspect,
                          args.dry_run, args.force, args.img_timeout):
                if not args.dry_run and out.exists():
                    manifest["images"]["cover"] = out.name; save_manifest(manifest)
            else:
                failures.append("cover")
        if do_vid and cover.get("video"):
            vout = ASSETS / "cover.mp4"
            if make_video(story, build_prompt(story, cover["video"]["prompt"]), out, vout,
                          int(cover["video"].get("duration", 6)), args.dry_run, args.force, args.vid_timeout):
                if not args.dry_run and vout.exists():
                    manifest["videos"]["cover"] = vout.name; save_manifest(manifest)
            else:
                failures.append("cover/video")

    for page in story["pages"]:
        pid = page["id"]
        if wanted and pid not in wanted:
            continue
        print(f"\n[{pid}] {page['title']}")
        if do_img:
            for layer in page["layers"]:
                out = ASSETS / f"{pid}_{layer['id']}.jpg"
                if make_image(story, build_prompt(story, layer["prompt"]), out, args.aspect,
                              args.dry_run, args.force, args.img_timeout):
                    if not args.dry_run and out.exists():
                        manifest["images"][f"{pid}_{layer['id']}"] = out.name; save_manifest(manifest)
                else:
                    failures.append(f"{pid}/{layer['id']}")
        if do_vid and page.get("video"):
            out = ASSETS / f"{pid}.mp4"
            src = ASSETS / f"{pid}_{page['video'].get('from', 'bg')}.jpg"
            if make_video(story, build_prompt(story, page["video"]["prompt"]), src, out,
                          int(page["video"].get("duration", 6)), args.dry_run, args.force, args.vid_timeout):
                if not args.dry_run and out.exists():
                    manifest["videos"][pid] = out.name; save_manifest(manifest)
            else:
                failures.append(f"{pid}/video")

    if not args.dry_run:
        save_manifest(manifest)
        print(f"\nmanifest: {len(manifest['images'])} images, {len(manifest['videos'])} videos")
        print("next: python3 scripts/build_book.py")
    if failures:
        print(f"\n{len(failures)} failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
