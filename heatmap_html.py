import csv

INPUT_FILE = "heatmap.csv"
OUTPUT_FILE = "heatmap.html"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def load_data():
    grid = {}
    for day in DAYS:
        grid[day] = {}
    with open(INPUT_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            grid[row["day"]][int(row["hour"])] = {
                "win_rate": float(row["win_rate"]),
                "total": int(row["total"]),
            }
    return grid

def color_for(win_rate):
    # Red (low) -> Yellow (mid) -> Green (high)
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

def build_html(grid):
    cells = ""
    for day in DAYS:
        cells += f'<tr><td class="day-label">{day}</td>'
        for hour in range(24):
            cell = grid[day].get(hour)
            if cell:
                wr = cell["win_rate"]
                n = cell["total"]
                color = color_for(wr)
                cells += f'<td style="background:{color}" title="{day} {hour:02d}:00 - {wr}% (n={n})">{wr:.0f}</td>'
            else:
                cells += '<td style="background:#333">-</td>'
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
<h2>Win Rate Heatmap by Day &amp; Hour</h2>
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
<p style="font-size:11px; color:#888;">Tap a cell to see exact win rate and sample size.</p>
</body>
</html>"""

    with open(OUTPUT_FILE, "w") as f:
        f.write(html)
    print(f"Saved to {OUTPUT_FILE}")

def main():
    grid = load_data()
    build_html(grid)

if __name__ == "__main__":
    main()
