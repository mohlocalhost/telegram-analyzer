import json
import csv
import math
from collections import defaultdict
from datetime import datetime

INPUT_FILE = "signals.json"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MIN_SAMPLE = 30

def load_signals():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def analyze(signals):
    heatmap = defaultdict(lambda: defaultdict(lambda: {"win": 0, "loss": 0}))
    for sig in signals:
        result = sig.get("result")
        if result not in ("WIN", "LOSS"):
            continue
        dt = datetime.fromisoformat(sig["date"])
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
    print("\n=== Win Rate % [95% CI], sample size ===")
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

def export_csv(heatmap, filename="heatmap.csv"):
    with open(filename, "w", newline="", encoding="utf-8") as f:
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
    print(f"\nExported to {filename}")

def main():
    signals = load_signals()
    print(f"Loaded {len(signals)} signals")
    heatmap = analyze(signals)
    print_heatmap_with_confidence(heatmap)
    export_csv(heatmap)

if __name__ == "__main__":
    main()
