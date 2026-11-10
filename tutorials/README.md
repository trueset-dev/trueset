# trueset tutorial series — production plan

A series of **short, single-idea videos** (60s–3min each) for the LinkedIn launch.
Short beats long: one idea per video, post one every few days through November.

Each script is written to sound **natural when read aloud** — short sentences,
first person, founder voice. Record them in **your own voice**: for an
open-source founder launch, authentic > polished, and it's the opposite of
"sounds like AI."

## The series (ordered)

| # | Title | ~Len | Goal | Status |
|---|-------|------|------|--------|
| 01 | What is trueset & why | 90s | The hook: checks pass, data's still wrong between systems | ✅ script ready |
| 02 | Your first check | 2m | Install → write checks.yml → run → read result → exit code | ✅ script ready |
| 03 | The check library | 2–3m | Tour the 15 checks; warn vs error; `suggest` to auto-draft | ⬜ |
| 04 | Cross-system reconciliation (the headline) | 3m | row_count_parity / referential_integrity / value_parity | ⬜ |
| 05 | Validate in your pipeline + quarantine | 2–3m | Python API, shift-left gate, split good/bad rows | ⬜ |
| 06 | Corroboration & ambiguity | 3m | Is an extreme value real or wrong? (commodities-grade) | ⬜ |
| 07 | Governance & reporting | 2m | owner/sensitivity/regulation, `report --by` | ⬜ |
| 08 | Monitoring & history | 2m | `--save`, `monitor` for anomalies, `freshness` | ⬜ |
| 09 | Runs on any engine | 2m | pandas / DuckDB / warehouse — same check | ⬜ |

(We can also do a 30–45s "sizzle" cut from clips of these for the launch post.)

## How to record (all free unless noted)

**Screen capture**
- **QuickTime** (built into your Mac): File → New Screen Recording. Simplest.
- **OBS Studio** (free): more control, good if you want webcam-in-corner.
- Before recording: bump your terminal font size (so it's readable on a phone),
  use a clean prompt, and record at 1080p. Most LinkedIn viewers are on mobile.

**Your voice**
- Any decent mic works — even AirPods are fine; a $60–100 USB mic (e.g. a Fifine
  or Samson) is a noticeable step up. Record in a quiet, soft room (not a bare,
  echoey one).
- Read the script, but don't sound like you're reading — talk to one person.
  It's fine to go off-script and say it your way; the script is a safety net.

**Editing**
- **Descript** (free tier) is ideal here: it transcribes your audio, lets you edit
  video by editing *text*, and removes "um"s in one click. Great for talking-to-
  screen tutorials.
- **CapCut** or **iMovie** (both free) also work.
- **Add captions.** Most LinkedIn viewers watch muted — captions roughly double
  watch time. Descript/CapCut auto-generate them.

**Workflow per video**
1. Open the script. Have the demo files ready (they're in `examples/`).
2. Do a dry run of the commands once so nothing surprises you on camera.
3. Record screen + voice (together, or voice-over after — your call).
4. Edit, caption, export vertical (9:16) or square (1:1) for LinkedIn feed.

## The demo environment

Every script uses the real files already in the repo so viewers can follow
along exactly:
- `examples/orders.csv` — a small orders dataset (has deliberate problems)
- `examples/checks.yml` — a single-source check suite
- `examples/warehouse_orders.csv` + `examples/source_orders.csv` — two "systems"
- `examples/reconcile.yml` — a reconciliation suite

Tell the viewer: `pip install trueset`, then `git clone` the repo (or download the
examples) to follow along.

---

**Next:** read script **01** aloud. If the tone fits your voice, I'll write 03–09
in the same style. If it feels too stiff / too casual / too long — tell me and
I'll retune before producing the rest.
