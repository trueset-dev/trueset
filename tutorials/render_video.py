#!/usr/bin/env python3
"""Render a trueset tutorial video from a scene list — fully from the command line.

Pipeline (all free, local):
  - macOS `say` (Samantha) -> per-scene narration audio  [SCRATCH VOICE — replace
    with your own voice for the final cut]
  - Pillow -> branded 1920x1080 frames with a caption bar
  - ffmpeg -> per-scene clips (image + audio), then concatenated to the final mp4

Usage:  python tutorials/render_video.py
Output: tutorials/out/01-what-is-trueset.mp4
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

# ---- brand ----------------------------------------------------------------
W, H = 1920, 1080
PAPER = (248, 249, 250); INK = (20, 24, 27); SLATE = (78, 87, 95)
TEAL = (15, 118, 110); TEAL_INK = (11, 95, 88); LINE = (228, 231, 234)
WASH = (236, 244, 242); PASS = (21, 115, 71); FAIL = (180, 35, 30); WHITE = (255, 255, 255)

SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"


def f(path, size):
    return ImageFont.truetype(path, size)


def text_w(d, s, font):
    return d.textlength(s, font=font)


def wrap(d, s, font, maxw):
    out, cur = [], ""
    for word in s.split():
        t = (cur + " " + word).strip()
        if text_w(d, t, font) <= maxw:
            cur = t
        else:
            out.append(cur); cur = word
    if cur:
        out.append(cur)
    return out


def mark(d, cx, cy, s, stroke, fill):
    """The two-tile 'true set' logo, centered at (cx, cy), tile size s."""
    gap = int(s * 0.62)
    r = int(s * 0.28)
    x0 = cx - gap // 2 - s // 2
    y0 = cy - s // 2
    left = (x0, y0, x0 + s, y0 + s)
    right = (x0 + gap, y0, x0 + gap + s, y0 + s)
    # filled intersection band
    ix0, ix1 = x0 + gap, x0 + s
    d.rounded_rectangle((ix0, y0, ix1, y0 + s), radius=max(2, r // 2), fill=fill)
    d.rounded_rectangle(left, radius=r, outline=stroke, width=max(3, s // 10))
    d.rounded_rectangle(right, radius=r, outline=stroke, width=max(3, s // 10))


def caption(img, d, text):
    """Dark caption bar at the bottom; returns the y where content must stop."""
    cf = f(SANS, 38)
    lines = wrap(d, text, cf, W - 260)
    lh = 50
    barh = max(170, len(lines) * lh + 64)
    d.rectangle((0, H - barh, W, H), fill=INK)
    y = H - barh + (barh - len(lines) * lh) // 2
    for ln in lines:
        w = text_w(d, ln, cf)
        d.text(((W - w) // 2, y), ln, font=cf, fill=(230, 234, 238))
        y += lh
    return H - barh


def base(bg):
    img = Image.new("RGB", (W, H), bg)
    return img, ImageDraw.Draw(img)


def centered(d, lines_fonts, cy, gap=26, accent_runs=None):
    """Draw a stack of (text, font, color) centered on cy."""
    heights = [font.getbbox(t)[3] for t, font, _ in lines_fonts]
    total = sum(heights) + gap * (len(lines_fonts) - 1)
    y = cy - total // 2
    for i, (t, font, color) in enumerate(lines_fonts):
        w = text_w(d, t, font)
        d.text(((W - w) // 2, y), t, font=font, fill=color, stroke_width=2, stroke_fill=color)
        y += heights[i] + gap


# ---- scene renderers ------------------------------------------------------

def scene_title(sc):
    img, d = base(TEAL)
    cy = (H - 180) // 2
    mark(d, W // 2, cy - 150, 150, WHITE, WHITE)
    wf = f(SANS, 150)
    true_w = text_w(d, "true", wf); set_w = text_w(d, "set", wf)
    x = (W - (true_w + set_w)) // 2
    d.text((x, cy + 10), "true", font=wf, fill=WHITE, stroke_width=2, stroke_fill=WHITE)
    d.text((x + true_w, cy + 10), "set", font=wf, fill=(190, 240, 232), stroke_width=2, stroke_fill=(190, 240, 232))
    sf = f(SANS, 46)
    sub = sc["subtitle"]; sw = text_w(d, sub, sf)
    d.text(((W - sw) // 2, cy + 200), sub, font=sf, fill=(200, 232, 228))
    caption(img, d, sc["narration"]); return img


def scene_outro(sc):
    img, d = base(TEAL)
    stop = caption(img, d, sc["narration"])
    mark(d, W // 2, stop // 2 - 110, 120, WHITE, WHITE)
    tf = f(SANS, 92)
    t = sc["title"]; w = text_w(d, t, tf)
    d.text(((W - w) // 2, stop // 2 + 20), t, font=tf, fill=WHITE, stroke_width=2, stroke_fill=WHITE)
    return img


def scene_statement(sc):
    img, d = base(PAPER)
    stop = caption(img, d, sc["narration"])
    bf = f(SANS, 86)
    lf = [(ln, bf, INK if not (sc.get("accent") and i == len(sc["lines"]) - 1) else TEAL_INK)
          for i, ln in enumerate(sc["lines"])]
    centered(d, lf, stop // 2)
    return img


def scene_list(sc):
    img, d = base(PAPER)
    stop = caption(img, d, sc["narration"])
    hf = f(SANS, 70); itf = f(MONO, 50)
    hw = text_w(d, sc["heading"], hf)
    d.text(((W - hw) // 2, stop // 2 - 180), sc["heading"], font=hf, fill=INK, stroke_width=2, stroke_fill=INK)
    row = " · ".join(sc["items"]); rw = text_w(d, row, itf)
    d.rounded_rectangle(((W - rw) // 2 - 40, stop // 2 - 20, (W + rw) // 2 + 40, stop // 2 + 90),
                        radius=16, fill=WHITE, outline=LINE, width=2)
    d.text(((W - rw) // 2, stop // 2 + 12), row, font=itf, fill=SLATE)
    return img


def scene_panel(sc):
    img, d = base(PAPER)
    stop = caption(img, d, sc["narration"])
    pw, ph = 1120, 520
    px, py = (W - pw) // 2, stop // 2 - ph // 2
    d.rounded_rectangle((px, py, px + pw, py + ph), radius=24, fill=WHITE, outline=LINE, width=2)
    hf = f(MONO, 34)
    d.text((px + 46, py + 34), "trueset reconcile · warehouse ⇄ source", font=hf, fill=SLATE)
    d.ellipse((px + 46 - 2, py + 36, px + 46 + 14, py + 52), fill=TEAL) if False else None
    rows = [("row_count_parity", "pass", PASS), ("referential_integrity", "fail · 1", FAIL),
            ("value_parity", "fail · 3", FAIL)]
    nf = f(MONO, 42); pf = f(MONO, 34)
    ry = py + 110
    for name, tag, col in rows:
        d.line((px + 40, ry, px + pw - 40, ry), fill=LINE, width=2)
        d.text((px + 48, ry + 26), name, font=nf, fill=INK)
        tw = text_w(d, tag, pf)
        bg = (234, 245, 238) if col == PASS else (251, 236, 234)
        d.rounded_rectangle((px + pw - 60 - tw - 36, ry + 24, px + pw - 60 + 6, ry + 70),
                            radius=22, fill=bg)
        d.text((px + pw - 60 - tw - 15, ry + 30), tag, font=pf, fill=col)
        ry += 96
    d.rounded_rectangle((px + 1, ry + 8, px + pw - 1, py + ph - 1), radius=24, fill=WASH)
    note = "Row counts matched. The values didn't."
    bf = f(SANS, 40); nw = text_w(d, note, bf)
    d.text((px + 46, ry + 34), note, font=bf, fill=INK, stroke_width=1, stroke_fill=INK)
    return img


def scene_terminal(sc):
    img, d = base(PAPER)
    stop = caption(img, d, sc["narration"])
    tw_, th = 1120, 300
    tx, ty = (W - tw_) // 2, stop // 2 - th // 2
    d.rounded_rectangle((tx, ty, tx + tw_, ty + th), radius=20, fill=(18, 22, 26))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((tx + 36 + i * 34, ty + 30, tx + 36 + i * 34 + 20, ty + 50), fill=c)
    mf = f(MONO, 54)
    d.text((tx + 48, ty + 150), "$ ", font=mf, fill=(127, 209, 196))
    d.text((tx + 48 + text_w(d, "$ ", mf), ty + 150), sc["cmd"], font=mf, fill=(223, 228, 234))
    return img


RENDER = {"title": scene_title, "statement": scene_statement, "list": scene_list,
          "panel": scene_panel, "terminal": scene_terminal, "outro": scene_outro}

# ---- scenes (Video 01) ----------------------------------------------------
SCENES = [
    {"type": "title", "subtitle": "open-source data quality & reconciliation",
     "narration": "This is trueset, an open-source data quality tool. Let me show you the problem it solves."},
    {"type": "statement", "lines": ["Your pipeline passed every test.", "The numbers are still wrong."], "accent": True,
     "narration": "If you work with data, you've shipped a pipeline that passed every check, and still delivered wrong numbers. No job failed. No alert fired. But the total in the warehouse didn't match the source."},
    {"type": "list", "heading": "Most tools check one table at a time.", "items": ["dbt tests", "Great Expectations", "Soda"],
     "narration": "Tools like these are good, but they check one table at a time. They can't see the problems that live between systems. A value that quietly changed on the way in. A row that vanished in a pipeline hop."},
    {"type": "panel",
     "narration": "trueset catches exactly that. It compares two systems row by row, so silent corruption can't hide behind matching totals."},
    {"type": "statement", "lines": ["Write once. Run anywhere.", "pandas · DuckDB · your warehouse"], "accent": True,
     "narration": "And you write a check once. It runs unchanged on pandas, on DuckDB, or pushed straight into your warehouse."},
    {"type": "terminal", "cmd": "pip install trueset",
     "narration": "It's open source, Apache licensed, and it's one pip install. Free, on PyPI today."},
    {"type": "outro", "title": "Next  →  your first check",
     "narration": "In the next video, I'll show you your first check. From nothing to a passing validation, in two minutes. Let's go."},
]

OUT = os.path.join(os.path.dirname(__file__), "out", "01-what-is-trueset.mp4")


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip())


def main():
    work = tempfile.mkdtemp(prefix="trueset_vid_")
    clips = []
    for i, sc in enumerate(SCENES):
        frame = os.path.join(work, f"f{i}.png")
        RENDER[sc["type"]](sc).save(frame)
        # narration via say (scratch voice)
        txt = os.path.join(work, f"n{i}.txt")
        open(txt, "w").write(sc["narration"])
        aiff = os.path.join(work, f"a{i}.aiff")
        run(["say", "-v", "Samantha", "-r", "178", "-f", txt, "-o", aiff])
        d = dur(aiff) + 0.6
        clip = os.path.join(work, f"c{i}.mp4")
        run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", frame, "-i", aiff,
             "-af", "apad=pad_dur=0.6", "-t", f"{d:.2f}", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-r", "30", clip])
        clips.append(clip)
        print(f"scene {i} ({sc['type']}): {d:.1f}s")
    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join(f"file '{c}'\n" for c in clips))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", OUT])
    print("TOTAL:", round(sum(dur(c) for c in clips), 1), "s ->", OUT)


if __name__ == "__main__":
    main()
