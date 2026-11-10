"""Centralized 'Data Trust' dashboard -- the Hub view, generated locally.

Reads the results history (`ResultStore`, populated by `trueset run --save`) and
renders ONE self-contained, chart-rich HTML page (premium light theme): a
trust-score hero with a trust-over-time chart, checks & throughput charts, the
shift-left data flow (rows checked vs. rerouted to quarantine), health by
data-quality dimension, a dense asset table, and an open-incident feed.

No server, no cloud, no new dependencies -- it reads data trueset already
produces. The open-source seed of the hosted hub (TrueSet Cloud).
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, timezone

from .monitoring import detect_anomaly

TEAL = "#0F766E"
GOOD = "#0E9F6E"
FAIL = "#D6454A"
WARN = "#B9822B"
_SENSITIVE = {"confidential", "pii", "pci", "phi"}

_DIM = {
    "not_null": "Completeness", "columns_exist": "Completeness",
    "in_set": "Validity", "in_range": "Validity", "matches_regex": "Validity", "metric": "Validity",
    "unique": "Uniqueness", "no_duplicate_rows": "Uniqueness",
    "row_count": "Volume",
    "row_count_parity": "Reconciliation", "referential_integrity": "Reconciliation",
    "value_parity": "Reconciliation", "corroboration": "Reconciliation",
    "source_corroboration": "Reconciliation",
}
_DIM_CHECKS = ["Completeness", "Validity", "Uniqueness", "Volume", "Reconciliation"]
_DIM_ICON = {"Freshness": "clock", "Completeness": "check", "Validity": "shield",
             "Uniqueness": "hash", "Volume": "bars", "Reconciliation": "compare"}
_ICONS = {
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "flow": '<line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    "dims": '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "datasets": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>',
    "incidents": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/>',
    "check": '<polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
    "hash": '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
    "bars": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "compare": '<circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><path d="M11 18H8a2 2 0 0 1-2-2V9"/>',
}


def _icon(name):
    return ('<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">' + _ICONS.get(name, "") + "</svg>")


def _band(score):
    return GOOD if score >= 95 else WARN if score >= 80 else FAIL


def _age_h(iso):
    try:
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600


def _rel(iso):
    h = _age_h(iso)
    if h is None:
        return iso
    if h < 1 / 40:
        return "just now"
    for u, s in (("d", 24), ("h", 1), ("m", 1 / 60)):
        if h >= s:
            return f"{int(h // s)}{u} ago"
    return "just now"


# ---- charts ---------------------------------------------------------------

def _area_chart(series, color=TEAL, w=1000, h=210):
    if not series:
        return ""
    if len(series) == 1:
        series = series + series
    vals = [v for _, v in series]
    pl, pr, pt, pb = 12, 32, 16, 26
    iw, ih = w - pl - pr, h - pt - pb
    ymin = max(0.0, min(min(vals) - 0.08, 0.5))
    rng = (1.0 - ymin) or 1
    n = len(series)
    def X(i): return pl + (i / (n - 1)) * iw
    def Y(v): return pt + (1 - (v - ymin) / rng) * ih
    pts = [(X(i), Y(v)) for i, (_, v) in enumerate(series)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"M{pl},{pt + ih:.1f} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L{X(n - 1):.1f},{pt + ih:.1f} Z"
    grid = ""
    for gv in (1.0, 0.75, 0.5):
        if gv < ymin - 1e-6:
            continue
        gy = Y(gv)
        grid += f'<line class="gl" x1="{pl}" y1="{gy:.1f}" x2="{pl + iw}" y2="{gy:.1f}"/>'
        grid += f'<text class="gll" x="{pl + iw + 6}" y="{gy + 3:.1f}">{int(gv * 100)}</text>'
    xl = "".join(f'<text class="xll" x="{X(i):.1f}" y="{h - 7}" text-anchor="middle">{series[i][0]}</text>'
                 for i in sorted({0, n // 2, n - 1}))
    dots = "".join(f'<circle class="pt" cx="{x:.1f}" cy="{y:.1f}" r="8" data-v="{round(series[i][1] * 100)}% · {series[i][0]}"/>'
                   for i, (x, y) in enumerate(pts))
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" style="width:100%;display:block">'
            f'<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{color}" stop-opacity=".16"/><stop offset=".9" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'{grid}<path d="{area}" fill="url(#ag)"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="4" fill="{color}" stroke="#fff" stroke-width="2"/>'
            f'{xl}<g fill="transparent">{dots}</g></svg>')


def _stack_bars(series, w=480, h=150):
    if not series:
        return ""
    pl, pr, pt, pb = 8, 8, 10, 24
    iw, ih = w - pl - pr, h - pt - pb
    maxt = max((p + f for _, p, f in series), default=1) or 1
    n = len(series)
    slot = iw / n
    bw = min(slot * 0.5, 30)
    out = ""
    for i, (lab, p, f) in enumerate(series):
        cx = pl + slot * (i + 0.5)
        x = cx - bw / 2
        ph, fh = (p / maxt) * ih, (f / maxt) * ih
        yp = pt + ih - ph
        out += f'<rect x="{x:.1f}" y="{yp:.1f}" width="{bw:.1f}" height="{ph:.1f}" rx="3" fill="{TEAL}"/>'
        if fh > 0.4:
            out += f'<rect x="{x:.1f}" y="{yp - fh:.1f}" width="{bw:.1f}" height="{max(fh, 2):.1f}" rx="2" fill="{FAIL}"/>'
        out += f'<text class="xll" x="{cx:.1f}" y="{h - 7}" text-anchor="middle">{lab}</text>'
    return f'<svg class="chart" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" style="width:100%;display:block">{out}</svg>'


def _vol_bars(series, w=480, h=150):
    if not series:
        return ""
    pl, pr, pt, pb = 8, 8, 10, 24
    iw, ih = w - pl - pr, h - pt - pb
    maxt = max((t for _, t, _ in series), default=1) or 1
    n = len(series)
    slot = iw / n
    bw = min(slot * 0.5, 30)
    out = ""
    for i, (lab, tot, q) in enumerate(series):
        cx = pl + slot * (i + 0.5)
        x = cx - bw / 2
        th = (tot / maxt) * ih
        y = pt + ih - th
        qh = (q / maxt) * ih if tot else 0
        out += f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{th:.1f}" rx="3" fill="{TEAL}" opacity=".28"/>'
        if qh > 0.3:
            out += f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(qh, 2.5):.1f}" rx="2" fill="{FAIL}"/>'
        out += f'<text class="xll" x="{cx:.1f}" y="{h - 7}" text-anchor="middle">{lab}</text>'
    return f'<svg class="chart" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet" style="width:100%;display:block">{out}</svg>'


def _spark(rates, w=100, h=28):
    if not rates:
        return ""
    if len(rates) == 1:
        rates = [rates[0], rates[0]]
    n, pad = len(rates), 3
    pts = [((pad + i / (n - 1) * (w - 2 * pad)), (h - pad - max(0.0, min(1.0, r)) * (h - 2 * pad)))
           for i, r in enumerate(rates)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    col = GOOD if rates[-1] >= 0.999 else FAIL
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.3" fill="{col}"/></svg>')


def _delta(pts):
    if pts >= 0.5:
        return f'<span class="delta up">&uarr; {pts:.0f} pts</span>'
    if pts <= -0.5:
        return f'<span class="delta down">&darr; {abs(pts):.0f} pts</span>'
    return '<span class="delta flat">&ndash; steady</span>'


def _kpi(value, label, tone=""):
    return f'<div class="kpi {tone}"><div class="kpi-v">{value}</div><div class="kpi-l">{label}</div></div>'


def _dim_tile(name, score, sub):
    ic = f'<span class="dim-name">{_icon(_DIM_ICON.get(name, ""))}{name}</span>'
    if score is None:
        return (f'<div class="dim none"><div class="dim-top">{ic}<span class="dim-pct">&mdash;</span></div>'
                f'<div class="dim-bar"></div><div class="dim-sub">no coverage</div></div>')
    c = _band(score)
    return (f'<div class="dim"><div class="dim-top">{ic}<span class="dim-pct" style="color:{c}">{score}%</span></div>'
            f'<div class="dim-bar"><i style="width:{score}%;background:{c}"></i></div>'
            f'<div class="dim-sub">{sub}</div></div>')


def build_dashboard_html(store, limit=400):
    runs = store.runs(limit=limit)
    generated = datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
    try:
        source = f"{store.engine.dialect.name} · {len(runs)} runs"
    except Exception:
        source = f"{len(runs)} runs"
    nav = dict(ov=_icon("overview"), fl=_icon("flow"), dm=_icon("dims"),
               ds=_icon("datasets"), inc=_icon("incidents"))

    if not runs:
        empty = ('<div class="empty"><h2>No runs yet</h2><p>Save a run, then refresh:</p>'
                 "<pre>trueset run --data orders.csv --checks checks.yml \\\n"
                 "  --save sqlite:///trueset_history.db</pre></div>")
        return _PAGE.format(generated=generated, source=source, score="—", delta="", trustchart="",
                            range="", kpis="", checkschart="", volchart="", flow=empty, dims="",
                            rows="", incidents="", **nav)

    by_suite = defaultdict(list)
    for r in runs:
        by_suite[r["suite"]].append(r)

    day = defaultdict(lambda: [0, 0, 0, 0])  # date -> [pass, total, rows, quar]
    for r in runs:
        d = day[r["ts"][:10]]
        tot = r["n_pass"] + r["n_fail"] + r["n_error"]
        d[0] += r["n_pass"]
        d[1] += tot
        d[2] += r["rows"] or 0
        d[3] += r.get("rows_quarantined") or 0
    days = sorted(day)
    def lbl(dk): return datetime.fromisoformat(dk).strftime("%b %d")
    trust_series = [(lbl(dk), (day[dk][0] / day[dk][1] if day[dk][1] else 1.0)) for dk in days]
    checks_series = [(lbl(dk), day[dk][0], day[dk][1] - day[dk][0]) for dk in days]
    vol_series = [(lbl(dk), day[dk][2], day[dk][3]) for dk in days]
    trust_delta = (trust_series[-1][1] - trust_series[0][1]) * 100 if len(trust_series) > 1 else 0
    span = f"{lbl(days[0])} – {lbl(days[-1])}" if len(days) > 1 else lbl(days[-1])

    datasets, incidents = [], []
    dim_counts = {d: [0, 0] for d in _DIM_CHECKS}
    tp = tc = sensitive_fail = win_rows = win_quar = 0
    for suite in sorted(by_suite):
        sruns = by_suite[suite]
        latest = sruns[0]
        results = store.results(latest["run_id"])
        total = latest["n_pass"] + latest["n_fail"] + latest["n_error"]
        rate = latest["n_pass"] / total if total else 1.0
        trend = [(r["n_pass"] / (r["n_pass"] + r["n_fail"] + r["n_error"]))
                 if (r["n_pass"] + r["n_fail"] + r["n_error"]) else 1.0 for r in reversed(sruns)]
        tp += latest["n_pass"]
        tc += total
        win_rows += sum(r["rows"] or 0 for r in sruns)
        win_quar += sum(r.get("rows_quarantined") or 0 for r in sruns)
        vol_anom = False
        vol_hist = [r["rows"] for r in reversed(sruns) if r["rows"] is not None]
        if len(vol_hist) >= 4:
            va = detect_anomaly(vol_hist, sigma=3.0, method="mad")
            if va.get("anomaly"):
                vol_anom = True
                cur = int(va["current"])
                ctr = va.get("center")
                drc = "dropped" if (ctr is not None and cur < ctr) else "spiked"
                base = f"~{ctr:,.0f} baseline" if ctr is not None else "its baseline"
                sc = f" · {abs(va['score']):.1f}\u03c3" if va.get("score") is not None else ""
                incidents.append({"dataset": latest.get("dataset") or suite, "check": "volume",
                                  "column": None, "severity": "error",
                                  "message": f"row volume {drc} to {cur:,} vs {base}{sc}",
                                  "ts": latest["ts"], "rank": 0})
        for r in results:
            d = _DIM.get(r["check"])
            if d in dim_counts:
                dim_counts[d][1] += 1
                if r["status"] == "pass":
                    dim_counts[d][0] += 1
            if r["status"] != "pass":
                if r.get("meta"):
                    try:
                        if json.loads(r["meta"]).get("sensitivity") in _SENSITIVE:
                            sensitive_fail += 1
                    except Exception:
                        pass
                incidents.append({"dataset": latest.get("dataset") or suite, "check": r["check"],
                                  "column": r.get("column"), "severity": r.get("severity", "error"),
                                  "message": (r.get("message") or "").strip(), "ts": latest["ts"],
                                  "rank": 0 if r.get("severity") != "warn" else 1})
        age = _age_h(latest["ts"]) or 0
        fresh_fail = any(r["check"] == "freshness" and r["status"] != "pass" for r in results)
        fstate = "stale" if (age >= 72 or fresh_fail) else "aging" if age >= 24 else "fresh"
        if fstate != "fresh":
            incidents.append({"dataset": latest.get("dataset") or suite, "check": "freshness", "column": None,
                              "severity": "error" if fstate == "stale" else "warn",
                              "message": f"data is {_rel(latest['ts']).replace(' ago', ' old')} (SLA 24h)",
                              "ts": latest["ts"], "rank": 0 if fstate == "stale" else 1})
        # Holistic status. A dataset that passes every check but has an open
        # condition -- a volume anomaly, or a freshness breach -- is NOT healthy;
        # it's a Warning, so the table badge matches the incident feed below it.
        if not latest["passed"]:
            status = "fail"
        elif vol_anom or fstate != "fresh":
            status = "warn"
        else:
            status = "pass"
        datasets.append({"suite": suite, "dataset": latest.get("dataset") or suite, "passed": bool(latest["passed"]),
                         "status": status,
                         "rate": rate, "n_pass": latest["n_pass"], "total": total, "rows": latest["rows"],
                         "quar": latest.get("rows_quarantined"), "age_iso": latest["ts"], "fstate": fstate,
                         "trend": trend, "vol_anom": vol_anom})

    score = round(100 * tp / tc) if tc else 100
    n_healthy = sum(1 for d in datasets if d["status"] == "pass")
    n_ds = len(datasets)
    n_fresh = sum(1 for d in datasets if d["fstate"] == "fresh")
    n_inc = len(incidents)
    kpis = "".join([
        _kpi(str(n_ds), "Datasets monitored"),
        _kpi(f"{n_healthy}/{n_ds}", "Datasets healthy", "ok" if n_healthy == n_ds else "bad"),
        _kpi(str(n_inc), "Open incidents", "bad" if n_inc else "ok"),
        _kpi(f"{win_quar:,}", "Rows rerouted · window"),
    ])

    clean = max(0, win_rows - win_quar)
    clean_pct = (clean / win_rows * 100) if win_rows else 100
    per = sorted([(d["dataset"], sum(r.get("rows_quarantined") or 0 for r in by_suite[d["suite"]])) for d in datasets],
                 key=lambda x: -x[1])
    flow_rows = "".join(f'<li><span>{html.escape(nm)}</span><b>{n:,}</b></li>' for nm, n in per if n > 0) \
        or '<li class="muted">Nothing needed rerouting in this window.</li>'
    flow = (f'<div class="flow-head"><div><div class="flow-big">{win_quar:,}</div>'
            f'<div class="flow-cap">rows rerouted to quarantine</div></div>'
            f'<div class="flow-meta">{win_rows:,} rows checked · <b style="color:{GOOD}">{clean_pct:.1f}%</b> clean throughput</div></div>'
            f'<div class="flowbar"><div class="fb-clean" style="width:{clean_pct:.2f}%"><span>{clean:,} loaded</span></div>'
            f'<div class="fb-quar" style="width:{max(100 - clean_pct, 0.6):.2f}%"></div></div>'
            f'<div class="flow-legend"><span class="lg clean">Clean &rarr; loaded</span>'
            f'<span class="lg quar">Bad &rarr; dead-letter ({win_quar:,})</span></div>'
            f'<ul class="flow-list">{flow_rows}</ul>')

    tiles = [_dim_tile("Freshness", round(100 * n_fresh / n_ds) if n_ds else None, f"{n_fresh}/{n_ds} within SLA")]
    for d in _DIM_CHECKS:
        p, t = dim_counts[d]
        tiles.append(_dim_tile(d, round(100 * p / t) if t else None, f"{p}/{t} checks" if t else "no coverage"))
    dims = "".join(tiles)

    trows = []
    _ST = {"pass": ("Passing", GOOD), "warn": ("Warning", WARN), "fail": ("Failing", FAIL)}
    for d in datasets:
        label, scol = _ST[d["status"]]
        fcol = {"fresh": GOOD, "aging": WARN, "stale": FAIL}[d["fstate"]]
        rows_txt = f'{d["rows"]:,}' if d["rows"] is not None else "—"
        rc_sty = f' style="color:{FAIL}"' if d.get("vol_anom") else ""
        rc_mk = " &#9888;" if d.get("vol_anom") else ""
        quar_txt = f'{d["quar"]:,}' if d["quar"] else ("0" if d["quar"] == 0 else "—")
        trows.append(f'<tr><td class="t-ds"><span class="s-dot" style="background:{scol}"></span>'
                     f'<span>{html.escape(d["dataset"])}<small>{html.escape(d["suite"])}</small></span></td>'
                     f'<td><span class="tag" style="color:{scol};border-color:{scol}44;background:{scol}14">'
                     f'{label}</span></td>'
                     f'<td class="t-num" style="color:{_band(d["rate"] * 100)}">{round(d["rate"] * 100)}%</td>'
                     f'<td><span class="fresh" style="color:{fcol}">{_rel(d["age_iso"])}</span></td>'
                     f'<td class="t-num t-dim"{rc_sty}>{rows_txt}{rc_mk}</td><td class="t-num t-dim">{quar_txt}</td>'
                     f'<td class="t-num">{d["n_pass"]}/{d["total"]}</td>'
                     f'<td class="t-trend">{_spark(d["trend"])}</td></tr>')
    rows = "".join(trows)

    incidents.sort(key=lambda x: (x["rank"], x["dataset"]))
    if incidents:
        items = []
        for inc in incidents[:10]:
            col = f'<span class="inc-col">{html.escape(inc["column"])}</span>' if inc["column"] else ""
            sev = "warn" if inc["severity"] == "warn" else "err"
            items.append(f'<li><span class="inc-sev {sev}"></span><span class="inc-ds">{html.escape(inc["dataset"])}</span>'
                         f'<span class="inc-ck">{html.escape(inc["check"])}{col}</span>'
                         f'<span class="inc-msg">{html.escape(inc["message"])}</span>'
                         f'<span class="inc-age">{_rel(inc["ts"])}</span></li>')
        inc_html = f'<ul class="inc">{"".join(items)}</ul>'
    else:
        inc_html = '<div class="allclear">✓ No open incidents — every monitored dataset is healthy.</div>'

    return _PAGE.format(
        generated=generated, source=source, score=score, delta=_delta(trust_delta),
        trustchart=_area_chart(trust_series, TEAL), range=span, kpis=kpis,
        checkschart=_stack_bars(checks_series), volchart=_vol_bars(vol_series),
        flow=flow, dims=dims, rows=rows, incidents=inc_html, **nav)


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>trueset · data trust</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
 :root{{--bg:#F5F6F8;--panel:#FFFFFF;--panel-2:#FAFBFC;--surface:#F1F4F6;--border:#E8EBEF;
  --text:#141A21;--text-2:#5B6774;--muted:#98A2AE;--teal:#0F766E;--teal2:#14B8A6;
  --good:#0E9F6E;--fail:#D6454A;--warn:#B9822B;
  --sans:'Inter',-apple-system,Segoe UI,Roboto,sans-serif;--mono:'JetBrains Mono',ui-monospace,Menlo,monospace;
  --sh:0 1px 2px rgba(17,24,39,.04),0 1px 3px rgba(17,24,39,.03);--sh2:0 1px 2px rgba(17,24,39,.04),0 12px 28px -18px rgba(17,24,39,.18);}}
 *{{box-sizing:border-box}}
 body{{margin:0;font-family:var(--sans);color:var(--text);background:var(--bg);-webkit-font-smoothing:antialiased;letter-spacing:-.1px}}
 a{{color:var(--teal);text-decoration:none}}
 .app{{display:grid;grid-template-columns:230px 1fr;min-height:100vh}}
 .side{{background:var(--panel);border-right:1px solid var(--border);padding:20px 15px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column}}
 .side .brand{{display:flex;align-items:center;gap:9px;font-weight:700;font-size:18px;padding:4px 8px 20px}}
 .side .brand .s{{color:var(--teal)}}
 .nav a{{display:flex;align-items:center;gap:11px;padding:8px 11px;border-radius:9px;color:var(--text-2);font-size:14px;font-weight:500;margin:2px 0}}
 .nav a:hover{{background:var(--surface);color:var(--text)}} .nav a.on{{background:rgba(15,118,110,.08);color:var(--teal)}}
 .nav a .ic{{width:16px;height:16px;color:var(--muted);flex:none}} .nav a.on .ic,.nav a:hover .ic{{color:var(--teal)}}
 .conn{{margin-top:auto;padding:12px 11px 2px;border-top:1px solid var(--border);color:var(--muted);font-family:var(--mono);font-size:11.5px;display:flex;align-items:center;gap:8px}}
 .conn .d{{width:7px;height:7px;border-radius:50%;background:var(--good);box-shadow:0 0 0 3px rgba(14,159,110,.15)}}
 main{{padding:26px 36px 72px;max-width:1280px}}
 .topbar{{display:flex;align-items:baseline;gap:13px;margin-bottom:22px}}
 .topbar h1{{margin:0;font-size:23px;font-weight:700;letter-spacing:-.7px}} .topbar .sub{{color:var(--text-2);font-size:14px}}
 .topbar .right{{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--muted)}} .topbar .right b{{color:var(--text-2);font-weight:500}}
 .tb-right{{display:flex;align-items:center;gap:14px;flex-wrap:wrap}}
 .upd{{font-family:var(--mono);font-size:12px;color:var(--muted)}} .upd b{{color:var(--text-2);font-weight:500}}
 .connect{{position:relative}}
 .connect-btn{{display:inline-flex;align-items:center;gap:7px;font-family:var(--sans);font-size:12.5px;font-weight:600;color:var(--text-2);background:var(--panel);border:1px solid var(--border);border-radius:9px;padding:7px 12px;cursor:pointer;box-shadow:var(--sh);transition:background .12s,color .12s,border-color .12s}}
 .connect-btn:hover,.connect-btn[aria-expanded="true"]{{color:var(--teal);border-color:rgba(15,118,110,.4);background:rgba(15,118,110,.06)}}
 .connect-btn .ic{{width:15px;height:15px}}
 .connect-pop{{position:absolute;top:calc(100% + 9px);right:0;width:332px;max-width:88vw;background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:0 12px 44px -10px rgba(17,24,39,.3);padding:15px;opacity:0;visibility:hidden;transform:translateY(-6px);transition:opacity .15s,transform .15s,visibility .15s;z-index:40;text-align:left}}
 .connect-pop.open{{opacity:1;visibility:visible;transform:none}}
 .cp-title{{font-size:14px;font-weight:700}}
 .cp-sub{{color:var(--text-2);font-size:12px;line-height:1.5;margin:4px 0 12px}}
 .cp-sub code{{font-family:var(--mono);font-size:11px;background:var(--surface);padding:1px 5px;border-radius:5px;color:var(--teal)}}
 .cp-list{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:1px}}
 .cp-list li{{display:flex;align-items:center;gap:11px;padding:8px;border-radius:9px;cursor:pointer}}
 .cp-list li:hover{{background:var(--surface)}}
 .wh{{width:26px;height:26px;border-radius:7px;display:inline-flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:10.5px;letter-spacing:-.3px;flex:none}}
 .wh svg{{width:15px;height:15px}}
 .wh-nm{{font-size:13px;font-weight:600;flex:1}}
 .wh-url{{font-family:var(--mono);font-size:11px;color:var(--muted)}}
 .cp-foot{{margin-top:12px;padding-top:11px;border-top:1px solid var(--border);color:var(--muted);font-size:11.5px;line-height:1.45}}
 .panel{{background:var(--panel);border:1px solid var(--border);border-radius:16px;box-shadow:var(--sh2)}}
 .pad{{padding:22px 24px}}
 .hero{{margin-bottom:16px;overflow:hidden;padding-bottom:6px}}
 .hero-top{{display:flex;align-items:flex-start;justify-content:space-between;padding:22px 24px 2px}}
 .hero-lbl{{font-family:var(--mono);font-size:11px;letter-spacing:1.4px;text-transform:uppercase;color:var(--muted)}}
 .hero-score{{display:flex;align-items:baseline;gap:14px;margin-top:6px}}
 .hero-score .n{{font-size:52px;font-weight:800;letter-spacing:-2.5px;line-height:1;font-variant-numeric:tabular-nums}}
 .hero-range{{text-align:right;font-family:var(--mono);font-size:12px;color:var(--muted);padding-top:6px}}
 .delta{{font-size:13px;font-weight:600;font-family:var(--mono);padding:3px 9px;border-radius:20px}}
 .delta.up{{color:var(--good);background:rgba(14,159,110,.1)}} .delta.down{{color:var(--fail);background:rgba(214,69,74,.1)}} .delta.flat{{color:var(--muted);background:var(--surface)}}
 .chart .gl{{stroke:var(--border);stroke-width:1}} .chart .gll,.chart .xll{{fill:var(--muted);font:10px var(--mono)}} .chart .pt{{cursor:crosshair}}
 .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}}
 .kpi{{background:var(--panel);border:1px solid var(--border);border-radius:13px;padding:16px 18px;box-shadow:var(--sh)}}
 .kpi-v{{font-family:var(--mono);font-size:26px;font-weight:700;letter-spacing:-.6px;font-variant-numeric:tabular-nums}}
 .kpi-l{{color:var(--text-2);font-size:12.5px;margin-top:4px}} .kpi.bad .kpi-v{{color:var(--fail)}} .kpi.ok .kpi-v{{color:var(--good)}}
 .sec{{display:flex;align-items:center;gap:10px;margin:26px 2px 13px}}
 .sec h2{{margin:0;font-size:12px;font-family:var(--mono);letter-spacing:1.5px;text-transform:uppercase;color:var(--text-2);font-weight:600}}
 .sec .line{{flex:1;height:1px;background:var(--border)}}
 .two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
 .ch-title{{font-size:13.5px;font-weight:600;margin-bottom:2px}} .ch-sub{{color:var(--muted);font-size:12px;margin-bottom:12px}}
 .flow-head{{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:14px}}
 .flow-big{{font-family:var(--mono);font-size:38px;font-weight:700;letter-spacing:-1.4px;color:var(--warn);line-height:1;font-variant-numeric:tabular-nums}}
 .flow-cap{{color:var(--text-2);font-size:13px;margin-top:4px}} .flow-meta{{color:var(--text-2);font-size:13.5px;font-family:var(--mono)}}
 .flowbar{{display:flex;height:30px;border-radius:9px;overflow:hidden;gap:2px;background:var(--surface)}}
 .fb-clean{{background:linear-gradient(90deg,var(--teal),var(--teal2));display:flex;align-items:center;padding:0 12px;color:#EAFBF7;font-size:12px;font-weight:600;font-family:var(--mono);white-space:nowrap;min-width:0}}
 .fb-quar{{background:repeating-linear-gradient(45deg,#E27B7F,#E27B7F 5px,#D6454A 5px,#D6454A 10px)}}
 .flow-legend{{display:flex;gap:18px;margin-top:11px;font-size:12.5px;color:var(--text-2)}}
 .flow-legend .lg::before{{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:7px;vertical-align:-1px}}
 .lg.clean::before{{background:var(--teal)}} .lg.quar::before{{background:var(--fail)}}
 .flow-list{{list-style:none;margin:16px 0 0;padding:14px 0 0;border-top:1px solid var(--border);display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px 22px}}
 .flow-list li{{display:flex;justify-content:space-between;font-size:13px;color:var(--text-2)}} .flow-list b{{font-family:var(--mono);color:var(--text)}} .flow-list .muted{{color:var(--muted)}}
 .dims{{display:grid;grid-template-columns:repeat(6,1fr);gap:13px}}
 .dim{{background:var(--panel);border:1px solid var(--border);border-radius:13px;padding:15px 16px;box-shadow:var(--sh)}} .dim.none{{opacity:.6}}
 .dim-top{{display:flex;justify-content:space-between;align-items:center}}
 .dim-name{{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600}} .dim .ic{{width:15px;height:15px;color:var(--teal)}}
 .dim-pct{{font-family:var(--mono);font-size:16px;font-weight:700;font-variant-numeric:tabular-nums}}
 .dim-bar{{height:5px;background:var(--surface);border-radius:4px;overflow:hidden;margin:11px 0 8px}} .dim-bar i{{display:block;height:100%;border-radius:4px}}
 .dim-sub{{color:var(--muted);font-size:11.5px;font-family:var(--mono)}}
 @media(max-width:1040px){{.dims{{grid-template-columns:repeat(3,1fr)}}.two{{grid-template-columns:1fr}}}}
 table{{width:100%;border-collapse:collapse;font-size:13.5px}}
 thead th{{text-align:left;font-family:var(--mono);font-size:10.5px;letter-spacing:.5px;text-transform:uppercase;color:var(--muted);font-weight:500;padding:0 14px 11px}}
 tbody td{{padding:13px 14px;border-top:1px solid var(--border)}} tbody tr:hover{{background:var(--panel-2)}}
 .t-ds{{display:flex;align-items:center;gap:10px}} .t-ds .s-dot{{width:8px;height:8px;border-radius:50%;flex:none}}
 .t-ds small{{display:block;color:var(--muted);font-family:var(--mono);font-size:11px;margin-top:1px}}
 .t-num{{font-family:var(--mono);font-weight:600;text-align:right;font-variant-numeric:tabular-nums}} .t-dim{{color:var(--text-2);font-weight:400}}
 .tag{{font-family:var(--mono);font-size:11px;padding:2px 9px;border:1px solid;border-radius:20px}}
 .fresh{{font-family:var(--mono);font-size:12.5px}} thead th.r,tbody td.t-num{{text-align:right}} .t-trend{{width:110px}}
 .inc{{list-style:none;margin:0;padding:0}}
 .inc li{{display:flex;align-items:center;gap:12px;padding:12px 4px;border-top:1px solid var(--border);font-size:13.5px}} .inc li:first-child{{border-top:none}}
 .inc-sev{{width:8px;height:8px;border-radius:50%;flex:none;background:var(--fail)}} .inc-sev.warn{{background:var(--warn)}}
 .inc-ds{{font-weight:600;min-width:150px}} .inc-ck{{font-family:var(--mono);font-size:12.5px;color:var(--text-2)}} .inc-col{{color:var(--teal);margin-left:6px}}
 .inc-msg{{margin-left:auto;color:var(--muted);font-size:12.5px;text-align:right;max-width:40%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
 .inc-age{{font-family:var(--mono);font-size:11.5px;color:var(--muted);min-width:64px;text-align:right}}
 .allclear{{color:var(--good);font-size:14px}}
 .empty{{text-align:center;padding:70px;color:var(--text-2)}} .empty h2{{color:var(--text)}}
 .empty pre{{display:inline-block;text-align:left;background:var(--surface);border:1px solid var(--border);padding:14px 18px;border-radius:12px;font-family:var(--mono);font-size:13px}}
 footer{{margin-top:34px;color:var(--muted);font-size:12.5px}}
 #tip{{position:fixed;pointer-events:none;opacity:0;transform:translate(-50%,-150%);background:var(--text);color:#fff;border-radius:8px;padding:5px 9px;font-family:var(--mono);font-size:12px;transition:opacity .1s;z-index:20;white-space:nowrap}}
 @media(max-width:860px){{.app{{grid-template-columns:1fr}}.side{{display:none}}.kpis{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body>
<div class="app">
 <aside class="side">
   <div class="brand"><svg viewBox="0 0 52 52" width="24" height="24" fill="none"><clipPath id="mk"><rect x="6" y="14" width="24" height="24" rx="6.5"/></clipPath>
     <g clip-path="url(#mk)"><rect x="22" y="14" width="24" height="24" rx="6.5" fill="#0F766E"/></g>
     <rect x="6" y="14" width="24" height="24" rx="6.5" fill="none" stroke="#141A21" stroke-width="2.6"/>
     <rect x="22" y="14" width="24" height="24" rx="6.5" fill="none" stroke="#141A21" stroke-width="2.6"/></svg><span>true<span class="s">set</span></span></div>
   <nav class="nav">
     <a class="on" href="#top">{ov}Overview</a><a href="#flow">{fl}Data flow</a>
     <a href="#dims">{dm}Dimensions</a><a href="#datasets">{ds}Datasets</a><a href="#incidents">{inc}Incidents</a>
   </nav>
   <div class="conn"><span class="d"></span>{source}</div>
 </aside>
 <main id="top">
   <div class="topbar"><h1>Data Trust</h1><span class="sub">Health of every monitored dataset</span>
     <div class="tb-right" style="margin-left:auto">
       <span class="upd"><b>Updated</b> {generated}</span>
       <div class="connect">
         <button class="connect-btn" id="connectBtn" type="button" aria-expanded="false">
           <svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Connect warehouse</button>
         <div class="connect-pop" id="connectPop">
           <div class="cp-title">Runs on any warehouse</div>
           <div class="cp-sub">Reading <b>{source}</b> &mdash; a local seed. Point a run (<code>--url</code>) or a shared store (<code>--store</code>) at your stack:</div>
           <ul class="cp-list">
             <li data-copy="snowflake://user:pwd@account/db"><span class="wh" style="background:#29B5E8"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><line x1="12" y1="3" x2="12" y2="21"/><line x1="4.2" y1="7.5" x2="19.8" y2="16.5"/><line x1="19.8" y1="7.5" x2="4.2" y2="16.5"/></svg></span><span class="wh-nm">Snowflake</span><code class="wh-url">snowflake://</code></li>
             <li data-copy="bigquery://project/dataset"><span class="wh" style="background:#4285F4">BQ</span><span class="wh-nm">BigQuery</span><code class="wh-url">bigquery://</code></li>
             <li data-copy="databricks://token:***@host/http_path"><span class="wh" style="background:#FF3621">Db</span><span class="wh-nm">Databricks</span><code class="wh-url">databricks://</code></li>
             <li data-copy="redshift+psycopg2://user:pwd@host:5439/db"><span class="wh" style="background:#8C4FFF">Rs</span><span class="wh-nm">Redshift</span><code class="wh-url">redshift://</code></li>
             <li data-copy="postgresql+psycopg://user:pwd@host:5432/db"><span class="wh" style="background:#336791">Pg</span><span class="wh-nm">Postgres</span><code class="wh-url">postgresql://</code></li>
             <li data-copy="duckdb:///warehouse.db"><span class="wh" style="background:#FCC419;color:#1A1A1A">DD</span><span class="wh-nm">DuckDB</span><code class="wh-url">duckdb:///</code></li>
           </ul>
           <div class="cp-foot">Same checks, pushed down as SQL &mdash; data never leaves the warehouse.</div>
         </div>
       </div>
     </div></div>
   <section class="panel hero">
     <div class="hero-top"><div><div class="hero-lbl">Data Trust Score</div>
       <div class="hero-score"><span class="n">{score}%</span>{delta}</div></div>
       <div class="hero-range">{range}</div></div>{trustchart}
   </section>
   <div class="kpis">{kpis}</div>
   <div class="two">
     <div class="panel pad"><div class="ch-title">Checks over time</div>
       <div class="ch-sub">Passing vs failing, per day</div>{checkschart}</div>
     <div class="panel pad"><div class="ch-title">Throughput &amp; rerouting</div>
       <div class="ch-sub">Rows checked, with rerouted rows highlighted</div>{volchart}</div>
   </div>
   <div class="sec" id="flow"><h2>Data flow · shift-left protection</h2><span class="line"></span></div>
   <div class="panel pad">{flow}</div>
   <div class="sec" id="dims"><h2>Quality by dimension</h2><span class="line"></span></div>
   <div class="dims">{dims}</div>
   <div class="sec" id="datasets"><h2>Monitored datasets</h2><span class="line"></span></div>
   <div class="panel pad"><table><thead><tr><th>Dataset</th><th>Status</th><th class="r">Trust</th>
     <th>Freshness</th><th class="r">Rows</th><th class="r">Rerouted</th><th class="r">Checks</th><th>Trend</th></tr></thead>
     <tbody>{rows}</tbody></table></div>
   <div class="sec" id="incidents"><h2>Open incidents</h2><span class="line"></span></div>
   <div class="panel pad">{incidents}</div>
   <footer>trueset · open-source data quality &amp; reconciliation · the local seed of the TrueSet hub —
     <a href="https://github.com/trueset-dev/trueset">github.com/trueset-dev/trueset</a></footer>
 </main>
</div>
<div id="tip"></div>
<script>
 const links=[...document.querySelectorAll('.nav a')];
 links.forEach(a=>a.addEventListener('click',e=>{{const t=document.querySelector(a.getAttribute('href'));
   if(t){{e.preventDefault();t.scrollIntoView({{behavior:'smooth',block:'start'}});links.forEach(l=>l.classList.remove('on'));a.classList.add('on');}}}}));
 const io=new IntersectionObserver(es=>es.forEach(en=>{{if(en.isIntersecting){{const id='#'+en.target.id;
   links.forEach(l=>l.classList.toggle('on',l.getAttribute('href')===id));}}}}),{{rootMargin:'-15% 0px -75% 0px'}});
 document.querySelectorAll('main [id]').forEach(s=>io.observe(s));
 const tip=document.getElementById('tip');
 document.querySelectorAll('.pt').forEach(p=>{{
   p.addEventListener('mouseenter',()=>{{const r=p.getBoundingClientRect();tip.textContent=p.dataset.v;
     tip.style.left=(r.left+r.width/2)+'px';tip.style.top=r.top+'px';tip.style.opacity=1;}});
   p.addEventListener('mouseleave',()=>tip.style.opacity=0);}});
 const cb=document.getElementById('connectBtn'),cp=document.getElementById('connectPop');
 if(cb){{
   cb.addEventListener('click',e=>{{e.stopPropagation();const o=cp.classList.toggle('open');cb.setAttribute('aria-expanded',o);}});
   document.addEventListener('click',e=>{{if(!cp.contains(e.target)&&!cb.contains(e.target)){{cp.classList.remove('open');cb.setAttribute('aria-expanded','false');}}}});
   cp.querySelectorAll('li').forEach(li=>li.addEventListener('click',()=>{{
     const u=li.getAttribute('data-copy');if(navigator.clipboard)navigator.clipboard.writeText(u);
     const el=li.querySelector('.wh-url'),t=el.textContent;el.textContent='✓ copied';
     setTimeout(()=>{{el.textContent=t;}},1200);}}));
 }}
</script>
</body></html>"""
