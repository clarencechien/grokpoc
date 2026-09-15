#!/usr/bin/env python3
"""Assemble the book: for each spread, its ambient clip, then its page-turn clip (which
ends on the blank book), cross-faded into the next spread's ambient clip so the next
diorama appears to surface on the page.

  {id}_ambient.mp4  : spread {id} with gentle motion (first frame = {id}.jpg)
  {id}_turn.mp4     : spread {id}'s near page flips up over the hinge, ending blank
  -> arrows/assets/book.mp4

All clips come from the same master, so a plain opacity fade reads as the scene
materialising on the page. Missing clips are skipped, not faked.

  python3 scripts/arrows_compose.py --ids cover,c1 [--fade 1.5]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "arrows" / "assets"
W, H, FPS = 1280, 720, 24


def dur(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def norm(src: Path, dst: Path) -> Path:
    """Same size / fps / pixel format so xfade and concat behave."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                    "-vf", f"scale={W}:{H},fps={FPS},format=yuv420p", "-an",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(dst)], check=True)
    return dst


def still_hold(img: Path, dst: Path, seconds: float) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(img), "-t", str(seconds),
                    "-vf", f"scale={W}:{H},fps={FPS},format=yuv420p", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "18", str(dst)], check=True)
    return dst


def xfade(a: Path, b: Path, dst: Path, fade: float) -> Path:
    off = max(dur(a) - fade, 0)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(a), "-i", str(b),
                    "-filter_complex", f"[0:v][1:v]xfade=transition=fade:duration={fade}:offset={off:.3f}[v]",
                    "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-pix_fmt", "yuv420p", str(dst)], check=True)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="spread order, e.g. cover,c1,c2")
    ap.add_argument("--fade", type=float, default=1.5)
    ap.add_argument("--hold", type=float, default=4.0, help="still hold when an ambient clip is missing")
    ap.add_argument("--out", default="book.mp4")
    args = ap.parse_args()
    ids = [x for x in args.ids.split(",") if x]
    tmp = ASSETS / "_compose"; tmp.mkdir(exist_ok=True)

    timeline: list[Path] = []  # alternating: ambient(id), turn(id), ambient(next) ...
    for i, uid in enumerate(ids):
        amb = ASSETS / f"{uid}_ambient.mp4"
        if amb.exists():
            timeline.append(norm(amb, tmp / f"{uid}_amb.mp4"))
            print(f"  {uid}: ambient {dur(amb):.1f}s")
        elif (ASSETS / f"{uid}.jpg").exists():
            timeline.append(still_hold(ASSETS / f"{uid}.jpg", tmp / f"{uid}_amb.mp4", args.hold))
            print(f"  {uid}: no ambient clip — holding still {args.hold}s")
        else:
            print(f"  {uid}: missing {uid}.jpg, skipped"); continue
        if i < len(ids) - 1:
            turn = ASSETS / f"{uid}_turn.mp4"
            if turn.exists():
                timeline.append(norm(turn, tmp / f"{uid}_turn.mp4"))
                print(f"  {uid}: turn {dur(turn):.1f}s")
            else:
                print(f"  {uid}: no turn clip — will fade straight into the next spread")

    if not timeline:
        print("nothing to assemble", file=sys.stderr); return 1
    # fold left with cross-fades; a turn clip ends blank, so the fade INTO the next
    # ambient is the "surfacing" moment, while ambient->turn is a plain cut-fade.
    acc = timeline[0]
    for j, nxt in enumerate(timeline[1:], 1):
        acc = xfade(acc, nxt, tmp / f"acc_{j}.mp4", args.fade)
    out = ASSETS / args.out
    out.write_bytes(acc.read_bytes())
    print(f"\n{out.relative_to(ROOT)}  {dur(out):.1f}s  {out.stat().st_size//1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
