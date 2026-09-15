#!/usr/bin/env python3
"""Inline the story and the asset manifest into book/template.html -> book/index.html.

The output is self-contained (no fetch at runtime), so the book opens straight
from disk with file:// as well as over a local web server.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORY = ROOT / "story" / "three-little-pigs.json"
TEMPLATE = ROOT / "book" / "template.html"
MANIFEST = ROOT / "book" / "assets" / "manifest.json"
OUT = ROOT / "book" / "index.html"


def main() -> None:
    story = json.loads(STORY.read_text(encoding="utf-8"))
    manifest = (
        json.loads(MANIFEST.read_text(encoding="utf-8"))
        if MANIFEST.exists()
        else {"images": {}, "videos": {}}
    )
    manifest.setdefault("images", {})
    manifest.setdefault("videos", {})

    # Only the viewer-relevant part of the story travels into the page; the
    # English prompts stay in the JSON so the built page stays small.
    slim = {
        "title": story["title"],
        "subtitle": story.get("subtitle", ""),
        "pages": [
            {
                "id": p["id"],
                "title": p["title"],
                "text": p["text"],
                "layers": [
                    {k: v for k, v in layer.items() if k != "prompt"}
                    for layer in p["layers"]
                ],
                "video": {"from": p["video"]["from"], "duration": p["video"]["duration"]}
                if p.get("video")
                else None,
            }
            for p in story["pages"]
        ],
    }

    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("/*__STORY__*/ null", slim), ("/*__MANIFEST__*/ {images:{}, videos:{}}", manifest)):
        if token not in html:
            raise SystemExit(f"template is missing the placeholder: {token}")
        html = html.replace(token, json.dumps(value, ensure_ascii=False))

    OUT.write_text(html, encoding="utf-8")
    print(
        f"built {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB) - "
        f"{len(slim['pages'])} pages, {len(manifest['images'])} images, "
        f"{len(manifest['videos'])} videos wired in"
    )


if __name__ == "__main__":
    main()
