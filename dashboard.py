"""
Generate an offline HTML dashboard from heatmap_gmt4.csv.

Usage:
    python dashboard.py                    # writes dashboard.html
    python dashboard.py --output my.html   # custom filename
"""

import csv
import argparse
from datetime import datetime
from collections import defaultdict

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["hour"] = int(r["hour"])
            r["win_rate"] = float(r["win_rate"])
            r["ci_low"] = float(r["ci_low"])
            r["ci_high"] = float(r["ci_high"])
            r["wins"] = int(r["wins"])
            r["losses"] = int(r["losses"])
            r["total"] = int(r["total"])
            rows.append(r)
    return rows

def wr_color(wr):
    if wr >= 97: return "#1b5e20"
    if wr >= 94: return "#2e7d32"
    if wr >= 90: return "#66bb6a"
    if wr >= 86: return "#fdd835"
    if wr >= 82: return "#fb8c00"
    return "#d32f2f"

def wr_text(wr):
    if wr >= 86: return "#fff"
    return "#eee"

def analyze_minutes(signals_path="signals.json"):
    """Pair signals with results and compute win rate per 5-min block."""
    import json
    from collections import defaultdict
    try:
        with open(signals_path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None

    results = defaultdict(lambda: {"win": 0, "loss": 0})
    pending = None
    paired = 0

    for msg in reversed(data):
        text = msg.get("text", "")
        result = msg.get("result")
        if result is None and "⌚️" in text:
            for line in text.split("\n"):
                if "⌚️" in line:
                    ts = line.split("⌚️")[-1].strip()
                    break
            else:
                continue
            parts = ts.split(":")
            hh, mm = int(parts[0]), int(parts[1].split()[0] if " " in parts[1] else parts[1])
            gmt4_h = (hh + 9) % 24
            pending = {"hour": gmt4_h, "block": mm // 5}
        elif result in ("WIN", "LOSS") and pending is not None:
            key = "win" if result == "WIN" else "loss"
            results[(pending["hour"], pending["block"])][key] += 1
            paired += 1
            pending = None

    return results if paired > 100 else None

def build_minutes_html(min_data):
    if not min_data:
        return "<p style='color:#888'>No signals data available for minute analysis.</p>"

    rows_html = ""
    avoid_set = set()
    best_set = set()

    for hour in range(24):
        slots = [(b, s) for (h, b), s in min_data.items()
                 if h == hour and s["win"] + s["loss"] >= 10]
        if not slots:
            rows_html += f"<tr><td>{hour:02d}:00</td><td colspan=5 style='color:#555'>insufficient data</td></tr>"
            continue
        slots.sort(key=lambda x: x[1]["win"] / (x[1]["win"] + x[1]["loss"]))
        worst = slots[0]
        best = slots[-1]
        w_wr = worst[1]["win"] / (worst[1]["win"] + worst[1]["loss"]) * 100
        b_wr = best[1]["win"] / (best[1]["win"] + best[1]["loss"]) * 100
        w_min = f"{worst[0]*5:02d}-{worst[0]*5+4:02d}"
        b_min = f"{best[0]*5:02d}-{best[0]*5+4:02d}"
        wc = wr_color(w_wr)
        bc = wr_color(b_wr)
        avoid_set.add(worst[0])
        best_set.add(best[0])
        rows_html += f"""<tr>
      <td>{hour:02d}:00</td>
      <td><span class="wr" style="color:{bc}">{b_min}</span></td>
      <td><span class="wr" style="color:{bc}">{b_wr:.0f}%</span></td>
      <td class="ci">n={best[1]['win']+best[1]['loss']}</td>
      <td><span class="wr" style="color:{wc}">{w_min}</span></td>
      <td><span class="wr" style="color:{wc}">{w_wr:.0f}%</span></td>
      <td class="ci">n={worst[1]['win']+worst[1]['loss']}</td>
    </tr>"""

    # Count most common avoid/best blocks
    from collections import Counter
    avoid_counts = Counter(avoid_set)
    best_counts = Counter(best_set)
    top_avoid = [f":{b*5:02d}-{b*5+4:02d}" for b, _ in avoid_counts.most_common(3)]
    top_best = [f":{b*5:02d}-{b*5+4:02d}" for b, _ in best_counts.most_common(3)]

    summary = f"""
    <div class="today-stats">
      Most commonly best: <b>{", ".join(top_best)}</b> &middot;
      Most commonly avoid: <b>{", ".join(top_avoid)}</b>
    </div>"""

    html = f"""<table class="table">
    <tr><th>Hour</th><th colspan="2">Best 5-min</th><th></th><th colspan="2">Worst 5-min</th><th></th></tr>
    {rows_html}
    </table>
    {summary}"""
    return html


def build_html(rows):
    now = datetime.now()
    today_name = DAYS[now.weekday()]

    min_s = 30
    slots = [r for r in rows if r["total"] >= min_s]
    slots.sort(key=lambda r: (-r["win_rate"], -r["ci_low"], -r["total"]))

    top20 = slots[:20]
    worst10 = list(reversed(slots[-10:]))

    today_slots = sorted(
        [r for r in slots if r["day"] == today_name],
        key=lambda r: (-r["win_rate"], -r["total"])
    )
    t3 = today_slots[:3] if today_slots else []

    strategies = []
    for thr in [97, 95, 94, 93, 92, 90]:
        ss = [r for r in slots if r["win_rate"] >= thr]
        if not ss:
            continue
        avg = sum(s["total"] for s in ss) / 7
        tl = sum(s["losses"] for s in ss)
        tn = sum(s["total"] for s in ss)
        strategies.append((thr, len(ss), int(avg), tl, tn, sum(s["wins"] for s in ss)))

    top_rows_html = ""
    for i, s in enumerate(top20, 1):
        c = wr_color(s["win_rate"])
        bar = "█" * int(s["win_rate"] / 3.5)
        top_rows_html += f"""<tr>
      <td class="rank">{i}</td>
      <td>{s["day"]}</td>
      <td>{s["hour"]:02d}:00</td>
      <td><span class="wr" style="color:{c}">{s["win_rate"]:.1f}%</span></td>
      <td class="ci">[{s["ci_low"]:.1f}–{s["ci_high"]:.1f}]</td>
      <td>{s["wins"]}W/{s["losses"]}L</td>
      <td>{s["total"]}</td>
      <td><span class="bar" style="background:{c};width:{s['win_rate']*0.7:.0f}px"></span></td>
    </tr>"""

    worst_rows_html = ""
    for s in worst10:
        c = wr_color(s["win_rate"])
        worst_rows_html += f"""<tr>
      <td>{s["day"]}</td>
      <td>{s["hour"]:02d}:00</td>
      <td><span class="wr" style="color:{c}">{s["win_rate"]:.1f}%</span></td>
      <td class="ci">[{s["ci_low"]:.1f}–{s["ci_high"]:.1f}]</td>
      <td>{s["wins"]}W/{s["losses"]}L</td>
      <td>{s["total"]}</td>
      <td>{s["losses"]/s["total"]*200:.0f}</td>
    </tr>"""

    strat_rows_html = ""
    for thr, n, avg, tl, tn, tw in strategies:
        wr = tw / tn * 100
        les_per_200 = tl / tn * 200
        strat_rows_html += f"""<tr>
      <td><span class="wr" style="color:{wr_color(thr+2)}">≥{thr}%</span></td>
      <td>{n}</td>
      <td>{avg}</td>
      <td>{wr:.1f}%</td>
      <td>{les_per_200:.1f}</td>
    </tr>"""

    today_html = ""
    if today_slots:
        today_html += """<table class="table today-tbl">
<tr><th>Hour</th><th>W%</th><th>95% CI</th><th>W/L</th><th>n</th></tr>"""
        cnt90 = 0
        for s in today_slots:
            if s["win_rate"] >= 90:
                cnt90 += 1
            c = wr_color(s["win_rate"])
            today_html += f"""<tr{" class='highlight'" if s in t3 else ""}>
      <td>{s["hour"]:02d}:00</td>
      <td><span class="wr" style="color:{c}">{s["win_rate"]:.1f}%</span></td>
      <td class="ci">[{s["ci_low"]:.1f}–{s["ci_high"]:.1f}]</td>
      <td>{s["wins"]}W/{s["losses"]}L</td>
      <td>{s["total"]}</td>
    </tr>"""
        today_html += "</table>"

        tw = sum(s["wins"] for s in today_slots)
        tl_ = sum(s["losses"] for s in today_slots)
        tn_ = tw + tl_
        today_html += f"""
    <div class="today-stats">
      Volume: <b>{tn_}</b> signals &middot; Avg WR: <b>{tw/tn_*100:.1f}%</b> &middot; ≥90% slots: <b>{cnt90}</b>
    </div>"""
    if t3:
        today_html += '<div class="best3">'
        for s in t3:
            today_html += f'<div class="pill" style="background:{wr_color(s["win_rate"])}">{s["hour"]:02d}:00 {s["win_rate"]:.0f}%</div>'
        today_html += "</div>"

    min_data = analyze_minutes()
    minutes_html = build_minutes_html(min_data)

    heatmap_html = "<table class='heatmap'><tr><th></th>"
    for h in range(24):
        heatmap_html += f"<th>{h:02d}</th>"
    heatmap_html += "</tr>"
    for day in DAYS:
        heatmap_html += f"<tr><td class='day-label'>{day}</td>"
        for h in range(24):
            cell = None
            for r in rows:
                if r["day"] == day and r["hour"] == h:
                    cell = r
                    break
            if cell and cell["total"] >= min_s:
                c = wr_color(cell["win_rate"])
                heatmap_html += f'<td class="hcell" style="background:{c}" title="{day} {h:02d}:00 — {cell["win_rate"]:.1f}% (n={cell["total"]}, {cell["wins"]}W/{cell["losses"]}L)">{cell["win_rate"]:.0f}</td>'
            elif cell:
                heatmap_html += f'<td class="hcell low-sample" title="{day} {h:02d}:00 — {cell["win_rate"]:.1f}% (n={cell["total"]})">{cell["win_rate"]:.0f}</td>'
            else:
                heatmap_html += '<td class="hcell empty">-</td>'
        heatmap_html += "</tr>"
    heatmap_html += "</table>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Signals Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #121212; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; padding: 16px; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .sub {{ color: #888; font-size: 12px; margin-bottom: 20px; }}
  h2 {{ font-size: 16px; margin: 20px 0 10px; color: #bbb; border-bottom: 1px solid #333; padding-bottom: 6px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 700px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{ background: #1e1e1e; border-radius: 10px; padding: 14px; }}
  .table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  .table th {{ text-align: left; padding: 6px 4px; border-bottom: 1px solid #333; color: #999; font-weight: 600; }}
  .table td {{ padding: 5px 4px; border-bottom: 1px solid #282828; }}
  .table tr:hover td {{ background: #252525; }}
  .rank {{ color: #666; width: 28px; }}
  .wr {{ font-weight: 700; font-size: 13px; }}
  .ci {{ color: #777; font-size: 11px; }}
  .bar {{ display: inline-block; height: 10px; border-radius: 4px; vertical-align: middle; }}
  .today-tbl tr.highlight {{ background: #1a2e1a !important; }}
  .today-tbl tr.highlight td {{ border-bottom-color: #2a4a2a; }}
  .today-stats {{ margin-top: 8px; padding: 8px; background: #181818; border-radius: 6px; font-size: 12px; color: #aaa; }}
  .best3 {{ display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }}
  .pill {{ padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 700; color: #fff; }}
  .avoid-card td {{ color: #e57373; }}
  .commands {{ font-size: 12px; }}
  .commands code {{ display: inline-block; background: #282828; padding: 2px 8px; border-radius: 4px; color: #81c784; font-family: 'SFMono', monospace; margin: 2px 0; }}
  .commands td {{ padding: 4px 8px; vertical-align: top; }}
  .cmd-desc {{ color: #999; }}
  .heatmap {{ font-size: 11px; border-collapse: collapse; width: 100%; }}
  .heatmap th {{ background: #1a1a1a; padding: 4px 2px; text-align: center; font-weight: 600; color: #999; font-size: 10px; }}
  .heatmap .day-label {{ font-weight: 700; padding: 4px 6px; text-align: left; color: #bbb; background: #1a1a1a; }}
  .hcell {{ text-align: center; padding: 4px 2px; cursor: default; font-weight: 700; font-size: 11px; color: #fff; width: 28px; }}
  .hcell.low-sample {{ opacity: 0.5; }}
  .hcell.empty {{ background: #1a1a1a !important; color: #333; }}
  .legend {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 10px 0 4px; font-size: 11px; align-items: center; }}
  .swatch {{ width: 14px; height: 14px; border-radius: 3px; display: inline-block; vertical-align: middle; margin-right: 3px; }}
  .footer {{ margin-top: 24px; padding: 12px 0; text-align: center; color: #555; font-size: 11px; border-top: 1px solid #222; }}
  .cmd-bar {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }}
  .cmd-btn {{ background: #2a2a2a; border: 1px solid #444; color: #ccc; padding: 6px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; font-family: 'SFMono', monospace; }}
  .cmd-btn:hover {{ background: #3a3a3a; border-color: #666; }}
  .cmd-btn:active {{ background: #4a4a4a; }}
  .cmd-btn.run {{ background: #1b5e20; border-color: #2e7d32; color: #a5d6a7; }}
  .cmd-output {{ background: #0d0d0d; border: 1px solid #333; border-radius: 6px; padding: 10px; font-family: 'SFMono', monospace; font-size: 11px; white-space: pre-wrap; overflow-x: auto; max-height: 400px; overflow-y: auto; color: #a0d0a0; display: none; line-height: 1.5; }}
  .cmd-output.loading {{ opacity: 0.5; }}
  .cmd-output .err {{ color: #e57373; }}
  .inp-group {{ display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }}
  .inp-group input {{ background: #1a1a1a; border: 1px solid #444; color: #ccc; padding: 4px 8px; border-radius: 4px; font-size: 12px; width: 80px; font-family: 'SFMono', monospace; }}
  .inp-group label {{ color: #888; font-size: 11px; }}
</style>
<script>
async function runCmd(cmd, args) {{
  const out = document.getElementById('cmd-output');
  const url = '/api/run?cmd=' + encodeURIComponent(cmd) + (args ? '&args=' + encodeURIComponent(args) : '');
  out.style.display = 'block';
  out.textContent = 'Running...';
  out.className = 'cmd-output loading';
  try {{
    const r = await fetch(url);
    const text = await r.text();
    out.textContent = text;
    out.className = 'cmd-output';
  }} catch(e) {{
    out.textContent = 'Error: ' + e.message;
    out.className = 'cmd-output err';
  }}
}}
function runTop() {{
  const n = document.getElementById('top-n').value || '20';
  runCmd('top20', '--top ' + n);
}}
function runStrategy() {{
  const n = document.getElementById('strat-n').value || '12';
  runCmd('strategy', '--target ' + n);
}}
</script>
</head>
<body>
<div class="container">

<h1>📊 Signals Dashboard</h1>
<div class="sub">{now.strftime("%a %b %d %Y %H:%M")} GMT+4 (Tbilisi) &middot; {len(slots)} qualified slots (min {min_s} samples)</div>

<div class="grid">
  <div class="card">
    <h2>📅 Today — {today_name}</h2>
    {today_html}
  </div>
  <div class="card">
    <h2>⚡ Run Commands</h2>
    <div class="cmd-bar">
      <button class="cmd-btn run" onclick="runCmd('today')">--today</button>
      <div class="inp-group">
        <label>--top</label>
        <input type="number" id="top-n" value="20" min="1" max="168">
        <button class="cmd-btn" onclick="runTop()">Go</button>
      </div>
      <button class="cmd-btn" onclick="runCmd('by-ci')">--by-ci</button>
      <div class="inp-group">
        <label>--strategy</label>
        <input type="number" id="strat-n" value="12" min="1" max="50">
        <button class="cmd-btn" onclick="runStrategy()">Go</button>
      </div>
      <button class="cmd-btn" onclick="runCmd('avoid')">--avoid</button>
      <button class="cmd-btn" onclick="runCmd('safest')">--safest</button>
    </div>
    <pre id="cmd-output" class="cmd-output"></pre>
  </div>
</div>

<div class="card" style="margin-top:16px">
  <h2>🏆 Top 20 Slots</h2>
  <table class="table">
    <tr><th class="rank">#</th><th>Day</th><th>Hour</th><th>W%</th><th>95% CI</th><th>W/L</th><th>n</th><th></th></tr>
    {top_rows_html}
  </table>
</div>

<div class="grid" style="margin-top:16px">
  <div class="card">
    <h2>⚠️ Worst 10 Slots to Avoid</h2>
    <table class="table avoid-card">
      <tr><th>Day</th><th>Hour</th><th>W%</th><th>95% CI</th><th>W/L</th><th>n</th><th>L/200</th></tr>
      {worst_rows_html}
    </table>
  </div>
  <div class="card">
    <h2>📈 Strategy Quick Reference</h2>
    <table class="table">
      <tr><th>Threshold</th><th>Slots</th><th>Signals/day</th><th>Avg W%</th><th>L/200</th></tr>
      {strat_rows_html}
    </table>
    <div style="margin-top:10px;font-size:12px;color:#888">
      <b>Run:</b> <code>python best_signals.py --strategy --target N</code>
    </div>
  </div>
</div>

<div class="card" style="margin-top:16px">
  <h2>⏱️ Minute Analysis — Best &amp; Worst 5-min Block per Hour</h2>
  <div style="font-size:11px;color:#888;margin-bottom:8px">
    Signal times converted from UTC-3 → GMT+4. Paired {min_data and sum(s['win']+s['loss'] for s in min_data.values()) or 0} signals with their results.
  </div>
  {minutes_html}
</div>

<div class="card" style="margin-top:16px">
  <h2>🗺️ Heatmap — Win Rate % by Day &amp; Hour (GMT+4)</h2>
  <div class="legend">
    <span><span class="swatch" style="background:#1b5e20"></span>97%+</span>
    <span><span class="swatch" style="background:#2e7d32"></span>94-97%</span>
    <span><span class="swatch" style="background:#66bb6a"></span>90-94%</span>
    <span><span class="swatch" style="background:#fdd835"></span>86-90%</span>
    <span><span class="swatch" style="background:#fb8c00"></span>82-86%</span>
    <span><span class="swatch" style="background:#d32f2f"></span>&lt;82%</span>
    <span style="color:#555">(dimmed = low sample)</span>
  </div>
  {heatmap_html}
</div>

<div class="footer">
  Interactive server · <code>python3 server.py</code> &middot; <code>python3 dashboard.py</code> to refresh HTML
</div>

</div>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate offline dashboard")
    parser.add_argument("--csv", default="heatmap_gmt4.csv")
    parser.add_argument("--output", default="dashboard.html")
    args = parser.parse_args()

    rows = load(args.csv)
    html = build_html(rows)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved to {args.output} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
