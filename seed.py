"""
Seed default data files for a fresh deployment.
Generates empty/fallback files so the server starts gracefully.
"""
import json, csv, os

DIR = os.path.dirname(os.path.abspath(__file__))

def seed_signals():
    path = os.path.join(DIR, "signals.json")
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump([], f)
        print(f"Created {path} (empty)")

def seed_heatmap():
    path = os.path.join(DIR, "heatmap_gmt4.csv")
    if not os.path.exists(path):
        days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["day","hour","win_rate","ci_low","ci_high","wins","losses","total"])
            for d in days:
                for h in range(24):
                    w.writerow([d, h, 0.0, 0.0, 0.0, 0, 0, 0])
        print(f"Created {path} (placeholder)")

def seed_dashboard():
    path = os.path.join(DIR, "dashboard.html")
    if not os.path.exists(path):
        html = "<!DOCTYPE html><html><head><title>Signals Dashboard</title></head><body><h1>Signals Dashboard</h1><p>No data yet. Run <code>python3 analyzer_v3.py && python3 dashboard.py</code> to generate.</p></body></html>"
        with open(path, "w") as f:
            f.write(html)
        print(f"Created {path} (placeholder)")

def seed_keys():
    path = os.path.join(DIR, "api_keys.json")
    # Preserve existing keys, don't create empty
    if os.path.exists(path):
        try:
            with open(path) as f:
                existing = json.load(f)
            if existing:
                print(f"Keys file exists ({len(existing)} keys)")
                return
        except json.JSONDecodeError:
            pass
    # Don't create empty file - server.py handles default key
    print(f"No api_keys.json - server will use default key")

if __name__ == "__main__":
    seed_signals()
    seed_heatmap()
    seed_dashboard()
    seed_keys()
    print("Seeding complete.")
