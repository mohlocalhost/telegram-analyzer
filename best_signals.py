"""
Rank the best day/hour slots by win rate with Wilson confidence intervals.

Usage:
    python best_signals.py                          # default: top 20 slots
    python best_signals.py --top 10 --min-samples 50
    python best_signals.py --by-ci                   # rank by CI lower bound
    python best_signals.py --strategy --target 12    # auto daily schedule
    python best_signals.py --today                   # what to trade right now
    python best_signals.py --avoid                   # worst slots to avoid
    python best_signals.py --safest                  # slots with minimal loss risk
"""

import csv
import argparse
from datetime import datetime

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def load_data(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["hour"] = int(r["hour"])
            r["win_rate"] = float(r["win_rate"])
            r["ci_low"] = float(r["ci_low"])
            r["ci_high"] = float(r["ci_high"])
            r["wins"] = int(r["wins"])
            r["losses"] = int(r["losses"])
            r["total"] = int(r["total"])
            rows.append(r)
    return rows

def rank_slots(rows, min_samples, by_ci=False):
    slots = [r for r in rows if r["total"] >= min_samples]
    if by_ci:
        slots.sort(key=lambda r: (-r["ci_low"], -r["win_rate"], -r["total"]))
    else:
        slots.sort(key=lambda r: (-r["win_rate"], -r["ci_low"], -r["total"]))
    return slots

def print_top(slots, top_n):
    print(f"{'Rank':<5} {'Day':<4} {'Hour':<6} {'W%':<7} {'95% CI':<14} {'W/L':<10} {'n':<6}")
    print("-" * 55)
    for i, s in enumerate(slots[:top_n], 1):
        ci = f"[{s['ci_low']:.1f}-{s['ci_high']:.1f}]"
        wl = f"{s['wins']}W/{s['losses']}L"
        print(f"{i:<5} {s['day']:<4} {s['hour']:>2d}:00  {s['win_rate']:>5.1f}%  {ci:<13} {wl:<10} {s['total']:<6}")

def best_by_day(rows, min_samples):
    print("\n=== Best Hour per Day ===")
    print(f"{'Day':<4} {'Hour':<6} {'W%':<7} {'95% CI':<14} {'n':<6}")
    print("-" * 40)
    for day in DAYS:
        day_slots = [r for r in rows if r["day"] == day and r["total"] >= min_samples]
        if not day_slots:
            continue
        best = max(day_slots, key=lambda r: (r["win_rate"], r["ci_low"]))
        ci = f"[{best['ci_low']:.1f}-{best['ci_high']:.1f}]"
        print(f"{day:<4} {best['hour']:>2d}:00  {best['win_rate']:>5.1f}%  {ci:<13} {best['total']:<6}")

def best_by_hour(rows, min_samples):
    print("\n=== Best Day per Hour ===")
    print(f"{'Hour':<6} {'Day':<4} {'W%':<7} {'95% CI':<14} {'n':<6}")
    print("-" * 40)
    for hour in range(24):
        hour_slots = [r for r in rows if r["hour"] == hour and r["total"] >= min_samples]
        if not hour_slots:
            continue
        best = max(hour_slots, key=lambda r: (r["win_rate"], r["ci_low"]))
        ci = f"[{best['ci_low']:.1f}-{best['ci_high']:.1f}]"
        print(f"{best['hour']:>2d}:00  {best['day']:<4} {best['win_rate']:>5.1f}%  {ci:<13} {best['total']:<6}")

def overall_by_day(rows, min_samples):
    print("\n=== Aggregate by Day ===")
    print(f"{'Day':<4} {'W%':<7} {'W/L':<12} {'n':<6}")
    print("-" * 32)
    for day in DAYS:
        day_slots = [r for r in rows if r["day"] == day and r["total"] >= min_samples]
        if not day_slots:
            continue
        total_w = sum(r["wins"] for r in day_slots)
        total_l = sum(r["losses"] for r in day_slots)
        total_n = total_w + total_l
        wr = total_w / total_n * 100 if total_n else 0
        print(f"{day:<4} {wr:>5.1f}%  {total_w}W/{total_l}L{'':>6} {total_n:<6}")

def overall_by_hour(rows, min_samples):
    print("\n=== Aggregate by Hour (all days) ===")
    print(f"{'Hour':<6} {'W%':<7} {'W/L':<12} {'n':<6}")
    print("-" * 32)
    for hour in range(24):
        hour_slots = [r for r in rows if r["hour"] == hour and r["total"] >= min_samples]
        if not hour_slots:
            continue
        total_w = sum(r["wins"] for r in hour_slots)
        total_l = sum(r["losses"] for r in hour_slots)
        total_n = total_w + total_l
        wr = total_w / total_n * 100 if total_n else 0
        print(f"{hour:>2d}:00  {wr:>5.1f}%  {total_w}W/{total_l}L{'':>6} {total_n:<6}")

# ─── Strategy Mode ────────────────────────────────────────────────────────

def build_strategy(rows, min_samples, target_per_day):
    print(f"  Target: ≥{target_per_day} trades/day, min {min_samples} samples per slot\n")

    thresholds = list(range(99, 79, -1))
    best_plan = None

    for thr in thresholds:
        slots = [r for r in rows if r["win_rate"] >= thr and r["total"] >= min_samples]
        if not slots:
            continue
        per_day = {d: 0 for d in DAYS}
        for s in slots:
            per_day[s["day"]] += s["total"]
        avg = sum(per_day.values()) / 7
        if avg >= target_per_day:
            best_plan = (thr, slots, per_day, avg)
            break

    if best_plan is None:
        print("  Cannot find a threshold that delivers enough daily volume.")
        print("  Try reducing --target or --min-samples.")
        return

    thr, slots, per_day, avg = best_plan
    avg_wr = sum(s["win_rate"] for s in slots) / len(slots)
    total_losses = sum(s["losses"] for s in slots)
    total_signals = sum(s["total"] for s in slots)
    loss_rate = total_losses / total_signals * 100

    print(f"  ◇ Threshold: ≥{thr}% win rate ({len(slots)} slots)")
    print(f"  ◇ Average WR: {avg_wr:.1f}%")
    print(f"  ◇ Signals/day: {avg:.0f} (total {total_signals}/week)")
    print(f"  ◇ Expected losses: {loss_rate:.1f}% ({total_losses}L in {total_signals} trades)")
    print(f"  ◇ Losses per 200 trades: ~{total_losses / total_signals * 200:.1f}")

    print(f"\n  {'── Daily Schedule':─<50}")
    for day in DAYS:
        day_slots = sorted(
            [s for s in slots if s["day"] == day],
            key=lambda r: (-r["win_rate"], -r["total"])
        )
        if not day_slots:
            print(f"  {day:<4}  —")
            continue
        parts = ", ".join(f"{s['hour']:>2d}:00 ({s['win_rate']:.0f}%, n={s['total']})" for s in day_slots)
        total_day = sum(s["total"] for s in day_slots)
        day_w = sum(s["wins"] for s in day_slots)
        day_l = sum(s["losses"] for s in day_slots)
        print(f"  {day:<4}  {parts}")
        print(f"       ~{total_day} signals ({day_w}W/{day_l}L)")

    # Golden hours
    title = f"── Golden Hours (≥{thr}% on 3+ days)"
    print(f"\n  {title:─<50}")
    from collections import defaultdict
    hour_days = defaultdict(list)
    for s in slots:
        hour_days[s["hour"]].append((s["day"], s["win_rate"], s["total"]))
    for h in sorted(hour_days):
        entries = hour_days[h]
        if len(entries) >= 3:
            days_str = ", ".join(f"{d}({wr:.0f}%,n={n})" for d, wr, n in entries)
            print(f"  {h:>2d}:00  {len(entries)} days: {days_str}")

    # Risk summary
    print(f"\n  {'── Risk Summary':─<50}")
    per_200 = total_losses / total_signals * 200
    print(f"  Per 200 trades: ~{per_200:.1f} losses")
    print(f"  Per 100 trades: ~{per_200/2:.1f} losses")
    print(f"  Per day ({avg:.0f} trades): ~{avg * loss_rate / 100:.1f} losses")


# ─── Today Mode ──────────────────────────────────────────────────────────

def show_today(rows, min_samples, day_name):
    print(f"  Today: {day_name} (GMT+4 / Tbilisi)\n")

    today_slots = sorted(
        [r for r in rows if r["day"] == day_name and r["total"] >= min_samples],
        key=lambda r: (-r["win_rate"], -r["total"])
    )

    if not today_slots:
        print("  No qualifying slots for today.")
        return

    print(f"  {'Hour':<6} {'W%':<7} {'95% CI':<14} {'W/L':<10} {'n':<6}")
    print(f"  {'─'*45}")
    for s in today_slots:
        ci = f"[{s['ci_low']:.1f}-{s['ci_high']:.1f}]"
        wl = f"{s['wins']}W/{s['losses']}L"
        print(f"  {s['hour']:>2d}:00  {s['win_rate']:>5.1f}%  {ci:<13} {wl:<10} {s['total']:<6}")

    total_w = sum(s["wins"] for s in today_slots)
    total_l = sum(s["losses"] for s in today_slots)
    total_n = total_w + total_l
    avg_wr = total_w / total_n * 100 if total_n else 0

    print(f"\n  Today's volume: {total_n} expected signals")
    print(f"  Average WR:    {avg_wr:.1f}%")
    print(f"  Expected:      ~{total_w} wins, ~{total_l} losses")

    # Best 3 for quick reference
    top3 = today_slots[:3]
    print(f"\n  Best 3 slots:")
    for s in top3:
        print(f"    {s['hour']:>2d}:00 — {s['win_rate']:.1f}% (n={s['total']}, {s['wins']}W/{s['losses']}L)")

    # Highlight golden hours
    golden = [s for s in today_slots if s["win_rate"] >= 90]
    if golden:
        parts = [f"{s['hour']:>2d}:00 ({s['win_rate']:.0f}%)" for s in golden]
        print(f"\n  Slots ≥90%: {', '.join(parts)}")


# ─── Avoid Mode ──────────────────────────────────────────────────────────

def show_avoid(rows, min_samples):
    print(f"  Min {min_samples} samples per slot\n")
    slots = [r for r in rows if r["total"] >= min_samples]
    slots.sort(key=lambda r: (r["win_rate"], r["ci_low"]))

    print(f"  {'── Worst 10 Slots (highest loss rate)':─<55}")
    print(f"  {'Day':<4} {'Hour':<6} {'W%':<7} {'95% CI':<14} {'W/L':<10} {'n':<7} {'Loss/200':<9}")
    print(f"  {'─'*55}")
    for s in slots[:10]:
        ci = f"[{s['ci_low']:.1f}-{s['ci_high']:.1f}]"
        wl = f"{s['wins']}W/{s['losses']}L"
        losses_per_200 = s["losses"] / s["total"] * 200
        print(f"  {s['day']:<4} {s['hour']:>2d}:00  {s['win_rate']:>5.1f}%  {ci:<13} {wl:<10} {s['total']:<7} {losses_per_200:>5.1f}")

    print(f"\n  {'── Worst per Day':─<40}")
    print(f"  {'Day':<4} {'Hour':<6} {'W%':<7} {'n':<6}")
    print(f"  {'─'*25}")
    for day in DAYS:
        day_slots = [r for r in slots if r["day"] == day]
        if not day_slots:
            continue
        worst = min(day_slots, key=lambda r: (r["win_rate"], -r["total"]))
        print(f"  {day:<4} {worst['hour']:>2d}:00  {worst['win_rate']:>5.1f}%  {worst['total']:<6}")

    total_w = sum(s["wins"] for s in slots)
    total_l = sum(s["losses"] for s in slots)
    total_n = total_w + total_l
    print(f"\n  Overall: {total_w}W/{total_l}L ({total_w/total_n*100:.1f}%) across {total_n} signals")

    worst_hours = sorted(
        [(h, sum(s["losses"] for s in slots if s["hour"] == h),
          sum(s["total"] for s in slots if s["hour"] == h))
         for h in range(24)],
        key=lambda x: -x[1]
    )[:5]
    print(f"\n  {'── 5 Riskiest Hours (most losses)':─<40}")
    for h, losses, total in worst_hours:
        wr = (total - losses) / total * 100 if total else 0
        print(f"  {h:>2d}:00 — {losses}L/{total} ({wr:.1f}%)")


# ─── Safest Mode ─────────────────────────────────────────────────────────

def show_safest(rows, min_samples):
    print(f"  Showing only slots with ≤5% expected loss rate\n")
    slots = [r for r in rows if r["total"] >= min_samples]
    safe = [s for s in slots if s["losses"] / s["total"] <= 0.05]
    safe.sort(key=lambda r: (-r["win_rate"], -r["total"]))

    if not safe:
        print("  No slots qualify. Try lowering --min-samples.")
        return

    print(f"  {len(safe)} slots with ≤5% loss rate:")
    print(f"  {'Day':<4} {'Hour':<6} {'W%':<7} {'95% CI':<14} {'W/L':<10} {'n':<7} {'Loss%':<7}")
    print(f"  {'─'*55}")
    for s in safe:
        ci = f"[{s['ci_low']:.1f}-{s['ci_high']:.1f}]"
        wl = f"{s['wins']}W/{s['losses']}L"
        loss_pct = s["losses"] / s["total"] * 100
        print(f"  {s['day']:<4} {s['hour']:>2d}:00  {s['win_rate']:>5.1f}%  {ci:<13} {wl:<10} {s['total']:<7} {loss_pct:>5.1f}%")

    total_w = sum(s["wins"] for s in safe)
    total_l = sum(s["losses"] for s in safe)
    total_n = total_w + total_l
    print(f"\n  Total: {total_n} signals ({total_w}W/{total_l}L, {total_w/total_n*100:.1f}%)")
    print(f"  Per 200 trades: ~{total_l/total_n*200:.1f} expected losses")


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Find best trading signals by win rate")
    parser.add_argument("--min-samples", type=int, default=30, help="Minimum sample threshold (default: 30)")
    parser.add_argument("--top", type=int, default=20, help="Number of top slots to show (default: 20)")
    parser.add_argument("--csv", default="heatmap_gmt4.csv", help="Input CSV file (default: heatmap_gmt4.csv)")
    parser.add_argument("--by-ci", action="store_true", help="Rank by CI lower bound instead of raw win rate")
    parser.add_argument("--strategy", action="store_true", help="Auto generate a daily trading schedule")
    parser.add_argument("--target", type=int, default=12, help="Target trades per day for strategy (default: 12)")
    parser.add_argument("--today", action="store_true", help="Show today's best slots only")
    parser.add_argument("--avoid", action="store_true", help="Show worst slots to avoid")
    parser.add_argument("--safest", action="store_true", help="Show only slots with minimal loss risk")
    args = parser.parse_args()

    rows = load_data(args.csv)
    print(f"Loaded {len(rows)} day/hour slots from {args.csv}\n")

    if args.strategy:
        build_strategy(rows, args.min_samples, args.target)
        return

    if args.today:
        now = datetime.now()
        day_name = DAYS[now.weekday()]
        show_today(rows, args.min_samples, day_name)
        return

    if args.avoid:
        show_avoid(rows, args.min_samples)
        return

    if args.safest:
        show_safest(rows, args.min_samples)
        return

    # Default report mode
    print(f"Filtering: min {args.min_samples} samples per slot")

    sort_mode = "CI lower bound" if args.by_ci else "win rate"
    print(f"Sorting by: {sort_mode}")

    slots = rank_slots(rows, args.min_samples, by_ci=args.by_ci)
    print(f"Qualified slots: {len(slots)}")

    print(f"\n─── Top {args.top} Slots (sorted by {sort_mode}) ───")
    print_top(slots, args.top)

    best_by_day(rows, args.min_samples)
    best_by_hour(rows, args.min_samples)
    overall_by_day(rows, args.min_samples)
    overall_by_hour(rows, args.min_samples)

    print(f"\nLegend: W% = win rate, 95% CI = Wilson confidence interval, W/L = wins/losses, n = sample size")
    print(f"All times in GMT+4 (Tbilisi). Minimum {args.min_samples} samples required.")

if __name__ == "__main__":
    main()
