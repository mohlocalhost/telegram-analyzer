#!/usr/bin/env python3
"""
Bankroll Tracker — Pocket Option
Goal: $70 → $450 by July 10, 2026
Risk per trade: 2.5% | Payout: 85% | Daily stop: 15%
"""
import json, math, os, sys
from datetime import date, datetime

STATE_FILE = os.path.join(os.path.dirname(__file__), "bankroll_state.json")

GOAL          = 450.0
START_BALANCE = 70.0
DEADLINE      = date(2026, 7, 10)
RISK_PCT      = 0.025
PAYOUT_PCT    = 0.85
DAILY_STOP    = 0.15

DEFAULT_STATE = {
    "balance": START_BALANCE,
    "peak_balance": START_BALANCE,
    "trades": [],
    "date": str(date.today()),
}

def load():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            s = json.load(f)
        if s.get("date") != str(date.today()):
            s["trades"] = []
            s["date"] = str(date.today())
        return s
    return dict(DEFAULT_STATE)

def save(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)

def calc(s):
    bal = s["balance"]
    peak = s["peak_balance"]
    today = date.today()
    days_left = (DEADLINE - today).days
    if days_left < 1:
        days_left = 1
    needed = max(0, GOAL - bal)
    daily_target = needed / days_left

    per_trade = bal * RISK_PCT
    win_add = per_trade * PAYOUT_PCT
    loss_amt = per_trade

    stop_bal = bal * (1 - DAILY_STOP)
    # stop loss from PEAK balance — locks in gains
    peak_stop = peak * (1 - DAILY_STOP)
    effective_stop = max(stop_bal, peak_stop)

    daily_pl = sum(t["pnl"] for t in s["trades"])
    trades_today = len(s["trades"])
    wins = sum(1 for t in s["trades"] if t["pnl"] > 0)
    losses = sum(1 for t in s["trades"] if t["pnl"] < 0)

    progress = ((bal - START_BALANCE) / (GOAL - START_BALANCE)) * 100

    return {
        "bal": bal, "peak": peak, "days_left": days_left,
        "needed": needed, "daily_target": daily_target,
        "per_trade": per_trade, "win_add": win_add, "loss_amt": loss_amt,
        "stop_bal": effective_stop,
        "daily_pl": daily_pl, "trades_today": trades_today,
        "wins": wins, "losses": losses,
        "progress": progress,
        "today_target_remaining": max(0, daily_target - daily_pl),
        "on_stop": bal <= effective_stop,
        "goal_reached": bal >= GOAL,
    }

def show(i, s):
    bal = i["bal"]
    print("\n" + "=" * 52)
    print(f"  BANKROLL TRACKER           {date.today()}")
    print("=" * 52)
    print(f"  {i['progress']:5.1f}%  ${bal:<7.2f}  ←  ${GOAL:.2f}")
    print(f"               {'─' * (int(i['progress'] / 5) if i['progress'] > 0 else 0)}>")
    print()
    print(f"  Balance:       ${bal:<8.2f}  (start ${START_BALANCE:.2f})")
    print(f"  Goal:          ${GOAL:<8.2f}  (${i['needed']:.2f} away)")
    print(f"  Days left:     {i['days_left']}")
    print()
    print(f"  {'Daily target:':20} ${i['daily_target']:<7.2f}")
    print(f"  {'Today P&L:':20} ${i['daily_pl']:<+.2f}")
    if i["daily_target"] > 0:
        target_pct = min(100, (i["daily_pl"] / i["daily_target"]) * 100)
        bar_len = int(target_pct / 5)
        print(f"  {'Progress:':20} {'█' * bar_len}{'░' * (20 - bar_len)} {target_pct:.0f}%")
    print()
    print(f"  {'Per trade (2.5%):':20} ${i['per_trade']:<7.2f}")
    print(f"  {'  Win adds:':20} +${i['win_add']:<7.2f}")
    print(f"  {'  Loss costs:':20} -${i['loss_amt']:<7.2f}")
    print()
    print(f"  {'Daily stop loss:':20} ${i['stop_bal']:<7.2f}")
    print(f"  {'Trades today:':20} {i['trades_today']}  ({i['wins']}W/{i['losses']}L)")
    print()
    if i["goal_reached"]:
        print("  🎉 GOAL REACHED! You hit $450!")
    elif i["on_stop"]:
        print("  STOP — daily loss limit hit. Walk away.")
    else:
        print(f"  Next trade: risk ${i['per_trade']:.2f} → +${i['win_add']:.2f} if win")
    print("=" * 52)

def main():
    s = load()
    i = calc(s)

    if len(sys.argv) < 2:
        show(i, s)
        return

    cmd = sys.argv[1]

    if cmd == "--win":
        amt = s["balance"] * RISK_PCT
        pnl = amt * PAYOUT_PCT
        s["balance"] += pnl
        if s["balance"] > s["peak_balance"]:
            s["peak_balance"] = s["balance"]
        s["trades"].append({"pnl": pnl, "result": "win", "time": str(datetime.now())})
        save(s)
        print(f"WIN  +${pnl:.2f}  →  ${s['balance']:.2f}")

    elif cmd == "--loss":
        amt = s["balance"] * RISK_PCT
        pnl = -amt
        s["balance"] += pnl
        s["trades"].append({"pnl": pnl, "result": "loss", "time": str(datetime.now())})
        save(s)
        print(f"LOSS -${amt:.2f}  →  ${s['balance']:.2f}")

    elif cmd == "--set-balance":
        if len(sys.argv) < 3:
            print("Usage: --set-balance <amount>")
            return
        s["balance"] = float(sys.argv[2])
        if s["balance"] > s["peak_balance"]:
            s["peak_balance"] = s["balance"]
        save(s)
        print(f"Balance set to ${s['balance']:.2f}")

    elif cmd == "--reset":
        s = dict(DEFAULT_STATE)
        s["date"] = str(date.today())
        save(s)
        print("State reset to defaults.")

    elif cmd == "--log":
        for t in s["trades"]:
            sign = "+" if t["pnl"] > 0 else ""
            print(f"  {t['result']:5}  {sign}${t['pnl']:<.2f}")
        print(f"  Total: ${sum(t['pnl'] for t in s['trades']):+.2f}")

    elif cmd == "--project":
        bal = s["balance"]
        win_rate = 0.85
        ev = 1 + RISK_PCT * PAYOUT_PCT * win_rate - RISK_PCT * (1 - win_rate)
        print(f"\n  Projection ({win_rate*100:.0f}% WR, {RISK_PCT*100:.1f}% risk, {PAYOUT_PCT*100:.0f}% payout)")
        print(f"  {'Trades':>7} {'Balance':>10} {'Per Trade':>10}")
        print(f"  {'─'*7} {'─'*10} {'─'*10}")
        for t in range(0, 201, 10):
            projected = bal * (ev ** t)
            pt = projected * RISK_PCT
            print(f"  {t:>6}  ${projected:>8.2f}  ${pt:>7.2f}")
            if projected >= GOAL:
                print(f"  → ~{t} trades to $450")
                break
        if projected < GOAL:
            needed = math.log(GOAL / bal) / math.log(ev)
            print(f"  → Need ~{needed:.0f} trades total")
        print()

    else:
        print("Commands: (no arg) | --win | --loss | --set-balance <amt> | --reset | --log | --project")

if __name__ == "__main__":
    main()
