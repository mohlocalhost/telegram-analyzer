import json
import csv
import math
from collections import defaultdict
from datetime import datetime, timedelta

INPUT_FILE = "signals.json"
OUTPUT_CSV = "heatmap_gmt4.csv"
OUTPUT_HTML = "heatmap_gmt4.html"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MIN_SAMPLE = 30
TZ_OFFSET_HOURS = 4  # Tbilisi GMT+4, no DST

def load_signals():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def analyze(signals):
    heatmap = defaultdict(lambda: defaultdict(lambda: {"win": 0, "loss": 0}))
    for sig in signals:
        result = sig.get("result")
        if result not in ("WIN", "LOSS"):
            continue
        dt = datetime.fromisoformat(sig["date"]) + timedelta(hours=TZ_OFFSET_HOURS)
        day = DAYS[dt.weekday()]
        hour = dt.hour
        key = "win" if result == "WIN" else "loss"
        heatmap[day][hour][key] += 1
    return heatmap

def win_rate(stats):
    total = stats["win"] + stats["loss"]
    return (stats["win"] / total * 100) if total else 0.0

def wilson_interval(wins, total, z=1.96):
    if total == 0:
        return (0, 0)
    p = wins / total
    denom = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    lower = (center - margin) / denom
    upper = (center + margin) / denom
    return (lower * 100, upper * 100)

def print_heatmap_with_confidence(heatmap):
    print(f"\n=== Win Rate % [95% CI], sample size (GMT+{TZ_OFFSET_HOURS} / Tbilisi) ===")
    for day in DAYS:
        print(f"\n--- {day} ---")
        for hour in range(24):
            stats = heatmap.get(day, {}).get(hour, {"win": 0, "loss": 0})
            total = stats["win"] + stats["loss"]
            if total == 0:
                continue
            wr = win_rate(stats)
            lo, hi = wilson_interval(stats["win"], total)
            flag = "  <-- LOW SAMPLE" if total < MIN_SAMPLE else ""
            print(f"  {hour:02d}:00  {wr:5.1f}%  [{lo:5.1f}-{hi:5.1f}%]  n={total}{flag}")

def export_csv(heatmap):
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["day", "hour", "win_rate", "ci_low", "ci_high", "wins", "losses", "total"])
        for day in DAYS:
            for hour in range(24):
                stats = heatmap.get(day, {}).get(hour, {"win": 0, "loss": 0})
                total = stats["win"] + stats["loss"]
                if total == 0:
                    continue
                wr = win_rate(stats)
                lo, hi = wilson_interval(stats["win"], total)
                writer.writerow([day, hour, f"{wr:.1f}", f"{lo:.1f}", f"{hi:.1f}", stats["win"], stats["loss"], total])
    print(f"\nExported to {OUTPUT_CSV}")

def color_for(win_rate):
    if win_rate >= 92:
        return "#2e7d32"
    elif win_rate >= 89:
        return "#66bb6a"
    elif win_rate >= 86:
        return "#fdd835"
    elif win_rate >= 82:
        return "#fb8c00"
    else:
        return "#e53935"

def export_html(heatmap):
    cells = ""
    for day in DAYS:
        cells += f'<tr><td class="day-label">{day}</td>'
        for hour in range(24):
            stats = heatmap.get(day, {}).get(hour, {"win": 0, "loss": 0})
            total = stats["win"] + stats["loss"]
            if total == 0:
                cells += '<td style="background:#333">-</td>'
                continue
            wr = win_rate(stats)
            color = color_for(wr)
            cells += f'<td style="background:{color}" title="{day} {hour:02d}:00 (GMT+4) - {wr:.1f}% (n={total})">{wr:.0f}</td>'
        cells += "</tr>\n"

    header = "".join(f"<th>{h:02d}</th>" for h in range(24))

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: sans-serif; background: #1a1a1a; color: #eee; padding: 10px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 11px; }}
  th, td {{ text-align: center; padding: 6px 2px; border: 1px solid #444; }}
  .day-label {{ font-weight: bold; background: #222; }}
  h2 {{ font-size: 16px; }}
  .legend {{ display: flex; gap: 8px; margin: 10px 0; font-size: 11px; flex-wrap: wrap; }}
  .swatch {{ width: 14px; height: 14px; display: inline-block; vertical-align: middle; margin-right: 4px; }}
</style>
</head>
<body>
<h2>Win Rate Heatmap by Day &amp; Hour (GMT+4 / Tbilisi)</h2>
<div class="legend">
  <span><span class="swatch" style="background:#e53935"></span>&lt;82%</span>
  <span><span class="swatch" style="background:#fb8c00"></span>82-86%</span>
  <span><span class="swatch" style="background:#fdd835"></span>86-89%</span>
  <span><span class="swatch" style="background:#66bb6a"></span>89-92%</span>
  <span><span class="swatch" style="background:#2e7d32"></span>92%+</span>
</div>
<table>
<tr><th></th>{header}</tr>
{cells}
</table>
<p style="font-size:11px; color:#888;">Tap a cell to see exact win rate and sample size. Times shown in GMT+4 (Tbilisi).</p>
</body>
</html>"""

    with open(OUTPUT_HTML, "w") as f:
        f.write(html)
    print(f"Saved to {OUTPUT_HTML}")

def main():
    signals = load_signals()
    print(f"Loaded {len(signals)} signals")
    heatmap = analyze(signals)
    print_heatmap_with_confidence(heatmap)
    export_csv(heatmap)
    export_html(heatmap)

if __name__ == "__main__":
    main()
