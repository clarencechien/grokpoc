#!/usr/bin/env python3
"""草船借箭 · Three.js 版 — 把既有的 Grok 素材拆成 3D 立體書用的零件。

不生成任何新圖。全部來源都在 arrows/assets/：

  ref_spread_blank.jpg   空白母版  -> 地頁紙（反透視攤平）、背頁紙、書口紙疊、木桌
  ref_cover_closed.jpg   闔上封面  -> 封面水墨小畫（反透視攤平）
  ref_cast.jpg           定裝表    -> 五個角色的乾淨剪紙（落幕謝幕用）
  <id>.jpg               各章跨頁  -> 紙偶／道具剪下來當立體卡片
  <id>_collapse.mp4      收折片    -> 人物倒下、背景還沒褪掉的那一格 = 乾淨背景板

剪紙：每張卡給一個粗框，GrabCut 以「跟空白母版／乾淨背景板的差異」當初始前景，
框外一律背景。卡片在 3D 裡的位置從跨頁上的腳底座標推回地頁（地頁四角已知）。

  python3 scripts/arrows3d_prep.py            # 產出 arrows3d/assets/ + scenes.json
  python3 scripts/arrows3d_prep.py --sheet    # 另存每章剪紙對照圖到 arrows3d/assets/_check/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "arrows" / "assets"
OUT = ROOT / "arrows3d" / "assets"

# ---- 母版上量出來的幾何（1280x720 影像座標）。所有跨頁都是母版的 edit，書的位置一致。
FAR = (352, 48, 950, 405)                        # 立著的背頁 x0,y0,x1,y1
FLOOR = [(320, 415), (975, 415), (1035, 595), (297, 595)]   # 地頁 後左、後右、前右、前左
BLOCK = (297, 595, 1035, 655)                    # 書口紙疊（地頁下方那一疊破紙邊）
PAGE_W, PAGE_H = 1.64, 1.0                       # 3D 裡一頁的寬、深（世界單位）

# 收折片裡「人物已倒、背景還在」的那一格；inpaint = 背景板上還殘留的道具（背頁座標）
PLATES = {
    "c1": (48, []),
    "c2": (84, [(330, 312, 455, 357)]),
    "c3": (68, []),
    "c4": (64, []),
    "c5": (60, [(0, 318, 598, 357)]),
    "c6": (44, []),
    "c7": (60, [(0, 322, 598, 357)]),
    "c8": (88, [(190, 268, 570, 357)]),
}

# 每章的卡片：rect = 跨頁上的粗框；minus = 框內要排除的區塊；holes = 保留鏤空（塔架）
# kind 決定 3D 動畫：figure（紙偶微晃）、lantern（掛一盞會閃的燈）、boat、group、tower、drums
CARDS: dict[str, list[dict]] = {
    "cover": [
        {"n": "boat", "rect": (425, 222, 662, 472), "kind": "boat", "lamp": (476, 310), "init": "rect"},
        {"n": "straw_l", "rect": (428, 368, 568, 552), "kind": "figure", "init": "rect"},
        {"n": "straw_back", "rect": (670, 288, 868, 424), "kind": "group", "init": "rect"},
        {"n": "straw_front", "rect": (716, 358, 948, 562), "kind": "group", "init": "rect"},
    ],
    "c1": [
        {"n": "zhouyu", "rect": (440, 135, 662, 506), "kind": "figure", "minus": [(608, 372, 662, 506)]},
        {"n": "zhuge", "rect": (664, 188, 926, 512), "kind": "figure", "minus": [(664, 360, 733, 512)]},
    ],
    "c2": [
        {"n": "zhouyu", "rect": (645, 158, 802, 466), "kind": "figure",
         "minus": [(662, 398, 728, 484)]},
        {"n": "zhuge_table", "rect": (418, 238, 728, 556), "kind": "group", "lamp": (692, 440)},
        {"n": "lusu", "rect": (794, 228, 948, 532), "kind": "figure"},
    ],
    "c3": [
        {"n": "zhuge", "rect": (518, 278, 668, 527), "kind": "figure"},
        {"n": "lusu", "rect": (678, 283, 812, 532), "kind": "figure"},
        {"n": "lantern", "rect": (826, 333, 902, 532), "kind": "lantern", "lamp": (864, 382)},
    ],
    "c4": [
        {"n": "lamp_table", "rect": (598, 303, 762, 452), "kind": "lantern", "lamp": (676, 368)},
        {"n": "zhuge", "rect": (398, 172, 612, 522), "kind": "figure", "steam": (548, 330)},
        {"n": "lusu", "rect": (733, 163, 918, 528), "kind": "figure", "pace": True},
    ],
    "c5": [
        {"n": "boat", "rect": (540, 278, 948, 562), "kind": "boat", "lamp": (726, 450)},
        {"n": "zhuge", "rect": (433, 308, 562, 538), "kind": "figure"},
    ],
    "c6": [
        {"n": "zhuge", "rect": (393, 248, 527, 502), "kind": "figure"},
        {"n": "lusu", "rect": (518, 260, 662, 512), "kind": "figure", "tremble": True},
        {"n": "lantern", "rect": (655, 198, 722, 478), "kind": "lantern", "lamp": (688, 420)},
        {"n": "drummers", "rect": (694, 293, 1000, 527), "kind": "drums"},
    ],
    "c7": [
        {"n": "tower", "rect": (418, 62, 632, 468), "kind": "tower", "holes": True, "init": "rect",
         "minus": [(578, 62, 632, 168), (578, 196, 632, 300)]},
        {"n": "boat", "rect": (604, 278, 988, 562), "kind": "boat", "target": True, "init": "rect"},
    ],
    "c8": [
        {"n": "boat", "rect": (573, 243, 862, 512), "kind": "boat", "lamp": (646, 382)},
        {"n": "straw_l", "rect": (393, 328, 582, 556), "kind": "group", "cheer": True},
        {"n": "straw_r", "rect": (793, 328, 1002, 552), "kind": "group", "cheer": True, "init": "rect"},
    ],
}

# 落幕頁：定裝表五人（ref_cast 的 x 區間見 story 的 cast_bounds）
CAST_Y = (88, 592)


# ---------------------------------------------------------------- io helpers

def rd(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB")).astype(np.float32)


def frame(clip: Path, k: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(clip))
    cap.set(cv2.CAP_PROP_POS_FRAMES, k)
    ok, f = cap.read()
    if not ok:
        raise SystemExit(f"cannot read frame {k} of {clip}")
    return cv2.cvtColor(f, cv2.COLOR_BGR2RGB).astype(np.float32)


def save_jpg(a: np.ndarray, p: Path, size=None, q=86, sharpen=False):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if size:
        im = im.resize(size, Image.LANCZOS)
    if sharpen:
        im = im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=70, threshold=2))
    im.save(p, quality=q, optimize=True, progressive=True)


def match_color(src: np.ndarray, ref: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """per-channel mean/std match on the pixels in mask (collapse frames are faded)."""
    out = src.copy()
    for c in range(3):
        s, r = src[..., c][mask], ref[..., c][mask]
        out[..., c] = (src[..., c] - s.mean()) / (s.std() + 1e-3) * r.std() + r.mean()
    return np.clip(out, 0, 255)


def unwarp(img: np.ndarray, quad, w: int, h: int) -> np.ndarray:
    M = cv2.getPerspectiveTransform(np.float32(quad), np.float32([(0, 0), (w, 0), (w, h), (0, h)]))
    return cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)


# ---------------------------------------------------------------- backdrops

def plate(cid: str, still: np.ndarray) -> np.ndarray:
    """clean backdrop in full-frame coords: still where nothing stands in front, collapse frame elsewhere."""
    k, fix = PLATES[cid]
    P = frame(SRC / f"{cid}_collapse.mp4", k)
    x0, y0, x1, y1 = FAR
    top = np.zeros(still.shape[:2], bool)
    top[y0:y0 + 120, x0 + 40:x1 - 40] = True          # nothing stands this high in any chapter
    P = match_color(P, still, top)
    # where the still differs from the plate, a figure is in front: use the plate there
    d = np.abs(still - P).sum(2)
    m = (d > 40).astype(np.uint8)
    m = cv2.dilate(cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)), np.ones((15, 15), np.uint8))
    m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 5)[..., None]
    out = still * (1 - m) + P * m
    crop = out[y0:y1, x0:x1].copy()
    if fix:
        mask = np.zeros(crop.shape[:2], np.uint8)
        for (a, b, c, e) in fix:
            mask[b:e, a:c] = 255
        crop = cv2.inpaint(crop.astype(np.uint8), mask, 9, cv2.INPAINT_TELEA).astype(np.float32)
    return crop


def cover_plate(still: np.ndarray, blank: np.ndarray, figmask: np.ndarray) -> np.ndarray:
    """the cover spread has no collapse clip: inpaint the figures out of the painted river."""
    x0, y0, x1, y1 = FAR
    crop = still[y0:y1, x0:x1].astype(np.uint8).copy()
    m = cv2.dilate(figmask[y0:y1, x0:x1].astype(np.uint8) * 255, np.ones((11, 11), np.uint8))
    small = cv2.resize(crop, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    ms = cv2.resize(m, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_NEAREST)
    fill = cv2.inpaint(small, ms, 15, cv2.INPAINT_TELEA)
    fill = cv2.GaussianBlur(cv2.resize(fill, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_CUBIC), (0, 0), 3)
    a = cv2.GaussianBlur(m.astype(np.float32) / 255, (0, 0), 4)[..., None]
    return crop * (1 - a) + fill * a


# ---------------------------------------------------------------- cut-outs

def resid(S: np.ndarray, R: np.ndarray):
    """shadow-tolerant difference: S ~ k*R means R under a different light (shadow / lamp glow)."""
    k = (S * R).sum(2) / ((R * R).sum(2) + 1e-3)
    E = np.linalg.norm(S - k[..., None] * R, axis=2) / (np.linalg.norm(R, axis=2) + 1e-3)
    return E, k


def fg_hint(still: np.ndarray, ref: np.ndarray, has_plate: bool) -> np.ndarray:
    E, k = resid(still, ref)
    d = np.abs(still - ref).sum(2)
    M = (E > 0.13) | ((k > 1.25) & (d > 90)) | ((k < 0.42) & (d > 120))
    if has_plate:
        x0, y0, x1, y1 = FAR
        M[y0:y1, x0:x1] = (d > 70)[y0:y1, x0:x1]
    M = M.astype(np.uint8)
    M = cv2.morphologyEx(M, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return cv2.morphologyEx(M, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))


def cut(still: np.ndarray, hint: np.ndarray, card: dict) -> np.ndarray:
    x0, y0, x1, y1 = card["rect"]
    H, W = hint.shape
    gc = np.full((H, W), cv2.GC_BGD, np.uint8)
    inside = np.zeros((H, W), bool)
    inside[y0:y1, x0:x1] = True
    for (a, b, c, e) in card.get("minus", []):
        inside[b:e, a:c] = False
    gc[inside] = cv2.GC_PR_BGD
    if card.get("init") != "rect":       # seed with the diff hint; "rect" = let GrabCut judge the box alone
        h = hint.copy()
        h[~inside] = 0
        gc[(h > 0) & inside] = cv2.GC_PR_FGD
        gc[(cv2.erode(h, np.ones((7, 7), np.uint8)) > 0) & inside] = cv2.GC_FGD
    else:
        gc[inside] = cv2.GC_PR_FGD
        # the box border is surely background: that is what GrabCut learns the backdrop colours from
        rim = inside & ~cv2.erode(inside.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        gc[rim] = cv2.GC_BGD
    img = np.ascontiguousarray(still.astype(np.uint8)[..., ::-1])
    bgm, fgm = np.zeros((1, 65)), np.zeros((1, 65))
    cv2.grabCut(img, gc, None, bgm, fgm, 5, cv2.GC_INIT_WITH_MASK)
    m = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)) & inside
    if not card.get("holes"):
        m = ndi.binary_fill_holes(m)
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n > 1:
        big = st[1:, 4].max()
        keep = [i for i in range(1, n) if st[i, 4] >= max(400, 0.08 * big)]
        m = np.isin(lab, keep).astype(np.uint8)
    return m


def rgba(still: np.ndarray, m: np.ndarray):
    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.8)[y0:y1, x0:x1]
    rgb = still[y0:y1, x0:x1]
    im = np.dstack([rgb, np.clip(a * 255, 0, 255)]).astype(np.uint8)
    return Image.fromarray(im, "RGBA"), (int(x0), int(y0), int(x1), int(y1)), m[y0:y1, x0:x1]


# ---------------------------------------------------------------- placement on the floor page

_Hf = cv2.getPerspectiveTransform(np.float32(FLOOR), np.float32([(0, 0), (1, 0), (1, 1), (0, 1)]))


def floor_uv(x: float, y: float):
    p = cv2.perspectiveTransform(np.float32([[[x, y]]]), _Hf)[0, 0]
    return float(p[0]), float(p[1])


def px_width_at(y: float) -> float:
    """page width in pixels at image row y (linear between the back and front edges of the floor)."""
    (bl, by), (br, _), (fr, fy), (fl, _) = FLOOR
    t = (y - by) / (fy - by)
    return (br - bl) + t * ((fr - fl) - (br - bl))


def place(box, m, img_pt=None):
    """card world size + base position from where it stands in the still."""
    x0, y0, x1, y1 = box
    cols = np.nonzero(m.any(0))[0]
    # base = the lowest opaque row (feet or paper tab); centre = middle of the bottom quarter
    base_y = y0 + np.nonzero(m.any(1))[0].max()
    low = m[int(m.shape[0] * 0.75):]
    lc = np.nonzero(low.any(0))[0] if low.any() else cols
    cx = x0 + (lc.min() + lc.max()) / 2
    by = max(base_y, FLOOR[0][1] + 6)
    u, v = floor_uv(cx, by)
    s = PAGE_W / px_width_at(by)
    card = {
        "w": round((x1 - x0) * s, 4), "h": round((y1 - y0) * s, 4),
        "x": round((u - 0.5) * PAGE_W, 4), "d": round(float(np.clip(v, 0.04, 0.9)) * PAGE_H, 4),
        # horizontal offset of the card centre from the stand point (card may be asymmetric)
        "ox": round(((x0 + x1) / 2 - cx) * s, 4),
    }
    if img_pt is not None:   # a point on the card (lamp, steam) in card-local UV (0..1, from bottom-left)
        card["pt"] = [round((img_pt[0] - x0) / (x1 - x0), 3), round(1 - (img_pt[1] - y0) / (y1 - y0), 3)]
    return card


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", action="store_true", help="write contact sheets of the cut-outs")
    args = ap.parse_args()
    (OUT / "cards").mkdir(parents=True, exist_ok=True)
    chk = OUT / "_check"
    if args.sheet:
        chk.mkdir(exist_ok=True)

    blank = rd(SRC / "ref_spread_blank.jpg")

    # --- paper, block, wood, cloth from the blank master
    x0, y0, x1, y1 = FAR
    save_jpg(blank[y0:y1, x0:x1], OUT / "page_far.jpg", (1024, 624), sharpen=True)
    save_jpg(unwarp(blank, FLOOR, 1024, 624), OUT / "page_floor.jpg", sharpen=True)
    bx0, by0, bx1, by1 = BLOCK
    save_jpg(blank[by0:by1, bx0:bx1], OUT / "page_block.jpg", (1024, 84))
    wood = blank[440:700, 0:215]                      # table left of the book
    wood = np.concatenate([wood, wood[:, ::-1]], 1)   # mirror so it tiles horizontally
    wood = np.concatenate([wood, wood[::-1]], 0)      # and vertically
    save_jpg(wood, OUT / "wood.jpg", (512, 512), q=82)

    closed = rd(SRC / "ref_cover_closed.jpg")
    # debossed ink-wash panel on the closed cover (its painting is upright toward the upper right)
    panel = unwarp(closed, [(598, 228), (1016, 300), (740, 470), (422, 366)], 520, 300)
    save_jpg(panel, OUT / "cover_panel.jpg", q=85, sharpen=True)

    scenes: dict[str, dict] = {}
    for cid, cards in CARDS.items():
        still = rd(SRC / f"{cid}.jpg")
        has_plate = cid in PLATES
        ref = blank.copy()
        if has_plate:
            bd = plate(cid, still)
            ref[y0:y1, x0:x1] = bd
        hint = fg_hint(still, ref, has_plate)
        out_cards, allm = [], np.zeros(hint.shape, np.uint8)
        for c in cards:
            m = cut(still, hint, c)
            allm |= m
            im, box, mm = rgba(still, m)
            name = f"{cid}_{c['n']}.webp"
            im.save(OUT / "cards" / name, quality=90, method=6)
            pt = c.get("lamp") or c.get("steam")
            spec = {"src": f"cards/{name}", "kind": c["kind"], **place(box, mm, pt)}
            for flag in ("lamp", "steam", "pace", "tremble", "target", "cheer", "role"):
                if flag in c:
                    spec[flag] = True if flag not in ("role",) else c[flag]
            out_cards.append(spec)
        if not has_plate:
            bd = cover_plate(still, blank, allm)
        save_jpg(bd, OUT / f"bd_{cid}.jpg", (1024, 624), sharpen=True)
        # draw the nearer cards last
        out_cards.sort(key=lambda s: s["d"])
        scenes[cid] = {"backdrop": f"bd_{cid}.jpg", "cards": out_cards}
        if args.sheet:
            v = still * 0.22
            v[allm > 0] = still[allm > 0]
            left = Image.fromarray(v.astype(np.uint8)).crop((300, 30, 1060, 640))
            right = Image.open(OUT / f"bd_{cid}.jpg").resize((760, 463))
            sh = Image.new("RGB", (1520, 610), (20, 20, 20))
            sh.paste(left, (0, 0))
            sh.paste(right, (760, 0))
            sh.save(chk / f"{cid}.jpg", quality=80)
        print(f"  {cid}: {len(out_cards)} cards")

    # --- curtain call: the five clean cut-outs from the cast sheet
    cast = rd(SRC / "ref_cast.jpg")
    cb = json.loads((ROOT / "story" / "red-cliff-arrows.json").read_text(encoding="utf-8"))["cast_bounds"]
    parch = cv2.GaussianBlur(cast, (0, 0), 25)          # smooth parchment as the "blank" reference
    hint = fg_hint(cast, parch, False)
    finale = []
    for i, (who, (a, b)) in enumerate(cb.items()):
        c = {"rect": (a + 4, CAST_Y[0], b - 4, CAST_Y[1])}
        m = cut(cast, hint, c)
        im, box, mm = rgba(cast, m)
        im.save(OUT / "cards" / f"cast_{who}.webp", quality=90, method=6)
        w, h = (box[2] - box[0]), (box[3] - box[1])
        s = 0.62 / 470                                     # ~ the height these figures have in the chapters
        finale.append({"src": f"cards/cast_{who}.webp", "kind": "figure", "role": who,
                       "w": round(w * s, 4), "h": round(h * s, 4),
                       "x": round((i - 2) * 0.3, 3), "d": 0.42 + 0.06 * (i % 2), "ox": 0})
    scenes["end"] = {"backdrop": "page_far.jpg", "cards": sorted(finale, key=lambda s: s["d"])}

    (OUT / "scenes.json").write_text(json.dumps(scenes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT / 'scenes.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
