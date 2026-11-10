#!/usr/bin/env python3
"""Tutorial video renderer — square 1:1 (LinkedIn), HYBRID style.

Animated title/point/outro cards (fade+slide) for energy; the actual
command-and-output demos stay clean and static so viewers can follow along.
Captioned throughout (most LinkedIn viewers watch muted). Narrated with `say`
(scratch voice — swap in your own for the final). Stitched with ffmpeg.

Edit SCENES at the bottom (or import and call render(scenes, out_path)).
Usage: python tutorials/render_tutorial.py   ->  tutorials/out/02-your-first-check.mp4
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

W = H = 1080
FPS = 30
PAPER = (248, 249, 250); INK = (20, 24, 27); SLATE = (78, 87, 95)
TEAL = (15, 118, 110); TEAL_INK = (11, 95, 88); LINE = (228, 231, 234)
WASH = (236, 244, 242); PASS = (21, 115, 71); FAIL = (180, 35, 30); WHITE = (255, 255, 255)
AMBER = (176, 120, 40)
SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
ANIM = {"title", "point", "outro"}


def f(p, s): return ImageFont.truetype(p, s)
def clamp(x): return max(0.0, min(1.0, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def enter(t, s, d=0.6): return ease((t - s) / d)
def base(bg): return Image.new("RGBA", (W, H), bg + (255,))


def lay():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); return im, ImageDraw.Draw(im)


def put(dst, src, a=1.0, dy=0):
    if a <= 0:
        return
    w = src
    if a < 1:
        al = src.getchannel("A").point(lambda p: int(p * a)); w = src.copy(); w.putalpha(al)
    if dy:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sh.paste(w, (0, dy), w); w = sh
    dst.alpha_composite(w)


def tw(d, s, fn): return d.textlength(s, font=fn)


def wrap(d, s, fn, mx):
    out, cur = [], ""
    for wd in s.split():
        t = (cur + " " + wd).strip()
        (out.append(cur) or 0) if tw(d, t, fn) > mx and cur else None
        cur = wd if (tw(d, t, fn) > mx and cur) else t
    if cur:
        out.append(cur)
    return out


def tlayer(s, fn, color, y, cx=W // 2, bold=True):
    im, d = lay(); x = cx - tw(d, s, fn) // 2
    d.text((x, y), s, font=fn, fill=color, stroke_width=2 if bold else 0, stroke_fill=color)
    return im


def mark(d, cx, cy, s, stroke, fill):
    g, r = int(s * 0.62), int(s * 0.28); x0, y0 = cx - g // 2 - s // 2, cy - s // 2
    d.rounded_rectangle((x0 + g, y0, x0 + s, y0 + s), radius=max(2, r // 2), fill=fill)
    d.rounded_rectangle((x0, y0, x0 + s, y0 + s), radius=r, outline=stroke, width=max(3, s // 10))
    d.rounded_rectangle((x0 + g, y0, x0 + g + s, y0 + s), radius=r, outline=stroke, width=max(3, s // 10))


def caption(img, text, dark_ok=True):
    d = ImageDraw.Draw(img); cf = f(SANS, 31)
    lines = wrap(d, text, cf, W - 150)
    lh = 42; bh = max(130, len(lines) * lh + 52)
    d.rectangle((0, H - bh, W, H), fill=INK)
    y = H - bh + (bh - len(lines) * lh) // 2
    for ln in lines:
        d.text(((W - tw(d, ln, cf)) // 2, y), ln, font=cf, fill=(230, 234, 238)); y += lh
    return H - bh


def brandtag(d):
    wf = f(SANS, 30)
    d.text((44, 40), "true", font=wf, fill=INK); x = 44 + tw(d, "true", wf)
    d.text((x, 40), "set", font=wf, fill=TEAL_INK)


# ---- scene renderers ------------------------------------------------------

def r_title(sc, t):
    im = base(TEAL); d = ImageDraw.Draw(im)
    stop = caption(im, sc["narration"]); mid = stop // 2
    a0 = enter(t, 0.0, 0.6)
    put(im, tlayer(sc["num"], f(SANS, 150), (190, 240, 232), mid - 230), a0, int((1 - a0) * 40))
    a1 = enter(t, 0.3, 0.6)
    tf = f(SANS, 92)
    tim, td = lay()
    for i, ln in enumerate(wrap(td, sc["title"], tf, W - 160)):
        td.text(((W - tw(td, ln, tf)) // 2, mid - 40 + i * 104), ln, font=tf, fill=WHITE, stroke_width=2, stroke_fill=WHITE)
    put(im, tim, a1, int((1 - a1) * 46))
    return im.convert("RGB")


def r_point(sc, t):
    im = base(PAPER); stop = caption(im, sc["narration"]); mid = stop // 2
    bf = f(SANS, 72); lines = sc["lines"]
    y = mid - (len(lines) * 88) // 2 - (40 if sc.get("sub") else 0)
    for i, ln in enumerate(lines):
        a = enter(t, 0.1 + 0.4 * i, 0.6)
        col = TEAL_INK if (sc.get("accent") and i == len(lines) - 1) else INK
        put(im, tlayer(ln, bf, col, y + i * 92), a, int((1 - a) * 48))
    if sc.get("sub"):
        a = enter(t, 0.1 + 0.4 * len(lines), 0.6); sf = f(MONO, 44)
        sim, sd = lay(); s = sc["sub"]; x = (W - tw(sd, s, sf)) // 2; yy = y + len(lines) * 92 + 40
        sd.rounded_rectangle((x - 34, yy - 16, x + tw(sd, s, sf) + 34, yy + 66), radius=16, fill=WHITE, outline=LINE, width=2)
        sd.text((x, yy), s, font=sf, fill=TEAL_INK)
        put(im, sim, a, int((1 - a) * 30))
    return im.convert("RGB")


def _card(d, x0, y0, x1, y1, fill, outline=LINE):
    d.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=fill, outline=outline, width=2)


def r_file(sc):
    im = base(PAPER); d = ImageDraw.Draw(im); brandtag(d)
    stop = caption(im, sc["narration"])
    mf = f(MONO, 34); hf = f(MONO, 26)
    lines = sc["lines"]; pad = 36
    ch = 70 + len(lines) * 46 + pad
    cw = W - 120; cx0, cy0 = 60, (stop - ch) // 2
    _card(d, cx0, cy0, cx0 + cw, cy0 + ch, (18, 22, 26), outline=(18, 22, 26))
    d.text((cx0 + pad, cy0 + 24), sc["head"], font=hf, fill=(140, 150, 158))
    y = cy0 + 74
    for ln in lines:
        if sc.get("yaml") and ":" in ln and not ln.strip().startswith("#"):
            key, _, rest = ln.partition(":")
            d.text((cx0 + pad, y), key + ":", font=mf, fill=(127, 209, 196))
            d.text((cx0 + pad + tw(d, key + ":", mf), y), rest, font=mf, fill=(227, 185, 129) if "[" in rest else (223, 228, 234))
        elif sc.get("csv") and "," in ln:
            d.text((cx0 + pad, y), ln, font=mf, fill=(223, 228, 234))
        else:
            d.text((cx0 + pad, y), ln, font=mf, fill=(223, 228, 234))
        y += 46
    return im.convert("RGB")


def r_terminal(sc):
    im = base(PAPER); d = ImageDraw.Draw(im); brandtag(d)
    stop = caption(im, sc["narration"])
    mf = f(MONO, 36); out = sc.get("out", [])
    ch = 150 + len(out) * 48; cw = W - 120; cx0, cy0 = 60, (stop - ch) // 2
    _card(d, cx0, cy0, cx0 + cw, cy0 + ch, (18, 22, 26), outline=(18, 22, 26))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((cx0 + 30 + i * 32, cy0 + 28, cx0 + 48 + i * 32, cy0 + 46), fill=c)
    d.text((cx0 + 34, cy0 + 90), "$ ", font=mf, fill=(127, 209, 196))
    d.text((cx0 + 34 + tw(d, "$ ", mf), cy0 + 90), sc["cmd"], font=mf, fill=(223, 228, 234))
    y = cy0 + 150
    for ln in out:
        d.text((cx0 + 34, y), ln, font=mf, fill=(150, 220, 180)); y += 48
    return im.convert("RGB")


def r_result(sc):
    im = base(PAPER); d = ImageDraw.Draw(im); brandtag(d)
    stop = caption(im, sc["narration"])
    rows = sc["rows"]; nf = f(MONO, 34); df = f(MONO, 23); pf = f(MONO, 27); hf = f(MONO, 25)
    rowh = 92; ch = 76 + len(rows) * rowh + 88
    cw = W - 110; cx0, cy0 = 55, (stop - ch) // 2
    _card(d, cx0, cy0, cx0 + cw, cy0 + ch, WHITE)
    d.text((cx0 + 36, cy0 + 26), "trueset run · " + sc["suite"], font=hf, fill=SLATE)
    y = cy0 + 80
    for name, col_, status, color, detail in rows:
        d.line((cx0 + 30, y, cx0 + cw - 30, y), fill=LINE, width=2)
        d.text((cx0 + 36, y + 16), name, font=nf, fill=INK)
        if detail:
            d.text((cx0 + 36, y + 58), detail, font=df, fill=SLATE)
        tag = status if status == "PASS" else f"{status} · {col_}"
        tagw = tw(d, tag, pf); bg = (234, 245, 238) if color == PASS else (251, 236, 234)
        d.rounded_rectangle((cx0 + cw - 44 - tagw - 30, y + 24, cx0 + cw - 40, y + 70), radius=22, fill=bg)
        d.text((cx0 + cw - 44 - tagw - 12, y + 30), tag, font=pf, fill=color)
        y += rowh
    vy = y + 6
    d.rounded_rectangle((cx0 + 1, vy, cx0 + cw - 1, cy0 + ch - 1), radius=22, fill=WASH)
    vf = f(SANS, 36)
    verdict, counts = sc["verdict"]
    d.text((cx0 + 36, vy + 22), verdict, font=vf, fill=FAIL, stroke_width=1, stroke_fill=FAIL)
    d.text((cx0 + 36 + tw(d, verdict + "  ", vf), vy + 26), counts, font=f(SANS, 30), fill=SLATE)
    return im.convert("RGB")


def r_outro(sc, t):
    im = base(TEAL); stop = caption(im, sc["narration"]); mid = stop // 2
    ml, md = lay(); mark(md, W // 2, mid - 120, 110, WHITE, WHITE)
    a0 = enter(t, 0.0, 0.6); put(im, ml, a0, int((1 - a0) * 30))
    a1 = enter(t, 0.3, 0.6)
    tf = f(SANS, 72); tim, td = lay()
    for i, ln in enumerate(wrap(td, sc["title"], tf, W - 150)):
        td.text(((W - tw(td, ln, tf)) // 2, mid + 20 + i * 84), ln, font=tf, fill=WHITE, stroke_width=2, stroke_fill=WHITE)
    put(im, tim, a1, int((1 - a1) * 44))
    return im.convert("RGB")


RENDER = {"title": r_title, "point": r_point, "file": r_file, "terminal": r_terminal,
          "result": r_result, "outro": r_outro}


def run(c): subprocess.run(c, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def dur(p): return float(subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())


def render(scenes, out):
    work = tempfile.mkdtemp(prefix="trueset_tut_")
    clips = []
    for i, sc in enumerate(scenes):
        txt = os.path.join(work, f"n{i}.txt"); open(txt, "w").write(sc["narration"])
        aiff = os.path.join(work, f"a{i}.aiff")
        run(["say", "-v", "Samantha", "-r", "178", "-f", txt, "-o", aiff])
        d = dur(aiff) + 0.6; clip = os.path.join(work, f"c{i}.mp4")
        fn = RENDER[sc["kind"]]
        if sc["kind"] in ANIM:
            n = int(d * FPS); sd = os.path.join(work, f"s{i}"); os.makedirs(sd)
            for k in range(n):
                fn(sc, k / FPS).save(os.path.join(sd, f"{k:05d}.png"))
            run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(sd, "%05d.png"), "-i", aiff,
                 "-af", "apad", "-t", f"{n/FPS:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-r", str(FPS), clip])
        else:
            frame = os.path.join(work, f"f{i}.png"); fn(sc).save(frame)
            run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", frame, "-i", aiff,
                 "-af", "apad=pad_dur=0.6", "-t", f"{d:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-r", str(FPS), clip])
        clips.append(clip); print(f"  scene {i} ({sc['kind']}): {d:.1f}s")
    lst = os.path.join(work, "l.txt"); open(lst, "w").write("".join(f"file '{c}'\n" for c in clips))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
    print("TOTAL", round(sum(dur(c) for c in clips), 1), "s ->", out)


VIDEO_02 = [
    {"kind": "title", "num": "02", "title": "Your first check",
     "narration": "Let's write your first check and run it. From nothing to a real validation, in two minutes."},
    {"kind": "point", "lines": ["Describe what should be true.", "trueset checks it."], "accent": True,
     "narration": "trueset works on a simple idea. You describe what should be true about your data, and trueset checks it."},
    {"kind": "file", "head": "orders.csv", "csv": True,
     "lines": ["order_id,amount,status,email", "1001,49.99,shipped,alice@...", "1003,-5.00,pending,carol@...",
               "1004,89.50,shipped,not-an-email", "1005,15.00,teleported,dave@..."],
     "narration": "Here's some order data. An id, an amount, a status, an email. A few things in here are wrong. Let's catch them."},
    {"kind": "file", "head": "checks.yml", "yaml": True,
     "lines": ["suite: orders_quality", "checks:", "  - type: not_null", "    column: order_id",
               "  - type: unique", "    column: order_id", "  - type: in_range", "    column: amount",
               "    min: 0", "  - type: in_set", "    column: status",
               "    values: [pending, shipped, delivered, cancelled]"],
     "narration": "And here's what I expect. order_id is never empty, and unique. amount is never negative. status is one of these four values. That's it, plain YAML."},
    {"kind": "result", "suite": "orders_quality",
     "rows": [("not_null", "0/7", "PASS", PASS, ""), ("unique", "1/7", "FAIL", FAIL, "a duplicate order_id"),
              ("in_range", "1/7", "FAIL", FAIL, "amount of -5 is below 0"),
              ("in_set", "1/7", "FAIL", FAIL, "status 'teleported'")],
     "verdict": ("FAILED", "1 pass · 3 fail"),
     "narration": "I run it, and there's the result. Each check, pass or fail, with the count of failing rows. It caught the duplicate id, the negative amount, and a status that should not exist."},
    {"kind": "terminal", "cmd": "echo $?", "out": ["1"],
     "narration": "And here's the part that matters for automation. trueset exits non-zero when an error check fails. That one number lets it gate a C I pipeline, an Airflow task, or a pre-load step. Good data passes. Bad data stops."},
    {"kind": "point", "lines": ["Don't want to write them by hand?"], "sub": "trueset suggest --data orders.csv",
     "narration": "And if you don't want to write checks by hand, trueset suggest profiles your data and drafts a starter suite for you to review and edit. You stay in control of what ships."},
    {"kind": "outro", "title": "Next → the check library",
     "narration": "That's your first check. Next, the full library of checks you can use. See you there."},
]

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "out", "02-your-first-check.mp4")
    render(VIDEO_02, out)
