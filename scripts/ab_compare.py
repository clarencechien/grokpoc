#!/usr/bin/env python3
"""c7 A/B: Grok CLI clips vs Gemini Omni 1.1 Flash clips — same inputs, same checks.

Programmatic checks only (grok-learned.md §16: code does the judging, eyes do the rest):
  size / fps / frames / audio      what came back
  first / last                     mean abs diff (0-255) of frame 0 / last frame vs the image
                                   that end was supposed to be; lower = that end is pinned
  rim                              max drift of the table+wall around the book vs frame 0
                                   (camera or book moving)
  peaks                            bursts of motion energy (a "turn" should be one)
Writes arrows/ab_omni/sheet_<test>.jpg (Grok row over Omni row) and metrics.json.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "arrows" / "assets"
O = ROOT / "arrows" / "ab_omni"
SM = (320, 180)

TESTS = {
    "rise": {
        "want": ("ref_spread_blank.jpg", "c7.jpg"),
        "grok": ["c7_rise.mp4"], "omni": ["omni_c7_rise.mp4"],
        "note": "blank book -> c7 pop-up stands up (Grok: reversed collapse clip)",
    },
    "turn": {
        "want": ("c7.jpg", "ref_spread_blank.jpg"),
        "grok": ["c7_turn.mp4"], "omni": ["omni_c7_turn.mp4"],
        "note": "c7 page turns away, book ends blank (Grok: first frame only)",
    },
    "ambient": {
        "want": ("c7.jpg", "c7.jpg"),
        "grok": ["c7_ambient.mp4"], "omni": ["omni_c7_ambient.mp4"],
        "note": "arrows keep falling, nothing else moves",
    },
    "direct": {
        "want": ("c6.jpg", "c7.jpg"),
        "grok": ["c6_turn.mp4", "c7_rise.mp4"], "omni": ["omni_c6_to_c7_a.mp4"],
        "note": "c6 -> c7 in one shot (Grok needs turn + rise + xfade)",
    },
    "direct_reroll": {
        "want": ("c6.jpg", "c7.jpg"),
        "grok": ["c6_turn.mp4", "c7_rise.mp4"], "omni": ["omni_c6_to_c7_b.mp4"],
        "note": "same prompt and frames as 'direct', second roll",
    },
}


def frames(p: Path) -> tuple[list[np.ndarray], float]:
    cap = cv2.VideoCapture(str(p))
    fps = cap.get(cv2.CAP_PROP_FPS)
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    return out, fps


def has_audio(p: Path) -> bool:
    import imageio_ffmpeg
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(p)], capture_output=True, text=True)
    return bool(re.search(r"Stream #\S+: Audio", r.stderr))


def small(a: np.ndarray) -> np.ndarray:
    return cv2.resize(a, SM, interpolation=cv2.INTER_AREA).astype(np.float32)


def dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(small(a) - small(b)).mean())


RIM = np.zeros((SM[1], SM[0]), bool)
RIM[:, :55] = True
RIM[:, -55:] = True
RIM[:8, :] = True


def metrics(fr: list[np.ndarray], fps: float, first: np.ndarray, last: np.ndarray, path_list) -> dict:
    s = [small(f) for f in fr]
    rim = max(float(np.abs(x - s[0])[RIM].mean()) for x in s)
    energy = np.array([np.abs(s[i] - s[i - 1]).mean() for i in range(1, len(s))])
    k = max(1, int(fps / 4))
    e = np.convolve(energy, np.ones(k) / k, mode="same")
    thr = max(1.0, 0.35 * e.max())
    peaks = int(((e[1:] >= thr) & (e[:-1] < thr)).sum() + (e[0] >= thr))
    return {
        "size": f"{fr[0].shape[1]}x{fr[0].shape[0]}", "fps": round(fps, 2), "frames": len(fr),
        "seconds": round(len(fr) / fps, 2), "audio": any(has_audio(p) for p in path_list),
        "first": round(dist(fr[0], first), 1), "last": round(dist(fr[-1], last), 1),
        "rim": round(rim, 1), "peaks": peaks,
    }


def strip(fr: list[np.ndarray], n: int, label: str, w: int = 200) -> Image.Image:
    idx = [round(i * (len(fr) - 1) / (n - 1)) for i in range(n)]
    h = int(w * 9 / 16)
    im = Image.new("RGB", (n * w, h + 18), (14, 16, 24))
    d = ImageDraw.Draw(im)
    for j, i in enumerate(idx):
        im.paste(Image.fromarray(fr[i]).resize((w, h)), (j * w, 18))
    d.text((6, 3), label, fill=(240, 220, 170))
    return im


def main() -> int:
    report = {}
    for name, t in TESTS.items():
        want = [np.asarray(Image.open(A / f).convert("RGB")) for f in t["want"]]
        rows, report[name] = [], {"note": t["note"]}
        for side in ("grok", "omni"):
            paths = [(A if side == "grok" else O) / f for f in t[side]]
            fr, fps = [], 24.0
            for p in paths:
                f, fps = frames(p)
                fr += f
            m = metrics(fr, fps, want[0], want[1], paths)
            report[name][side] = m
            label = f"{side.upper()}  {' + '.join(t[side])}   first {m['first']}  last {m['last']}  rim {m['rim']}  peaks {m['peaks']}"
            rows.append(strip(fr, 10, label))
        ref = Image.new("RGB", (rows[0].width, 130), (14, 16, 24))
        for j, f in enumerate(t["want"]):
            ref.paste(Image.open(A / f).resize((200, 112)), (j * (rows[0].width - 200), 18))
        ImageDraw.Draw(ref).text((210, 3), f"{name}: {t['note']}   (left: wanted first frame, right: wanted last frame)", fill=(200, 200, 210))
        sheet = Image.new("RGB", (rows[0].width, ref.height + sum(r.height for r in rows)))
        y = 0
        for r in [ref] + rows:
            sheet.paste(r, (0, y))
            y += r.height
        sheet.save(O / f"sheet_{name}.jpg", quality=85)
    (O / "metrics.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"{'test':15}{'side':6}{'size':>10}{'sec':>6}{'aud':>5}{'first':>7}{'last':>7}{'rim':>6}{'peaks':>6}")
    for name, r in report.items():
        for side in ("grok", "omni"):
            m = r[side]
            print(f"{name:15}{side:6}{m['size']:>10}{m['seconds']:>6}{str(m['audio'])[0]:>5}{m['first']:>7}{m['last']:>7}{m['rim']:>6}{m['peaks']:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
