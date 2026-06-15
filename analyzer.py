import json
from collections import defaultdict
from datetime import datetime

INPUT_FILE = "signals.json"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def load_signals():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def analyze(signals):
    by_day = defaultdict(lambda: {"win": 0, "loss": 0})
    by_hour = defaultdict(lambda: {"win": 0, "loss": 0})
    heatmap = defaultdict(lambda: defaultdict(lambda: {"win": 0, "loss": 0}))

    for sig in signals:
        result = sig.get("result")
        if result not in ("WIN", "LOSS"):
            continue

        dt = datetime.fromisoformat(sig["date"])
        day = DAYS[dt.weekday()]
        hour = dt.hour
        key = "win" if result == "WIN" else "loss"

        by_day[day][key] += 1
        by_hour[hour][key] += 1
        heatmap[day][hour][key] += 1

    return by_day, by_hour, heatmap

def win_rate(stats):
    total = stats["win"] + stats["loss"]
    return (stats["win"] / total * 100) if total else 0.0

def print_report(by_day, by_hour, heatmap):
    print("\n=== Win Rate by Day of Week ===")
    for day in DAYS:
        stats = by_day.get(day, {"win": 0, "loss": 0})
        total = stats["win"] + stats["loss"]
        if total == 0:
            continue
        print(f"{day}: {win_rate(stats):.1f}% ({stats['win']}W / {stats['loss']}L, {total} total)")

    print("\n=== Win Rate by Hour ===")
    for hour in sorted(by_hour.keys()):
        stats = by_hour[hour]
        total = stats["win"] + stats["loss"]
        if total == 0:
            continue
        print(f"{hour:02d}:00 -> {win_rate(stats):.1f}% ({stats['win']}W / {stats['loss']}L, {total} total)")

    print("\n=== Day x Hour Heatmap (Win Rate %) ===")
    header = "     " + "".join(f"{h:>6d}" for h in range(24))
    print(header)
    for day in DAYS:
        row = f"{day:<4} "
        for hour in range(24):
            stats = heatmap.get(day, {}).get(hour, {"win": 0, "loss": 0})
            total = stats["win"] + stats["loss"]
            row += "     -" if total == 0 else f"{win_rate(stats):6.0f}"
        print(row)

def main():
    signals = load_signals()
    print(f"Loaded {len(signals)} signals")
    by_day, by_hour, heatmap = analyze(signals)
    print_report(by_day, by_hour, heatmap)

if __name__ == "__main__":
    main()
