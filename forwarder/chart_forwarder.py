import asyncio
import logging
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

import pandas as pd
import yfinance as yf

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_NAME = os.environ.get("SESSION_NAME", "chart_forwarder_session")
FOREX_SOURCE = os.environ.get("FOREX_SOURCE", "-1002770121139")
FOREX_DEST = os.environ.get("FOREX_DEST", "-1003877136886")
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


def pair_to_symbol(pair):
    pair = PAIR_CORRECTIONS.get(pair, pair).upper().strip()
    if len(pair) == 6 and pair.isalpha():
        return f"{pair}=X"
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


async def verify_signal(signal, signal_time_utc):
    pair = signal["pair"]
    direction = signal["direction"]
    symbol = pair_to_symbol(pair)
    if not symbol:
        log.error(f"Cannot resolve symbol: {pair}")
        return None

    candle_start = signal_time_utc.replace(second=0, microsecond=0)
    start = candle_start - timedelta(minutes=2)
    end = candle_start + timedelta(minutes=4)

    for attempt in range(3):
        try:
            df = yf.download(symbol, start=start, end=end, interval="1m", progress=False)
        except Exception as e:
            log.warning(f"yfinance attempt {attempt+1} failed: {e}")
            df = pd.DataFrame()
        if not df.empty:
            break
        if attempt < 2:
            log.info(f"  No data yet, retrying in 30s...")
            await asyncio.sleep(30)

    if df.empty:
        log.warning(f"No data after retries for {symbol}")
        return None

    tz = df.index.tz
    target = pd.Timestamp(candle_start).tz_convert(tz) if tz else pd.Timestamp(candle_start)

    entry_idx = None
    for i, ts in enumerate(df.index):
        if ts >= target:
            entry_idx = i
            break

    if entry_idx is None or entry_idx < 1:
        log.warning(f"No entry candle or no candle before entry for {symbol}")
        return None

    try:
        entry_price = float(df.iloc[entry_idx - 1][("Close", symbol)])
        c1_price = float(df.iloc[entry_idx][("Close", symbol)])
    except (KeyError, TypeError, IndexError):
        log.warning(f"Failed to read price data for {symbol}")
        return None

    c1_won = (c1_price > entry_price) if direction == "CALL" else (c1_price < entry_price)

    if c1_won:
        return {"result": "WIN", "level": 0, "label": "PROFIT"}

    if entry_idx + 1 < len(df):
        try:
            c2_price = float(df.iloc[entry_idx + 1][("Close", symbol)])
        except (KeyError, TypeError, IndexError):
            return {"result": "LOSS", "level": None, "label": "LOSS"}
        c2_won = (c2_price > c1_price) if direction == "CALL" else (c2_price < c1_price)
        if c2_won:
            return {"result": "WIN", "level": 1, "label": "PROFIT 1"}

    return {"result": "LOSS", "level": None, "label": "LOSS"}


def get_field_from_row(row, field, symbol):
    try:
        return float(row[(field, symbol)])
    except (KeyError, TypeError):
        pass
    try:
        return float(row[field])
    except (KeyError, TypeError):
        return None


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
            log.info(f"  ⏰ {signal['entry_hour']:02d}:{signal['entry_min']:02d} UTC-2 → entry at {entry_time.strftime('%H:%M:%S')} UTC")
        else:
            entry_time = msg.date.replace(tzinfo=timezone.utc) if msg.date.tzinfo is None else msg.date
            log.info(f"  No ⏰ field, using message time: {entry_time.strftime('%H:%M:%S')} UTC")

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
