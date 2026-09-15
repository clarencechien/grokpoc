#!/usr/bin/env python3
"""《草船借箭》— image-to-video route via the Grok Build CLI agent.

Different model from the pop-up book: each chapter is ONE still (image_gen) that
is then animated into ONE clip (image_to_video), with the page-turn baked INTO
the video (see the story's `turn` prefix). The web page only scrolls between
clips — there is no CSS 3D here.

No XAI_API_KEY needed — uses the logged-in `grok` agent. Resumable (skips assets
that already exist and clear the size threshold). Maintains arrows/assets/manifest.json
in the same shape build_arrows.py expects.

Usage
  grok login
  python3 scripts/arrows_gen.py --check
  python3 scripts/arrows_gen.py --dry-run
  python3 scripts/arrows_gen.py --stills        # only the still images
  python3 scripts/arrows_gen.py --videos        # only the clips (needs stills)
  python3 scripts/arrows_gen.py --ids cover,c1  # a subset
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORY = ROOT / "story" / "red-cliff-arrows.json"
ASSETS = ROOT / "arrows" / "assets"
GROK = "grok"

MIN_IMAGE_BYTES = 8 * 1024
MIN_VIDEO_BYTES = 24 * 1024


def run_agent(instruction: str, timeout: int) -> tuple[bool, str]:
    try:
        p = subprocess.run([GROK, "--always-approve", "-p", instruction],
                           cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except FileNotFoundError:
        sys.exit("`grok` not found on PATH. Install it and run `grok login` first.")
    return p.returncode == 0, ((p.stdout or "") + (p.stderr or "")).strip()[-600:]


def img_prompt(story: dict, prompt: str, only: str = "") -> str:
    # The still is frame 0 of the clip, so the page being turned has to exist HERE.
    # image_to_video only animates what is already in the source image.
    # `only` keeps the shared cast block from leaking extra characters into a scene.
    cast_limit = (f" Only these characters appear in this scene: {only}. "
                  f"No other named characters anywhere in the frame.") if only else ""
    return (f"A pop-up book spread whose paper diorama shows: {prompt}. "
            f"{story['page_still']}. Style: {story['style']}. {story['cast']}{cast_limit}")


def vid_prompt(story: dict, motion: str) -> str:
    # The clip completes the turn the still set up, then plays the scene's own motion.
    return f"{story['page_motion']} {motion}. Style: {story['style']}. {story['cast']}"


def multi_edit_instruction(prompt: str, sources: list[Path], out: Path, aspect: str) -> str:
    refs = ", ".join(str(p) for p in sources)
    return (f"Use your image_edit tool with these reference images, in this order: {refs}. "
            f"Apply the prompt below and save the result to {out}. Overwrite if it exists. "
            f"Aspect ratio {aspect}. Do not modify the prompt. Do not ask questions; edit and save."
            f"\n\nPrompt: {prompt}\n\nWhen finished, print only: SAVED {out}")


def make_multi_edit(prompt: str, sources: list[Path], out: Path, aspect: str,
                    dry: bool, force: bool, timeout: int) -> bool:
    if out.exists() and out.stat().st_size > 20_000 and not force:
        print(f"    skip {out.name} ({out.stat().st_size//1024} KB)"); return True
    if dry:
        print(f"    DRY image_edit [{', '.join(p.name for p in sources)}] -> {out.name}"); return True
    missing = [p for p in sources if not p.exists()]
    if missing:
        print(f"    skip {out.name} (missing refs: {', '.join(p.name for p in missing)})"); return False
    ok, tail = run_agent(multi_edit_instruction(prompt, sources, out, aspect), timeout)
    if ok and out.exists() and out.stat().st_size > 20_000:
        print(f"    ok  {out.name} ({out.stat().st_size//1024} KB)"); return True
    print(f"    FAIL {out.name}: {tail[-200:]}")
    return False


def last_frame(clip: Path, out: Path) -> bool:
    """Grab a clip's final frame — the imagine skill's way to make the next shot continuous."""
    import subprocess
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", str(clip),
                        "-update", "1", "-q:v", "2", str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        print(f"    FAIL last-frame: {r.stderr[-200:]}"); return False
    print(f"    ok  {out.name} (last frame of {clip.name})")
    return True


def edit_instruction(prompt: str, source: Path, out: Path) -> str:
    return (f"Use your image_edit tool with the source image {source} and the prompt below, then "
            f"save the result to {out}. Overwrite if it exists. Do not modify the prompt. "
            f"Do not ask questions; edit and save.\n\n"
            f"Prompt: {prompt}\n\nWhen finished, print only: SAVED {out}")


def make_edit(prompt: str, source: Path, out: Path, dry: bool, force: bool, timeout: int) -> bool:
    if out.exists() and out.stat().st_size > 20_000 and not force:
        print(f"    skip {out.name} ({out.stat().st_size//1024} KB)"); return True
    if dry:
        print(f"    DRY image_edit {source.name} -> {out.name}"); return True
    if not source.exists():
        print(f"    skip {out.name} (source {source.name} missing)"); return False
    ok, tail = run_agent(edit_instruction(prompt, source, out), timeout)
    if ok and out.exists() and out.stat().st_size > 20_000:
        print(f"    ok  {out.name} ({out.stat().st_size//1024} KB)"); return True
    print(f"    FAIL {out.name}: {tail[-200:]}")
    return False


def join_clips(parts: list[Path], out: Path) -> bool:
    """Concat shots with stream copy (no re-encode), per the imagine skill."""
    import subprocess, tempfile
    if not all(p.exists() for p in parts):
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        for p in parts:
            fh.write(f"file '{p.resolve()}'\n")
        listing = fh.name
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                        "-i", listing, "-c", "copy", str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        print(f"    FAIL concat: {r.stderr[-200:]}"); return False
    print(f"    ok  {out.name} ({out.stat().st_size//1024} KB, stream copy)")
    return True


def image_instruction(prompt: str, out: Path, aspect: str) -> str:
    return (f"Use your image_gen tool to generate ONE cinematic image and save it to {out} as JPEG. "
            f"Overwrite if it exists. Aspect ratio {aspect}. Do not ask questions; generate and save.\n\n"
            f"Prompt: {prompt}\n\nWhen finished, print only: SAVED {out}")


def video_instruction(motion: str, source: Path, out: Path, duration: int) -> str:
    return (f"Use your image_to_video tool with the input image {source} to animate it into a "
            f"paper pop-up book clip that OPENS by completing the page-turn already begun in "
            f"the source image, and save the MP4 to {out}. Overwrite if it exists. "
            f"Set duration={duration} and resolution_name=\"720p\" on the tool call — 720p is required, "
            f"do not leave it at the 480p default. Do not ask questions; generate and save.\n\n"
            f"Motion: {motion}\n\nWhen finished, print only: SAVED {out}")


def make_image(instr_prompt, out: Path, aspect, dry, force, timeout) -> bool:
    if out.exists() and out.stat().st_size >= MIN_IMAGE_BYTES and not force:
        print(f"    skip {out.name} ({out.stat().st_size//1024} KB)"); return True
    if dry:
        print(f"    DRY image_gen -> {out.name} [{aspect}] {instr_prompt[:80]}..."); return True
    ok, tail = run_agent(image_instruction(instr_prompt, out, aspect), timeout)
    if out.exists() and out.stat().st_size >= MIN_IMAGE_BYTES:
        print(f"    ok  {out.name} ({out.stat().st_size//1024} KB)"); return True
    print(f"    FAIL {out.name}: {'agent error' if not ok else 'no/tiny file'}\n      {tail}", file=sys.stderr)
    return False


def make_video(motion, source: Path, out: Path, duration, dry, force, timeout) -> bool:
    if out.exists() and out.stat().st_size >= MIN_VIDEO_BYTES and not force:
        print(f"    skip {out.name} ({out.stat().st_size//1024} KB)"); return True
    if dry:
        # In a real run the still is rendered in the same pass just before this,
        # so don't treat a not-yet-existing source as a failure while planning.
        print(f"    DRY image_to_video {source.name} -> {out.name} ~{duration}s"); return True
    if not source.exists():
        print(f"    skip {out.name} (source {source.name} missing — render stills first)"); return False
    ok, tail = run_agent(video_instruction(motion, source, out, duration), timeout)
    if out.exists() and out.stat().st_size >= MIN_VIDEO_BYTES:
        print(f"    ok  {out.name} ({out.stat().st_size//1024} KB)"); return True
    print(f"    FAIL {out.name}: {'agent error' if not ok else 'no/tiny file'}\n      {tail}", file=sys.stderr)
    return False


def load_manifest() -> dict:
    mp = ASSETS / "manifest.json"
    m = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    m.setdefault("images", {}); m.setdefault("videos", {})
    return m


def save_manifest(m: dict) -> None:
    m["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    m["models"] = {"image": "grok image_gen (cli)", "video": "grok image_to_video (cli)"}
    (ASSETS / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def units(story: dict):
    """Yield (id, image_prompt, motion_prompt, duration) for cover + chapters."""
    if story.get("cover"):
        cov = story["cover"]
        yield "cover", cov["prompt"], (cov.get("video") or {}).get("beat"), 6, cov.get("only", "")
    for ch in story["chapters"]:
        v = ch.get("video") or {}
        yield ch["id"], ch["prompt"], v.get("beat"), 6, ch.get("only", "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render 草船借箭 stills + clips via the Grok CLI agent.")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--refs", action="store_true", help="build the canonical book/cast references")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--videos", action="store_true")
    ap.add_argument("--ids", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--img-timeout", type=int, default=420)
    ap.add_argument("--vid-timeout", type=int, default=900)
    args = ap.parse_args()

    if args.refs:
        story = json.loads(STORY.read_text(encoding="utf-8"))
        ASSETS.mkdir(parents=True, exist_ok=True)
        rc = 0
        for key, ref in story["refs"].items():
            out = ASSETS / ref["file"]
            print(f"\n[ref:{key}]")
            prompt = ref["prompt"]
            if key != "cast":
                prompt = f"{prompt} Camera: {story['camera']}. Lighting: {story['grade']}."
            if not make_image(prompt, out, args.aspect, args.dry_run, args.force, args.img_timeout):
                rc = 1
        return rc

    if args.check:
        ok, tail = run_agent("List your media tools (image_gen, image_to_video). One line, names only. Generate nothing.", 120)
        print(tail or "(no output)"); return 0 if ok else 1

    story = json.loads(STORY.read_text(encoding="utf-8"))
    ASSETS.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    wanted = {x for x in args.ids.split(",") if x}
    do_img = args.stills or not args.videos
    do_vid = args.videos or not args.stills
    failures: list[str] = []

    for uid, iprompt, motion, dur, only in units(story):
        if wanted and uid not in wanted:
            continue
        title = next((c["title"] for c in story["chapters"] if c["id"] == uid), "主視覺")
        print(f"\n[{uid}] {title}")
        still = ASSETS / f"{uid}.jpg"
        if do_img:
            limit = (f"Only these characters appear: {only}. No other named characters." if only else "")
            scene_prompt = story["scene_edit"].format(scene=iprompt, only=limit)
            refs = [ASSETS / story["refs"]["book"]["file"], ASSETS / story["refs"]["cast"]["file"]]
            if make_multi_edit(scene_prompt, refs, still, args.aspect,
                               args.dry_run, args.force, args.img_timeout):
                if not args.dry_run and still.exists():
                    manifest["images"][uid] = still.name; save_manifest(manifest)
            else:
                failures.append(f"{uid}/img")
        if do_vid and motion:
            # Two shots, one action each (imagine skill): A = the page turn, B = the scene alive.
            open_still = ASSETS / f"{uid}_open.jpg"
            clip_a = ASSETS / f"{uid}_a.mp4"
            clip_b = ASSETS / f"{uid}_b.mp4"
            clip = ASSETS / f"{uid}.mp4"

            ok_a = make_video(story["page_motion"], still, clip_a, 6,
                              args.dry_run, args.force, args.vid_timeout)
            # Continuity: shot B starts from the exact frame shot A ended on, so the
            # camera, light and page position carry over instead of being re-imagined.
            if args.dry_run:
                print(f"    DRY last-frame {clip_a.name} -> {open_still.name}")
            elif ok_a and (args.force or not open_still.exists()):
                if not last_frame(clip_a, open_still):
                    failures.append(f"{uid}/last-frame")
            shot_b = f"{motion}. {story['scene_motion_suffix']}"
            ok_b = make_video(shot_b, open_still, clip_b, 6,
                              args.dry_run, args.force, args.vid_timeout)
            if not ok_a:
                failures.append(f"{uid}/shotA")
            if not ok_b:
                failures.append(f"{uid}/shotB")
            if args.dry_run:
                print(f"    DRY concat {clip_a.name} + {clip_b.name} -> {clip.name}")
            elif ok_a and ok_b and join_clips([clip_a, clip_b], clip):
                manifest["videos"][uid] = clip.name; save_manifest(manifest)
            else:
                failures.append(f"{uid}/join")

    if not args.dry_run:
        save_manifest(manifest)
        print(f"\nmanifest: {len(manifest['images'])} stills, {len(manifest['videos'])} clips")
        print("next: python3 scripts/build_arrows.py")
    if failures:
        print(f"\n{len(failures)} failed: {', '.join(failures)}", file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
