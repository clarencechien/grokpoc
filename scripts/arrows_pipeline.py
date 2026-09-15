#!/usr/bin/env python3
"""草船借箭 pop-up book — the whole pipeline as staged, resumable steps.

Single source of truth: story/red-cliff-arrows.json (prompts, cast, per-chapter
cast lists, motion templates). This script only orchestrates and verifies.
Low-level calls (grok CLI image_gen / image_edit / image_to_video) live in
arrows_gen.py; assembly lives in arrows_compose.py.

Stages, in order (each skips outputs that already exist unless --force):

  refs     ref_cast.jpg (image_gen)      the chibi character sheet
           ref_spread_blank.jpg (gen)    the empty old book, open at 90 degrees  <- MASTER
           ref_cover_closed.jpg (edit)   derived from the master
  sheets   cast/<slot>.jpg               ffmpeg crops of the character sheet
           cast/sheet_<id>.jpg           per-scene sheet: ONLY that scene's characters
  spreads  <id>.jpg                      multi-image edit [master, scene sheet]
  clips    <id>_turn.mp4                 near page flips up over the hinge, ends blank
           <id>_collapse.mp4 -> _rise    scene folds flat; reversed = scene rises from blank
           <id>_ambient.mp4              one gentle motion (video.beat)
  compose  book.mp4                      ambient -> turn -> rise -> ambient ... (xfade)
  publish  re-encode in place            720p crf27 +faststart; keeps <name>.orig.* beside
  check    contact sheets + a pass/fail table for everything above

Usage
  python3 scripts/arrows_pipeline.py check                 # what exists, what is wrong
  python3 scripts/arrows_pipeline.py refs                  # step 1 (then LOOK at them)
  python3 scripts/arrows_pipeline.py sheets
  python3 scripts/arrows_pipeline.py spreads --ids cover,c1
  python3 scripts/arrows_pipeline.py clips   --ids cover,c1
  python3 scripts/arrows_pipeline.py compose --ids cover,c1
  python3 scripts/arrows_pipeline.py all     --ids cover,c1
  add --dry-run to print every prompt without calling anything.

Rules learned the hard way (do not skip):
  * Look at every reference image before generating anything from it — all
    spreads inherit the master's camera, light and book; a bad master is a bad book.
  * One new element per edit. Ask for the open book first, then the diorama.
  * Put ONLY a scene's characters in its reference sheet; text whitelists do not
    stop the model from copying everyone on a full sheet.
  * grok image_to_video pins the FIRST frame only, so the page turn is generated
    from the spread and the reveal is a reversed collapse clip (both ends pinned).
  * Pass resolution 720p explicitly (arrows_gen does); the default is 480p.
  * Never pkill by a pattern that matches your own shell command line.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arrows_gen as G  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STORY = ROOT / "story" / "red-cliff-arrows.json"
ASSETS = ROOT / "arrows" / "assets"
MIN_IMG, MIN_VID = 20_000, 100_000


# ---------------------------------------------------------------- helpers

def load() -> dict:
    return json.loads(STORY.read_text(encoding="utf-8"))


def units(story: dict, ids: set[str]) -> list[tuple[str, dict]]:
    out = [("cover", story["cover"])] + [(c["id"], c) for c in story["chapters"]]
    return [(u, d) for u, d in out if not ids or u in ids]


def have(p: Path, min_bytes: int) -> bool:
    return p.exists() and p.stat().st_size >= min_bytes


def probe(p: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(p)],
                       capture_output=True, text=True)
    try:
        j = json.loads(r.stdout); s = j["streams"][0]
        return {"w": s.get("width"), "h": s.get("height"), "fps": s.get("r_frame_rate"),
                "dur": float(j.get("format", {}).get("duration", 0))}
    except Exception:
        return {}


def contact_sheet(clip: Path, n: int = 12) -> Path:
    out = ASSETS / "_check" / f"{clip.stem}_sheet.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "clip_frames.py"), str(clip), "--n", str(n),
                    "--width", "400", "--out", str(out)], capture_output=True, text=True)
    return out


# ---------------------------------------------------------------- stages

def stage_refs(story: dict, dry: bool, force: bool) -> bool:
    ok = True
    for key in ("cast", "spread_blank", "cover_closed"):
        r = story["refs"][key]; out = ASSETS / r["file"]
        print(f"\n[refs:{key}] -> {out.name}")
        if r.get("from"):
            ok &= G.make_edit(r["prompt"], ASSETS / r["from"], out, dry, force, 420)
        else:
            ok &= G.make_image(r["prompt"], out, "16:9", dry, force, 420)
    print("\nNow LOOK at the three references before continuing (camera, light, torn pages, 90-degree hinge).")
    return ok


def stage_sheets(story: dict, ids: set[str], dry: bool, force: bool) -> bool:
    cast_dir = ASSETS / "cast"; cast_dir.mkdir(exist_ok=True)
    src = ASSETS / story["refs"]["cast"]["file"]
    if not src.exists():
        print("missing", src.name); return False
    w = story["cast_slot_width"]
    for slot, x in story["cast_slots"].items():
        out = cast_dir / f"{slot}.jpg"
        if out.exists() and not force:
            continue
        if dry:
            print(f"  DRY crop {slot} x={x}"); continue
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", f"crop={w}:720:{x}:0", str(out)], check=True)
    for uid, u in units(story, ids):
        out = ASSETS / u["sheet"]
        parts = [cast_dir / f"{s}.jpg" for s in u["cast_list"]]
        if out.exists() and not force:
            print(f"  skip {out.name}"); continue
        if dry:
            print(f"  DRY sheet {uid}: {' + '.join(u['cast_list'])}"); continue
        cmd = ["ffmpeg", "-v", "error", "-y"]
        for p in parts:
            cmd += ["-i", str(p)]
        cmd += ["-filter_complex", f"hstack=inputs={len(parts)}" if len(parts) > 1 else "null", str(out)]
        subprocess.run(cmd, check=True)
        print(f"  ok  {out.name}: {' + '.join(u['cast_list'])}")
    return True


def stage_spreads(story: dict, ids: set[str], dry: bool, force: bool) -> bool:
    master = ASSETS / story["refs"]["spread_blank"]["file"]
    ok = True
    for uid, u in units(story, ids):
        out = ASSETS / f"{uid}.jpg"
        sheet = ASSETS / u["sheet"]
        limit = f"Only these characters appear: {u['only']}."
        prompt = story["scene_edit"].format(scene=u["prompt"], only=limit)
        print(f"\n[spread:{uid}]")
        ok &= G.make_multi_edit(prompt, [master, sheet], out, "16:9", dry, force, 420)
    print("\nNow LOOK at each spread: count the figures, check the expression, check the book is unchanged.")
    return ok


def stage_clips(story: dict, ids: set[str], dry: bool, force: bool) -> bool:
    ok = True
    for uid, u in units(story, ids):
        still = ASSETS / f"{uid}.jpg"
        if not still.exists() and not dry:
            print(f"[{uid}] missing {still.name}, run spreads first"); ok = False; continue
        print(f"\n[clips:{uid}]")
        ok &= G.make_video(story["turn_motion"], still, ASSETS / f"{uid}_turn.mp4", 6, dry, force, 900)
        coll = ASSETS / f"{uid}_collapse.mp4"
        ok &= G.make_video(story["collapse_motion"], still, coll, 6, dry, force, 900)
        rise = ASSETS / f"{uid}_rise.mp4"
        if not dry and coll.exists() and (force or not rise.exists()):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(coll), "-vf",
                            "reverse,scale=1280:720,fps=24,format=yuv420p", "-an", "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "18", str(rise)], check=True)
            print(f"    ok  {rise.name} (reversed collapse)")
        elif dry:
            print(f"    DRY reverse {coll.name} -> {rise.name}")
        beat = (u.get("video") or {}).get("beat", "")
        ok &= G.make_video(story["ambient_motion"].format(beat=beat), still, ASSETS / f"{uid}_ambient.mp4",
                           6, dry, force, 900)
    return ok


def stage_compose(ids: list[str], dry: bool) -> bool:
    if dry:
        print(f"DRY compose --ids {','.join(ids)}"); return True
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "arrows_compose.py"), "--ids", ",".join(ids),
                        "--fade", "0.8", "--out", "book.mp4"], text=True, capture_output=True)
    print(r.stdout[-600:]); return r.returncode == 0



def stage_publish(story: dict, ids: set[str], dry: bool, force: bool) -> bool:
    """Re-encode clips and stills for the web: smaller, faststart, same names in dist/.

    Originals stay untouched in arrows/assets/; the site serves arrows/assets/ too,
    so publishing overwrites in place only when --force is given (we keep a copy of
    the original beside it the first time, as <name>.orig.mp4, so it is reversible).
    """
    total_before = total_after = 0
    for uid, _ in units(story, ids):
        for name in (f"{uid}_turn.mp4", f"{uid}_rise.mp4", f"{uid}_ambient.mp4"):
            src = ASSETS / name
            if not have(src, MIN_VID):
                continue
            orig = src.with_suffix(".orig.mp4")
            before = src.stat().st_size
            if orig.exists() and not force:
                print(f"  skip {name} (already published, {before // 1024} KB)")
                total_before += before; total_after += before
                continue
            if dry:
                print(f"  DRY re-encode {name} ({before // 1024} KB)"); continue
            if not orig.exists():
                orig.write_bytes(src.read_bytes())
            tmp = src.with_suffix(".tmp.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(orig),
                            "-vf", "scale=1280:720:flags=lanczos", "-r", "24",
                            "-c:v", "libx264", "-profile:v", "high", "-preset", "slow",
                            "-crf", "27", "-pix_fmt", "yuv420p", "-an",
                            "-movflags", "+faststart", str(tmp)], check=True)
            tmp.replace(src)
            after = src.stat().st_size
            total_before += before; total_after += after
            print(f"  ok  {name}  {before // 1024} KB -> {after // 1024} KB")
        still = ASSETS / f"{uid}.jpg"
        if have(still, MIN_IMG) and not dry:
            orig = still.with_suffix(".orig.jpg")
            if not orig.exists() or force:
                if not orig.exists():
                    orig.write_bytes(still.read_bytes())
                tmp = still.with_suffix(".tmp.jpg")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(orig),
                                "-vf", "scale=1280:-1:flags=lanczos", "-q:v", "4", str(tmp)], check=True)
                tmp.replace(still)
    if not dry and total_before:
        print(f"\nvideo total {total_before // 1024 // 1024} MB -> {total_after // 1024 // 1024} MB")
    return True


def stage_check(story: dict, ids: set[str]) -> bool:
    rows: list[tuple[str, str, str]] = []
    def img(p: Path, label: str):
        if have(p, MIN_IMG):
            pr = probe(p); rows.append((label, "ok", f"{pr.get('w')}x{pr.get('h')}"))
        else:
            rows.append((label, "MISSING", ""))
    def vid(p: Path, label: str):
        if not have(p, MIN_VID):
            rows.append((label, "MISSING", "")); return
        pr = probe(p); bad = []
        if (pr.get("w"), pr.get("h")) != (1280, 720): bad.append(f"{pr.get('w')}x{pr.get('h')} (want 1280x720 — 480p default?)")
        if not 5.5 <= pr.get("dur", 0) <= 10.5: bad.append(f"dur {pr.get('dur'):.1f}s")
        rows.append((label, "BAD" if bad else "ok", "; ".join(bad) or f"{pr['dur']:.1f}s"))
        contact_sheet(p)
    for key in ("cast", "spread_blank", "cover_closed"):
        img(ASSETS / story["refs"][key]["file"], f"ref {key}")
    for uid, u in units(story, ids):
        img(ASSETS / u["sheet"], f"{uid} sheet")
        img(ASSETS / f"{uid}.jpg", f"{uid} spread")
        for k in ("turn", "collapse", "rise", "ambient"):
            vid(ASSETS / f"{uid}_{k}.mp4", f"{uid} {k}")
    width = max(len(r[0]) for r in rows)
    bad = 0
    for label, status, note in rows:
        bad += status != "ok"
        print(f"  {label:<{width}}  {status:<8} {note}")
    print(f"\n{len(rows) - bad}/{len(rows)} ok; contact sheets in arrows/assets/_check/ — open them and look.")
    return bad == 0


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["refs", "sheets", "spreads", "clips", "compose", "publish", "check", "all"])
    ap.add_argument("--ids", default="", help="cover,c1,... (default: every unit)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    story = load(); ASSETS.mkdir(parents=True, exist_ok=True)
    ids = {x for x in a.ids.split(",") if x}
    order = [u for u, _ in units(story, ids)]

    ok = True
    if a.stage in ("refs", "all"):      ok &= stage_refs(story, a.dry_run, a.force)
    if a.stage in ("sheets", "all"):    ok &= stage_sheets(story, ids, a.dry_run, a.force)
    if a.stage in ("spreads", "all"):   ok &= stage_spreads(story, ids, a.dry_run, a.force)
    if a.stage in ("clips", "all"):     ok &= stage_clips(story, ids, a.dry_run, a.force)
    if a.stage in ("compose", "all"):   ok &= stage_compose(order, a.dry_run)
    if a.stage == "publish":            ok &= stage_publish(story, ids, a.dry_run, a.force)
    if a.stage in ("check", "all") and not a.dry_run:
        ok &= stage_check(story, ids)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
