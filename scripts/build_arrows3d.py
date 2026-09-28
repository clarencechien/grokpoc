#!/usr/bin/env python3
"""Embed story text + scenes.json into arrows3d/template.html -> arrows3d/index.html.

Run scripts/arrows3d_prep.py first (it cuts the pop-up cards out of arrows/assets/).
The page needs http(s) (WebGL refuses file:// textures): python3 -m http.server, open /arrows3d/.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "arrows3d"


def main() -> int:
    story = json.loads((ROOT / "story" / "red-cliff-arrows.json").read_text(encoding="utf-8"))
    scenes = json.loads((D / "assets" / "scenes.json").read_text(encoding="utf-8"))
    h = hashlib.sha1()
    for p in sorted((D / "assets").rglob("*")):
        if p.is_file() and "_check" not in p.parts:
            h.update(p.name.encode()); h.update(p.read_bytes())
    data = {
        "title": story["title"],
        "cover": {"text": story["cover"]["text"]},
        "chapters": [{"id": c["id"], "title": c["title"], "text": c["text"]} for c in story["chapters"]],
        "scenes": scenes,
        "v": h.hexdigest()[:10],
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (D / "template.html").read_text(encoding="utf-8").replace("/*__DATA__*/", blob)
    (D / "index.html").write_text(html, encoding="utf-8")
    print(f"wrote {D / 'index.html'} ({len(html) // 1024} KB, assets v={data['v']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
