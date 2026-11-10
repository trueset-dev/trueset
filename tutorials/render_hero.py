#!/usr/bin/env python3
"""Animated website hero video for trueset — real motion, not a slideshow.

Elements fade+slide in, the terminal types, the reconcile panel reveals row by
row. 30fps frame-by-frame via Pillow, narrated with `say` (scratch voice),
stitched with ffmpeg. No caption bar — the kinetic text carries it, so it also
reads well autoplaying muted on the landing page.

Usage:  python tutorials/render_hero.py   ->   tutorials/out/hero.mp4
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
PAPER = (248, 249, 250); INK = (20, 24, 27); SLATE = (78, 87, 95)
TEAL = (15, 118, 110); LINE = (228, 231, 234); WASH = (236, 244, 242)
PASS = (21, 115, 71); FAIL = (180, 35, 30); WHITE = (255, 255, 255)
SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"


def f(p, s): return ImageFont.truetype(p, s)
def clamp(x): return max(0.0, min(1.0, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def enter(t, start, dur=0.6): return ease((t - start) / dur)


def base(bg): return Image.new("RGBA", (W, H), bg + (255,))


def lay():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def put(dst, src, alpha=1.0, dy=0):
    if alpha <= 0:
        return
    work = src
    if alpha < 1:
        a = src.getchannel("A").point(lambda p: int(p * alpha))
        work = src.copy(); work.putalpha(a)
    if dy:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sh.paste(work, (0, dy), work); work = sh
    dst.alpha_composite(work)


def tl(d, s, font): return d.textlength(s, font=font)


def text_layer(s, font, color, y, cx=W // 2):
    im, d = lay()
    x = cx - tl(d, s, font) // 2
    d.text((x, y), s, font=font, fill=color, stroke_width=2, stroke_fill=color)
    return im


def mark(d, cx, cy, s, stroke, fill):
    gap, r = int(s * 0.62), int(s * 0.28)
    x0, y0 = cx - gap // 2 - s // 2, cy - s // 2
    d.rounded_rectangle((x0 + gap, y0, x0 + s, y0 + s), radius=max(2, r // 2), fill=fill)
    d.rounded_rectangle((x0, y0, x0 + s, y0 + s), radius=r, outline=stroke, width=max(3, s // 10))
    d.rounded_rectangle((x0 + gap, y0, x0 + gap + s, y0 + s), radius=r, outline=stroke, width=max(3, s // 10))


# ---- scenes (each takes local time t, returns RGB) ------------------------

def s_title(t):
    im = base(TEAL)
    ml, md = lay(); mark(md, W // 2, 372, 150, WHITE, WHITE)
    a = enter(t, 0.0, 0.7); put(im, ml, a, int((1 - a) * 30))
    wf = f(SANS, 150); wl, wd = lay()
    tw, sw = tl(wd, "true", wf), tl(wd, "set", wf); x = (W - (tw + sw)) // 2
    wd.text((x, 525), "true", font=wf, fill=WHITE, stroke_width=2, stroke_fill=WHITE)
    wd.text((x + tw, 525), "set", font=wf, fill=(190, 240, 232), stroke_width=2, stroke_fill=(190, 240, 232))
    a2 = enter(t, 0.35, 0.7); put(im, wl, a2, int((1 - a2) * 45))
    a3 = enter(t, 0.85, 0.7)
    put(im, text_layer("open-source data quality & reconciliation", f(SANS, 46), (200, 232, 228), 745), a3, int((1 - a3) * 30))
    return im.convert("RGB")


def s_statement(t):
    im = base(PAPER); big = f(SANS, 92)
    a1 = enter(t, 0.1, 0.6); put(im, text_layer("Your pipeline passed every test.", big, INK, 430), a1, int((1 - a1) * 50))
    a2 = enter(t, 0.65, 0.6); put(im, text_layer("The numbers are still wrong.", big, FAIL, 560), a2, int((1 - a2) * 50))
    return im.convert("RGB")


def s_panel(t):
    im = base(PAPER)
    pw, ph = 1180, 560; px, py = (W - pw) // 2, (H - ph) // 2
    a0 = enter(t, 0.0, 0.5)
    card, cd = lay()
    cd.rounded_rectangle((px, py, px + pw, py + ph), radius=24, fill=WHITE, outline=LINE, width=2)
    cd.text((px + 48, py + 36), "trueset reconcile · warehouse ⇄ source", font=f(MONO, 34), fill=SLATE)
    put(im, card, a0, int((1 - a0) * 25))
    rows = [("row_count_parity", "pass", PASS), ("referential_integrity", "fail · 1", FAIL), ("value_parity", "fail · 3", FAIL)]
    nf, pf = f(MONO, 44), f(MONO, 36); ry = py + 118
    for i, (name, tag, col) in enumerate(rows):
        ai = enter(t, 0.55 + 0.45 * i, 0.5)
        rl, rd = lay()
        rd.line((px + 42, ry, px + pw - 42, ry), fill=LINE, width=2)
        rd.text((px + 50, ry + 28), name, font=nf, fill=INK)
        tw = tl(rd, tag, pf); bg = (234, 245, 238) if col == PASS else (251, 236, 234)
        rd.rounded_rectangle((px + pw - 64 - tw - 36, ry + 26, px + pw - 58, ry + 76), radius=24, fill=bg)
        rd.text((px + pw - 64 - tw - 14, ry + 33), tag, font=pf, fill=col)
        put(im, rl, ai, int((1 - ai) * 35))
        ry += 102
    an = enter(t, 0.55 + 0.45 * 3 + 0.1, 0.55)
    nl, nd = lay()
    nd.rounded_rectangle((px + 1, ry + 6, px + pw - 1, py + ph - 1), radius=24, fill=WASH)
    nd.text((px + 48, ry + 34), "Row counts matched. The values didn't.", font=f(SANS, 42), fill=INK, stroke_width=1, stroke_fill=INK)
    put(im, nl, an, int((1 - an) * 20))
    return im.convert("RGB")


def s_engines(t):
    im = base(PAPER)
    a = enter(t, 0.1, 0.6)
    put(im, text_layer("Write once. Run anywhere.", f(SANS, 92), INK, 360), a, int((1 - a) * 50))
    chips = ["pandas", "DuckDB", "your warehouse"]; cf = f(MONO, 50)
    d0 = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    widths = [tl(d0, c, cf) + 80 for c in chips]
    total = sum(widths) + 40 * (len(chips) - 1); x = (W - total) // 2; y = 600
    for i, c in enumerate(chips):
        ai = enter(t, 0.6 + 0.25 * i, 0.5)
        cl, cd = lay()
        cd.rounded_rectangle((x, y, x + widths[i], y + 96), radius=20, fill=WHITE, outline=TEAL, width=3)
        cd.text((x + 40, y + 20), c, font=cf, fill=(11, 95, 88))
        put(im, cl, ai, int((1 - ai) * 40))
        x += widths[i] + 40
    return im.convert("RGB")


def s_install(t):
    im = base(TEAL)
    tw_, th = 1160, 300; tx, ty = (W - tw_) // 2, 300
    a = enter(t, 0.0, 0.5)
    tl_, td = lay()
    td.rounded_rectangle((tx, ty, tx + tw_, ty + th), radius=20, fill=(14, 20, 24))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        td.ellipse((tx + 36 + i * 34, ty + 30, tx + 56 + i * 34, ty + 50), fill=c)
    put(im, tl_, a, int((1 - a) * 25))
    cmd = "pip install trueset"; mf = f(MONO, 56)
    prog = clamp((t - 0.6) / 1.3); shown = cmd[:int(prog * len(cmd))]
    cur = "_" if (int(t * 2) % 2 == 0 and prog < 1) else ""
    cl, cd = lay()
    cd.text((tx + 50, ty + 150), "$ ", font=mf, fill=(127, 209, 196))
    cd.text((tx + 50 + tl(cd, "$ ", mf), ty + 150), shown + cur, font=mf, fill=(223, 228, 234))
    put(im, cl, min(1.0, a * 1.5))
    a2 = enter(t, 1.9, 0.6)
    put(im, text_layer("free · open source · Apache-2.0", f(SANS, 44), (200, 232, 228), 720), a2, int((1 - a2) * 30))
    return im.convert("RGB")


SCENES = [
    (s_title, "This is trueset. Open-source data quality, and the one thing most tools can't do."),
    (s_statement, "Your pipeline can pass every test, and the numbers are still wrong."),
    (s_panel, "trueset compares your systems row by row, and catches the drift that hides behind matching totals."),
    (s_engines, "Write a check once. Run it on pandas, DuckDB, or your warehouse."),
    (s_install, "Free. Open source. One pip install. trueset."),
]
OUT = os.path.join(os.path.dirname(__file__), "out", "hero.mp4")


def run(c): subprocess.run(c, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def dur(p): return float(subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())


def main():
    work = tempfile.mkdtemp(prefix="trueset_hero_")
    clips = []
    for i, (fn, narr) in enumerate(SCENES):
        txt = os.path.join(work, f"n{i}.txt"); open(txt, "w").write(narr)
        aiff = os.path.join(work, f"a{i}.aiff")
        run(["say", "-v", "Samantha", "-r", "180", "-f", txt, "-o", aiff])
        d = dur(aiff) + 0.7
        n = int(d * FPS)
        sd = os.path.join(work, f"s{i}"); os.makedirs(sd, exist_ok=True)
        for k in range(n):
            fn(k / FPS).save(os.path.join(sd, f"{k:05d}.png"))
        clip = os.path.join(work, f"c{i}.mp4")
        run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(sd, "%05d.png"),
             "-i", aiff, "-af", "apad", "-t", f"{n / FPS:.2f}", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-r", str(FPS), clip])
        clips.append(clip); print(f"scene {i}: {n} frames, {n/FPS:.1f}s")
    lst = os.path.join(work, "l.txt"); open(lst, "w").write("".join(f"file '{c}'\n" for c in clips))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", OUT])
    print("TOTAL", round(sum(dur(c) for c in clips), 1), "s ->", OUT)


if __name__ == "__main__":
    main()
