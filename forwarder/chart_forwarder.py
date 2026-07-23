import asyncio
import json
import logging
import os
import sys
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_NAME = os.environ.get("SESSION_NAME", "chart_forwarder_session")
FOREX_SOURCE = os.environ.get("FOREX_SOURCE", "-1002770121139")
FOREX_DEST = os.environ.get("FOREX_DEST", "-1003877136886")
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")
HEALTH_PORT = int(os.environ.get("PORT", os.environ.get("HEALTH_PORT", "8080")))

PAIR_CORRECTIONS = {"USDCallAD": "USDCAD", "GBPCallAD": "GBPUSD"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("chart_forwarder.log"), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def parse_channel(ch):
    ch = ch.strip()
    return int(ch) if ch.lstrip("-").isdigit() else ch


SOURCE_ID = parse_channel(FOREX_SOURCE)
DEST_ID = parse_channel(FOREX_DEST)


def pair_to_twelve(pair):
    pair = PAIR_CORRECTIONS.get(pair, pair).upper().strip()
    if len(pair) == 6 and pair.isalpha():
        return f"{pair[:3]}/{pair[3:]}"
    return None


def parse_signal(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    pair = None
    direction = None
    entry_hour = None
    entry_min = None
    for line in lines:
        if "📊" in line:
            pair = line.replace("📊", "").strip()
        elif "Call" in line and "UP" in line:
            direction = "CALL"
        elif "PUT" in line and "DOWN" in line:
            direction = "PUT"
        elif line.startswith("⏰"):
            parts = line.replace("⏰", "").strip().split(":")
            if len(parts) == 2:
                entry_hour = int(parts[0])
                entry_min = int(parts[1])
    if not pair or not direction:
        return None
    return {"pair": pair, "direction": direction, "entry_hour": entry_hour, "entry_min": entry_min}


def build_result_text(pair, verification):
    if verification["result"] == "WIN":
        if verification["level"] == 0:
            return f"\U0001f5d3 {pair} Profit \u2705"
        return f"\U0001f5d3 {pair} PROFIT 1 \u26a1"
    return f"\U0001f5d3 {pair} LOSS \u274c"


UTC_MINUS_2 = timezone(timedelta(hours=-2))

def entry_time_to_utc(msg_date, entry_hour, entry_min):
    msg_date = msg_date.replace(tzinfo=timezone.utc) if msg_date.tzinfo is None else msg_date
    msg_utc_minus_2 = msg_date.astimezone(UTC_MINUS_2)
    entry_utc_minus_2 = msg_utc_minus_2.replace(hour=entry_hour, minute=entry_min, second=0, microsecond=0)
    return entry_utc_minus_2.astimezone(timezone.utc)


def fetch_forex_candles(symbol, count=5):
    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={symbol}"
        f"&interval=1min"
        f"&outputsize={count}"
        f"&timezone=UTC"
        f"&apikey={TWELVE_DATA_KEY}"
    )
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as e:
        log.warning(f"Twelve Data request failed: {e}")
        return None

    if data.get("status") != "ok":
        log.warning(f"Twelve Data error: {data.get('error', 'unknown')}")
        return None

    values = data.get("values", [])
    if not values:
        log.warning(f"Twelve Data returned no values for {symbol}")
        return None

    candles = []
    for v in reversed(values):
        try:
            dt = datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            o = float(v["open"])
            c = float(v["close"])
            candles.append({"time": dt, "open": o, "close": c})
        except (KeyError, ValueError, TypeError) as e:
            log.warning(f"Bad candle data: {v} - {e}")
            continue

    return candles


def is_green(candle):
    return candle["close"] > candle["open"]

def is_red(candle):
    return candle["close"] < candle["open"]


async def verify_signal(signal, entry_time_utc):
    pair = signal["pair"]
    direction = signal["direction"]
    symbol = pair_to_twelve(pair)
    if not symbol:
        log.error(f"Cannot resolve symbol: {pair}")
        return None

    for attempt in range(3):
        candles = fetch_forex_candles(symbol, count=5)
        if candles:
            break
        if attempt < 2:
            log.info(f"  Retrying in 30s...")
            await asyncio.sleep(30)

    if not candles:
        log.warning(f"No data for {symbol} after retries")
        return None

    candle_entry = None
    candle_martingale = None
    for c in candles:
        if c["time"] == entry_time_utc.replace(second=0, microsecond=0):
            candle_entry = c
        if c["time"] == entry_time_utc.replace(second=0, microsecond=0) + timedelta(minutes=1):
            candle_martingale = c

    if not candle_entry:
        log.warning(f"No candle at entry time {entry_time_utc} for {symbol}")
        log.info(f"  Available: {[c['time'].strftime('%H:%M') for c in candles]}")
        return None

    green = is_green(candle_entry)
    red = is_red(candle_entry)

    c1_won = green if direction == "CALL" else red

    if c1_won:
        return {"result": "WIN", "level": 0, "label": "PROFIT"}

    if candle_martingale:
        mgreen = is_green(candle_martingale)
        mred = is_red(candle_martingale)
        c2_won = mgreen if direction == "CALL" else mred
        if c2_won:
            return {"result": "WIN", "level": 1, "label": "PROFIT 1"}

    return {"result": "LOSS", "level": None, "label": "LOSS"}


def make_client():
    session_str = os.environ.get("TELETHON_SESSION")
    if session_str:
        return TelegramClient(StringSession(session_str), API_ID, API_HASH)
    return TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def generate_session():
    log.info("Creating StringSession for Railway deployment...")
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()
    session_str = client.session.save()
    print("\n" + "=" * 60)
    print("SESSION STRING (set this as Railway env TELETHON_SESSION):")
    print("=" * 60)
    print(session_str)
    print("=" * 60 + "\n")
    await client.disconnect()


client = make_client()
seen = set()


def run_health_server():
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, *a): pass
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    log.info(f"Health server on port {HEALTH_PORT}")
    server.serve_forever()


async def main():
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    log.info("Starting Chart-Verified Forwarder...")
    await client.start()
    log.info("Logged in successfully")

    try:
        source = await client.get_entity(SOURCE_ID)
        dest = await client.get_entity(DEST_ID)
    except Exception as e:
        log.error(f"Channel resolution failed: {e}")
        return

    source_name = getattr(source, "title", str(SOURCE_ID))
    dest_name = getattr(dest, "title", str(DEST_ID))
    log.info(f"Source: {source_name}")
    log.info(f"Dest:   {dest_name}")

    @client.on(events.NewMessage(chats=source.id))
    async def handler(event):
        msg = event.message
        text = msg.text.strip() if msg.text else ""
        if not text or msg.id in seen:
            return
        if "\U0001f5d3" in text or "Profit" in text or "Loss" in text:
            return

        signal = parse_signal(text)
        if not signal:
            return

        seen.add(msg.id)
        log.info(f"Signal #{msg.id}: {signal['pair']} {signal['direction']}")

        if signal["entry_hour"] is not None and signal["entry_min"] is not None:
            entry_time = entry_time_to_utc(msg.date, signal["entry_hour"], signal["entry_min"])
            log.info(f"  \u23f0 {signal['entry_hour']:02d}:{signal['entry_min']:02d} UTC-2 \u2192 entry at {entry_time.strftime('%H:%M:%S')} UTC")
        else:
            entry_time = msg.date.replace(tzinfo=timezone.utc) if msg.date.tzinfo is None else msg.date
            log.info(f"  No \u23f0 field, using message time: {entry_time.strftime('%H:%M:%S')} UTC")

        now = datetime.now(timezone.utc)
        wait = (entry_time - now).total_seconds() + 180
        if wait < 60:
            wait = 60
        log.info(f"  Waiting {wait:.0f}s for candles to close...")
        await asyncio.sleep(wait)

        verification = await verify_signal(signal, entry_time)

        if verification:
            result_text = build_result_text(signal["pair"], verification)
            try:
                await client.send_message(dest, result_text)
                log.info(f"Sent: {result_text}")
            except Exception as e:
                log.error(f"Send failed for #{msg.id}: {e}")
        else:
            log.warning(f"Verification failed for #{msg.id}")

    log.info("Listening for Forex M1 signals...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    if "--generate-session" in sys.argv:
        asyncio.run(generate_session())
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            log.info("Shutdown")
