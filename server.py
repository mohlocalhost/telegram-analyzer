"""
Production API server for signals dashboard.
API key auth. All data from signals.json + heatmap_gmt4.csv.

Usage:
    python3 server.py                          # port 8080
    python3 server.py --port 9000              # custom port
    python3 server.py --master-key mysecret     # override master key

Endpoints:
    GET /dashboard.html                         interactive dashboard
    GET /api/v1/status                          health check
    GET /api/v1/today                           today's best slots
    GET /api/v1/top?n=20&min_samples=30         top slots
    GET /api/v1/strategy?target=12              strategy schedule
    GET /api/v1/avoid                           worst slots
    GET /api/v1/safest                          safest slots
    GET /api/v1/minutes                         5-min block analysis
    GET /api/v1/heatmap                         full heatmap data
    GET /api/v1/dashboard                       all data aggregated
    POST /admin/keys                            create API key
    GET  /admin/keys                            list API keys
    DELETE /admin/keys/{key}                    revoke API key
"""
import argparse, csv, json, os, subprocess, sys, time, uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# --- config ---
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNALS_JSON = os.path.join(DATA_DIR, "signals.json")
HEATMAP_CSV  = os.path.join(DATA_DIR, "heatmap_gmt4.csv")
KEYS_FILE    = os.path.join(DATA_DIR, "api_keys.json")
MASTER_KEY   = os.environ.get("MASTER_KEY") or os.environ.get("ADMIN_KEY") or "change-me-master-123"

# --- API key management ---
# Stores keys in api_keys.json (persistent across restarts on Railway via env var)
KEY_STORE = {}

def load_keys():
    global KEY_STORE
    if KEY_STORE:
        return KEY_STORE
    # Try file first
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            KEY_STORE = json.load(f)
        return KEY_STORE
    # Fallback to env var (for Railway ephemeral storage)
    env_keys = os.environ.get("API_KEYS_JSON")
    if env_keys:
        try:
            KEY_STORE = json.loads(env_keys)
            save_keys(KEY_STORE)
            return KEY_STORE
        except json.JSONDecodeError:
            pass
    KEY_STORE = {}
    return KEY_STORE

def save_keys(keys):
    global KEY_STORE
    KEY_STORE = keys
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2)

def validate_api_key(request):
    key = request.headers.get("X-API-Key", "")
    if not key:
        qs = parse_qs(urlparse(request.path).query)
        key = qs.get("api_key", [""])[0]
    if not key:
        return None
    keys = load_keys()
    info = keys.get(key)
    if info and info.get("active", True):
        return info
    return None

# --- data helpers ---
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def load_heatmap():
    rows = []
    if not os.path.exists(HEATMAP_CSV):
        return rows
    with open(HEATMAP_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "day": r["day"],
                "hour": int(r["hour"]),
                "win_rate": float(r["win_rate"]),
                "ci_low": float(r["ci_low"]),
                "ci_high": float(r["ci_high"]),
                "wins": int(r["wins"]),
                "losses": int(r["losses"]),
                "total": int(r["total"]),
            })
    return rows

def filter_slots(rows, min_samples=30):
    return [r for r in rows if r["total"] >= min_samples]

def today_slots(rows):
    now = datetime.now(timezone(timedelta(hours=4)))
    today_name = DAYS[now.weekday()]
    return [r for r in rows if r["day"] == today_name], today_name

def analyze_minutes():
    results = defaultdict(lambda: {"win": 0, "loss": 0})
    if not os.path.exists(SIGNALS_JSON):
        return results
    with open(SIGNALS_JSON) as f:
        data = json.load(f)
    pending = None
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
            pending = None
    return results

def minute_blocks_json(min_data):
    out = []
    for hour in range(24):
        slots = [(b, s) for (h, b), s in min_data.items()
                 if h == hour and s["win"] + s["loss"] >= 10]
        if not slots:
            continue
        slots.sort(key=lambda x: x[1]["win"] / (x[1]["win"] + x[1]["loss"]))
        best = slots[-1]
        worst = slots[0]
        b_wr = round(best[1]["win"] / (best[1]["win"] + best[1]["loss"]) * 100, 1)
        w_wr = round(worst[1]["win"] / (worst[1]["win"] + worst[1]["loss"]) * 100, 1)
        out.append({
            "hour": hour,
            "best_block": f"{best[0]*5:02d}-{best[0]*5+4:02d}",
            "best_wr": b_wr,
            "best_n": best[1]["win"] + best[1]["loss"],
            "best_wins": best[1]["win"],
            "best_losses": best[1]["loss"],
            "worst_block": f"{worst[0]*5:02d}-{worst[0]*5+4:02d}",
            "worst_wr": w_wr,
            "worst_n": worst[1]["win"] + worst[1]["loss"],
            "worst_wins": worst[1]["win"],
            "worst_losses": worst[1]["loss"],
        })
    return out

# --- JSON responses ---
def json_response(handler, data, status=200):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode())

def error_response(handler, msg, status=401):
    json_response(handler, {"error": msg}, status)

# --- request handler ---
class APIHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # Public: dashboard page
        if path == "/dashboard.html" or path == "" or path == "/":
            return super().do_GET()

        # Public: status (no key needed)
        if path == "/api/v1/status":
            return self.handle_status()

        # Public: run commands (interactive dashboard buttons)
        if path == "/api/run":
            return self.handle_run(qs)

        # Admin endpoints
        if path == "/admin/keys":
            mk = qs.get("master", [""])[0] or self.headers.get("X-Master-Key", "")
            if mk != MASTER_KEY:
                return error_response(self, "invalid master key")
            return self.handle_admin_list_keys()

        if path.startswith("/admin/keys/"):
            mk = qs.get("master", [""])[0] or self.headers.get("X-Master-Key", "")
            if mk != MASTER_KEY:
                return error_response(self, "invalid master key")
            key_to_revoke = path.split("/")[-1]
            return self.handle_admin_revoke_key(key_to_revoke)

        # All other API endpoints require auth
        user = validate_api_key(self)
        if not user:
            return error_response(self, "invalid or missing API key (send X-API-Key header or ?api_key=...)")

        # API v1 endpoints
        if path == "/api/v1/today":
            return self.handle_today()
        if path == "/api/v1/top":
            return self.handle_top(qs)
        if path == "/api/v1/strategy":
            return self.handle_strategy(qs)
        if path == "/api/v1/avoid":
            return self.handle_avoid()
        if path == "/api/v1/safest":
            return self.handle_safest()
        if path == "/api/v1/minutes":
            return self.handle_minutes()
        if path == "/api/v1/heatmap":
            return self.handle_heatmap()
        if path == "/api/v1/dashboard":
            return self.handle_dashboard()

        # Static files (dashboard.html, etc.)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/admin/keys":
            mk = qs.get("master", [""])[0] or self.headers.get("X-Master-Key", "")
            if mk != MASTER_KEY:
                return error_response(self, "invalid master key")
            return self.handle_admin_create_key()

        if path == "/api/v1/refresh":
            user = validate_api_key(self)
            if not user:
                return error_response(self, "invalid API key")
            return self.handle_refresh()

        return error_response(self, "not found", 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-API-Key, X-Master-Key, Content-Type")
        self.end_headers()

    # --- handlers ---
    def handle_status(self):
        rows = load_heatmap()
        sigs = os.path.exists(SIGNALS_JSON)
        json_response(self, {
            "status": "ok",
            "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "heatmap_slots": len(rows),
            "signals_file": sigs,
            "version": "1.0",
        })

    COMMANDS = {
        "today":   ["--today"],
        "top20":   [],
        "by-ci":   ["--by-ci"],
        "strategy": ["--strategy"],
        "avoid":   ["--avoid"],
        "safest":  ["--safest"],
    }

    def handle_run(self, qs):
        cmd = qs.get("cmd", [""])[0]
        args_str = qs.get("args", [""])[0]
        base_args = self.COMMANDS.get(cmd)
        if base_args is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Unknown command")
            return
        full_args = base_args + (args_str.split() if args_str else [])
        try:
            r = subprocess.run(
                ["python3", "best_signals.py"] + full_args,
                cwd=DATA_DIR, capture_output=True, text=True, timeout=60,
            )
            out = r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            out = "Command timed out (60s)"
        except Exception as e:
            out = f"Error: {e}"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out.encode())

    def handle_today(self):
        rows = filter_slots(load_heatmap())
        slots, today_name = today_slots(rows)
        json_response(self, {"day": today_name, "slots": slots})

    def handle_top(self, qs):
        n = int(qs.get("n", ["20"])[0])
        min_s = int(qs.get("min_samples", ["30"])[0])
        rows = filter_slots(load_heatmap(), min_s)
        rows.sort(key=lambda r: (-r["win_rate"], -r["ci_low"], -r["total"]))
        json_response(self, {"top": n, "min_samples": min_s, "total": len(rows), "slots": rows[:n]})

    def handle_strategy(self, qs):
        target = int(qs.get("target", ["12"])[0])
        rows = filter_slots(load_heatmap())
        thresholds = [97, 95, 93, 91, 89, 87, 85, 83, 80]
        result = []
        for th in thresholds:
            qualified = [r for r in rows if r["win_rate"] >= th]
            if not qualified:
                continue
            per_day = len(qualified)
            avg_wr = sum(r["win_rate"] for r in qualified) / len(qualified)
            losses_per_200 = round(200 * (1 - avg_wr / 100), 1)
            result.append({
                "threshold": th,
                "slots": per_day,
                "signals_per_day": per_day,
                "avg_wr": round(avg_wr, 1),
                "losses_per_200": losses_per_200,
            })
        json_response(self, {"target": target, "tiers": result})

    def handle_avoid(self):
        rows = filter_slots(load_heatmap())
        rows.sort(key=lambda r: (-r["losses"] / r["total"], -r["losses"]))
        out = []
        for r in rows[:10]:
            loss_rate = round(r["losses"] / r["total"] * 100, 1)
            per_200 = round(200 * loss_rate / 100, 1)
            out.append({**r, "loss_rate": loss_rate, "losses_per_200": per_200})
        json_response(self, {"slots": out})

    def handle_safest(self):
        rows = filter_slots(load_heatmap())
        safe = [r for r in rows if r["losses"] / r["total"] * 100 <= 5]
        safe.sort(key=lambda r: (r["losses"] / r["total"], -r["total"]))
        json_response(self, {"slots": safe})

    def handle_minutes(self):
        min_data = analyze_minutes()
        json_response(self, {
            "total_paired": sum(s["win"]+s["loss"] for s in min_data.values()),
            "blocks": minute_blocks_json(min_data),
        })

    def handle_heatmap(self):
        rows = load_heatmap()
        grid = {}
        for r in rows:
            day = r["day"]
            if day not in grid:
                grid[day] = {}
            grid[day][r["hour"]] = {
                "wr": r["win_rate"],
                "n": r["total"],
                "wins": r["wins"],
                "losses": r["losses"],
                "ci_low": r["ci_low"],
                "ci_high": r["ci_high"],
            }
        json_response(self, {"grid": grid})

    def handle_dashboard(self):
        rows = filter_slots(load_heatmap())
        slots_today, today_name = today_slots(rows)
        rows_sorted = sorted(rows, key=lambda r: (-r["win_rate"], -r["ci_low"]))
        min_data = analyze_minutes()
        json_response(self, {
            "total_slots": len(rows),
            "today": {"day": today_name, "slots": slots_today},
            "top20": rows_sorted[:20],
            "minutes": {
                "total_paired": sum(s["win"]+s["loss"] for s in min_data.values()),
                "blocks": minute_blocks_json(min_data),
            },
        })

    def handle_refresh(self):
        try:
            subprocess.run(["python3", "analyzer_v3.py"], cwd=DATA_DIR,
                          capture_output=True, text=True, timeout=120)
            json_response(self, {"status": "ok", "message": "data refreshed"})
        except Exception as e:
            error_response(self, f"refresh failed: {e}", 500)

    def handle_admin_create_key(self):
        keys = load_keys()
        new_key = str(uuid.uuid4())
        label = f"user_{len(keys) + 1}"
        keys[new_key] = {
            "label": label,
            "created": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "active": True,
        }
        save_keys(keys)
        json_response(self, {"api_key": new_key, "label": label}, 201)

    def handle_admin_list_keys(self):
        keys = load_keys()
        safe = {k: v for k, v in keys.items()}
        json_response(self, {"keys": safe})

    def handle_admin_revoke_key(self, key):
        keys = load_keys()
        if key in keys:
            keys[key]["active"] = False
            save_keys(keys)
            json_response(self, {"status": "revoked", "key": key})
        else:
            error_response(self, "key not found", 404)

    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

def main():
    parser = argparse.ArgumentParser(description="Signals API server")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--master-key", default=None)
    args = parser.parse_args()

    global MASTER_KEY
    if args.master_key:
        MASTER_KEY = args.master_key

    os.chdir(DATA_DIR)

    # ensure api_keys.json exists
    if not os.path.exists(KEYS_FILE):
        save_keys({})

    print(f"Signals API server")
    print(f"  URL:  http://{args.host}:{args.port}/")
    print(f"  Dashboard: http://{args.host}:{args.port}/dashboard.html")
    print(f"  Master key: {MASTER_KEY[:8]}...{MASTER_KEY[-4:]}")
    print(f"  API keys: {len(load_keys())} registered")
    print(f"  Signals: {os.path.exists(SIGNALS_JSON)}")
    print(f"  Heatmap: {os.path.exists(HEATMAP_CSV)}")
    print()

    HTTPServer((args.host, args.port), APIHandler).serve_forever()

if __name__ == "__main__":
    main()
