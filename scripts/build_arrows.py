#!/usr/bin/env python3
"""Build arrows/index.html from the story and whatever assets actually exist.

Reads story/red-cliff-arrows.json for the running order and the Chinese text,
scans arrows/assets/ for each page's still and clips, and inlines the result
into arrows/template.html. Nothing is fetched at runtime, so the page opens
from disk as well as over a server.

A page contributes whatever it has:
    {id}.jpg          still          (required — no still, no page)
    {id}_ambient.mp4  gentle loop    (optional — falls back to the still)
    {id}_turn.mp4     page flips up  (optional — falls back to a plain fade)
    {id}_rise.mp4     scene appears  (optional — falls back to a plain fade)

  python3 scripts/build_arrows.py [--ids cover,c1,c2]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORY = ROOT / "story" / "red-cliff-arrows.json"
ASSETS = ROOT / "arrows" / "assets"
TEMPLATE = ROOT / "arrows" / "template.html"
OUT = ROOT / "arrows" / "index.html"
MIN_IMG, MIN_VID = 20_000, 100_000


def usable(p: Path, floor: int) -> str | None:
    return p.name if p.exists() and p.stat().st_size >= floor else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="restrict to these pages, in this order")
    args = ap.parse_args()

    story = json.loads(STORY.read_text(encoding="utf-8"))
    order = [("cover", story["cover"], "", story.get("title", "")) ] + [
        (c["id"], c, str(i), c["title"]) for i, c in enumerate(story["chapters"], 1)
    ]
    if args.ids:
        want = [x for x in args.ids.split(",") if x]
        order = [u for u in order if u[0] in want]
        order.sort(key=lambda u: want.index(u[0]))

    pages, missing = [], []
    for uid, src, no, title in order:
        still = usable(ASSETS / f"{uid}.jpg", MIN_IMG)
        if not still:
            missing.append(uid)
            continue
        pages.append({
            "id": uid, "no": no, "title": title,
            "text": src.get("text", ""),
            "still": still,
            "ambient": usable(ASSETS / f"{uid}_ambient.mp4", MIN_VID),
            "turn": usable(ASSETS / f"{uid}_turn.mp4", MIN_VID),
            "rise": usable(ASSETS / f"{uid}_rise.mp4", MIN_VID),
        })

    data = {"title": story.get("title", ""), "subtitle": story.get("subtitle", ""), "pages": pages}
    html = TEMPLATE.read_text(encoding="utf-8")
    token = "/*__DATA__*/ {title:\"草船借箭\",subtitle:\"\",pages:[]}"
    if token not in html:
        raise SystemExit("template is missing the /*__DATA__*/ placeholder")
    OUT.write_text(html.replace(token, json.dumps(data, ensure_ascii=False)), encoding="utf-8")

    have = lambda k: sum(1 for p in pages if p[k])
    print(f"built {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
    print(f"  {len(pages)} pages: {', '.join(p['id'] for p in pages)}")
    print(f"  ambient {have('ambient')}/{len(pages)}   turn {have('turn')}/{len(pages)}   rise {have('rise')}/{len(pages)}")
    if missing:
        print(f"  skipped (no still yet): {', '.join(missing)}")


if __name__ == "__main__":
    main()
