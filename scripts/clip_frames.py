#!/usr/bin/env python3
"""Extract an evenly-spaced contact sheet from a clip, to check what actually moves.

The repo has no system ffmpeg, but Playwright ships one; this finds it.

  python3 scripts/clip_frames.py arrows/assets/c1.mp4 --n 8 --out /tmp/c1_sheet.jpg
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path


def find_ffmpeg() -> str:
    for cand in [shutil.which("ffmpeg"), *glob.glob("/opt/pw-browsers/ffmpeg-*/ffmpeg-linux")]:
        if cand and Path(cand).exists():
            return cand
    sys.exit("no ffmpeg found (looked on PATH and in /opt/pw-browsers/ffmpeg-*)")


def duration(ff: str, src: Path) -> float:
    # ffprobe is not shipped alongside; parse ffmpeg's own stderr banner instead.
    out = subprocess.run([ff, "-i", str(src)], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    sys.exit(f"could not read duration from {src}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--n", type=int, default=8, help="how many frames to sample")
    ap.add_argument("--out", default="", help="contact sheet path (default: <clip>_sheet.jpg)")
    ap.add_argument("--width", type=int, default=480, help="per-tile width")
    args = ap.parse_args()

    ff = find_ffmpeg()
    src = Path(args.clip)
    if not src.exists():
        sys.exit(f"missing {src}")
    dur = duration(ff, src)
    out = Path(args.out) if args.out else src.with_name(src.stem + "_sheet.jpg")

    cols = min(args.n, 4)
    rows = (args.n + cols - 1) // cols
    # sample just inside the clip so the first and last frames are real content
    fps = args.n / max(dur - 0.05, 0.1)
    cmd = [ff, "-y", "-i", str(src),
           "-vf", f"fps={fps:.4f},scale={args.width}:-1,tile={cols}x{rows}",
           "-frames:v", "1", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        sys.exit(f"ffmpeg failed:\n{r.stderr[-800:]}")

    print(json.dumps({"clip": str(src), "duration_s": round(dur, 2),
                      "frames": args.n, "grid": f"{cols}x{rows}",
                      "sheet": str(out), "sheet_kb": out.stat().st_size // 1024}, indent=2))


if __name__ == "__main__":
    main()
