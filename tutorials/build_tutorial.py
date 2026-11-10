#!/usr/bin/env python3
"""Build a REAL step-by-step terminal tutorial (16:9, YouTube).

Each step is an actual recorded terminal session — commands typed live, real
trueset output (asciinema -> agg) — framed on a branded canvas with a step
label and a narration caption, with `say` voice-over (scratch; swap your own).

This records the tool actually running. It is not a mockup.

Usage: python tutorials/build_tutorial.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

ROOT = "/Users/admin/Downloads/validate-assay"
SCR = "/private/tmp/claude-501/-Users-admin-Downloads-validate-assay/b54112a9-1a54-4e1f-a799-2d143cf7b8e9/scratchpad"
W, H, FPS = 1920, 1080, 30
PAPER = (244, 246, 248); INK = (20, 24, 27); SLATE = (78, 87, 95)
TEAL = (15, 118, 110); TEAL_INK = (11, 95, 88); LINE = (224, 228, 232); WHITE = (255, 255, 255)
SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
COLS = 100
TOP = 168                       # terminal top y
SIDE = 90

work = tempfile.mkdtemp(prefix="trueset_tut_")


def ff(p, s): return ImageFont.truetype(p, s)
def run(c, **k): subprocess.run(c, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **k)
def probe(p, s): return subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", s, "-of", "csv=p=0:s=,", p], capture_output=True, text=True).stdout.strip()
def dur(p): return float(probe(p, "format=duration"))


def wrap(d, s, fn, mx):
    out, cur = [], ""
    for wd in s.split():
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=fn) > mx and cur:
            out.append(cur); cur = wd
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def demo_dir():
    d = os.path.join(SCR, "demo02")
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    shutil.copy(os.path.join(ROOT, "examples/orders.csv"), d)
    open(os.path.join(d, "checks.yml"), "w").write(
        "suite: orders_quality\n"
        "checks:\n"
        "  - type: not_null\n    column: order_id\n"
        "  - type: unique\n    column: order_id\n"
        "  - type: in_range\n    column: amount\n    min: 0\n"
        "  - type: in_set\n    column: status\n    values: [pending, shipped, delivered, cancelled]\n"
    )
    return d


def record(cmds, rows, name):
    """Record a live terminal session of `cmds` -> an mp4 clip (native size)."""
    ddir = os.path.join(SCR, "demo02")
    sh = os.path.join(work, f"{name}.sh")
    body = [
        "#!/bin/bash", f"cd {ddir}", f"source {ROOT}/.venv/bin/activate",
        "export FORCE_COLOR=1 COLUMNS=100 PS1=''", "set +e",
        "typecmd(){ printf '\\033[38;5;37m$\\033[0m '; s=\"$1\";",
        "  for((i=0;i<${#s};i++)); do printf '%s' \"${s:$i:1}\"; sleep 0.035; done;",
        "  printf '\\n'; eval \"$s\"; }",
        "sleep 0.5",
    ]
    for c in cmds:
        body.append(f'typecmd {sh_quote(c)}')
        body.append("sleep 1.6")
    open(sh, "w").write("\n".join(body) + "\n")
    cast = os.path.join(work, f"{name}.cast")
    run(["asciinema", "rec", "--overwrite", "--cols", str(COLS), "--rows", str(rows),
         "-c", f"bash {sh}", cast])
    gif = os.path.join(work, f"{name}.gif")
    run(["agg", "--font-size", "23", "--theme", "asciinema", "--line-height", "1.4", cast, gif])
    mp4 = os.path.join(work, f"{name}_term.mp4")
    run(["ffmpeg", "-y", "-i", gif, "-movflags", "+faststart", "-pix_fmt", "yuv420p",
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", mp4])
    return mp4


def sh_quote(s): return "'" + s.replace("'", "'\\''") + "'"


def wordmark(d, x, y, size):
    wf = ff(SANS, size)
    d.text((x, y), "true", font=wf, fill=INK)
    d.text((x + d.textlength("true", font=wf), y), "set", font=wf, fill=TEAL_INK)


def step_bg(label, narration):
    """Branded canvas with header + caption; returns (png_path, term_area)."""
    img = Image.new("RGB", (W, H), PAPER); d = ImageDraw.Draw(img)
    wordmark(d, SIDE, 54, 40)
    lf = ff(SANS, 34)
    d.text((SIDE, 112), label, font=lf, fill=SLATE)
    d.line((SIDE, 150, W - SIDE, 150), fill=LINE, width=2)
    cf = ff(SANS, 33); lines = wrap(d, narration, cf, W - 2 * 150); lh = 44
    bh = max(130, len(lines) * lh + 48)
    d.rectangle((0, H - bh, W, H), fill=INK)
    y = H - bh + (bh - len(lines) * lh) // 2
    for ln in lines:
        d.text(((W - d.textlength(ln, font=cf)) // 2, y), ln, font=cf, fill=(230, 234, 238)); y += lh
    p = os.path.join(work, f"bg_{abs(hash(label)) % 99999}.png"); img.save(p)
    area = (SIDE, TOP, W - SIDE, H - bh - 24)   # x0,y0,x1,y1 for the terminal
    return p, area


def card(text_lines, sub, bg, fg, accent, name):
    img = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(img)
    mf = ff(SANS, 96); total = len(text_lines) * 112
    y = (H - total) // 2 - 40
    for ln in text_lines:
        d.text(((W - d.textlength(ln, font=mf)) // 2, y), ln, font=mf, fill=fg, stroke_width=2, stroke_fill=fg); y += 112
    if sub:
        sf = ff(SANS, 44)
        d.text(((W - d.textlength(sub, font=sf)) // 2, y + 20), sub, font=sf, fill=accent)
    p = os.path.join(work, f"card_{name}.png"); img.save(p)
    return p


def say(text, name):
    txt = os.path.join(work, f"{name}.txt"); open(txt, "w").write(text)
    a = os.path.join(work, f"{name}.aiff")
    run(["say", "-v", "Samantha", "-r", "178", "-f", txt, "-o", a])
    return a, dur(a)


def card_clip(png, narration, name):
    a, ad = say(narration, name); d = ad + 0.7
    out = os.path.join(work, f"{name}.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", png, "-i", a,
         "-af", "apad=pad_dur=0.7", "-t", f"{d:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-r", str(FPS), out])
    return out


def step_clip(cmds, rows, label, narration, name):
    term = record(cmds, rows, name)
    tw, th = (int(x) for x in probe(term, "stream=width,height").split(","))
    bg, (ax0, ay0, ax1, ay1) = step_bg(label, narration)
    aw, ah = ax1 - ax0, ay1 - ay0
    scale = min(1.0, aw / tw, ah / th)
    sw, sh = int(tw * scale) // 2 * 2, int(th * scale) // 2 * 2
    ox, oy = (W - sw) // 2, ay0
    a, ad = say(narration, name + "_v")
    td = dur(term); target = max(td, ad) + 0.8
    out = os.path.join(work, f"{name}.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-i", bg, "-i", term, "-i", a,
         "-filter_complex", f"[1:v]scale={sw}:{sh}[t];[0:v][t]overlay={ox}:{oy}:eof_action=repeat[v]",
         "-map", "[v]", "-map", "2:a", "-af", "apad", "-t", f"{target:.2f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", out])
    print(f"  {name}: term {td:.1f}s, narr {ad:.1f}s -> {target:.1f}s")
    return out


def concat(clips, out):
    lst = os.path.join(work, "list.txt")
    # normalize all to same params already; concat via demuxer needs same codec/tbn -> re-encode safe
    open(lst, "w").write("".join(f"file '{c}'\n" for c in clips))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", out])


def main():
    demo_dir()
    clips = []
    clips.append(card_clip(
        card(["Your first check"], "trueset · tutorial 02", TEAL, WHITE, (190, 240, 232), "title"),
        "Welcome to trueset. In this tutorial we'll write your first data quality check and run it, from scratch.",
        "c_title"))
    clips.append(step_clip(
        ["cat orders.csv"], 12, "Step 1 · Your data",
        "Here's our data: a small orders file. An id, an amount, a status, an email. A few rows in here are bad. Let's catch them with trueset.",
        "s_data"))
    clips.append(step_clip(
        ["cat checks.yml"], 16, "Step 2 · Write the checks",
        "This is our checks file, in plain YAML. We say order_id is never empty, and unique. amount is never negative. And status must be one of these four values.",
        "s_checks"))
    clips.append(step_clip(
        ["trueset run --data orders.csv --checks checks.yml; echo \"exit code: $?\""], 20, "Step 3 · Run it",
        "Now we run it. trueset checks every rule against the data. not_null passes. But it caught a duplicate id, an amount below zero, and a status that should not exist. And notice the exit code is one. That non-zero code is what lets trueset stop a C I pipeline when data is bad.",
        "s_run"))
    clips.append(step_clip(
        ["trueset suggest --data orders.csv | head -n 16"], 20, "Step 4 · Draft from your data",
        "And if you don't want to write checks by hand, trueset suggest profiles your data and drafts a starter suite for you to review and edit. You stay in control of what ships.",
        "s_suggest"))
    clips.append(card_clip(
        card(["Next up: the check library"], "trueset · tutorial 03", TEAL, WHITE, (190, 240, 232), "outro"),
        "That's your first check. In the next tutorial, we'll go through the full library of checks you can use. See you there.",
        "c_outro"))
    out = os.path.join(ROOT, "tutorials/out/02-your-first-check.mp4")
    concat(clips, out)
    print("DONE", round(dur(out), 1), "s ->", out)


if __name__ == "__main__":
    main()
