"""
Automated data pipeline: scrape → analyze → dashboard.
Run via cron or systemd timer.

Usage:
    python3 update_data.py                     # full pipeline
    python3 update_data.py --skip-scrape       # skip scraping (re-analyze only)
    python3 update_data.py --skip-analyze      # scrape only
"""
import argparse, os, subprocess, sys, time

DIR = os.path.dirname(os.path.abspath(__file__))

def run_step(name, cmd):
    print(f"[{time.strftime('%H:%M:%S')}] {name}...")
    t0 = time.time()
    r = subprocess.run(cmd, cwd=DIR, capture_output=True, text=True, timeout=600)
    elapsed = time.time() - t0
    for line in r.stdout.strip().split("\n"):
        print(f"  {line}")
    if r.returncode != 0:
        print(f"  ERROR: {r.stderr.strip()}")
        return False
    print(f"  Done in {elapsed:.1f}s")
    return True

def main():
    parser = argparse.ArgumentParser(description="Update signals data pipeline")
    parser.add_argument("--skip-scrape", action="store_true")
    parser.add_argument("--skip-analyze", action="store_true")
    args = parser.parse_args()

    print(f"=== Data Update [{time.strftime('%Y-%m-%d %H:%M:%S')}] ===")

    if not args.skip_scrape:
        ok = run_step("Scraping Telegram", ["python3", "scrape_history.py"])
        if not ok:
            print("Scrape failed, aborting.")
            sys.exit(1)

    if not args.skip_analyze:
        run_step("Analyzing", ["python3", "analyzer_v3.py"])
        run_step("Dashboard", ["python3", "dashboard.py"])

    print(f"=== Update Complete ===")

if __name__ == "__main__":
    main()
