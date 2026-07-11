import asyncio
import logging
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_NAME = os.environ.get("SESSION_NAME", "forwarder_session")

def _parse_channels(raw):
    out = []
    for c in raw.split(","):
        c = c.strip()
        if c.lstrip("-").isdigit():
            out.append(int(c))
        else:
            out.append(c)
    return out

SOURCE_CHANNELS = _parse_channels(os.environ["SOURCE_CHANNELS"])
DEST_CHANNELS = _parse_channels(os.environ["DEST_CHANNELS"])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("forwarder.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)


def make_client():
    session_str = os.environ.get("TELETHON_SESSION")
    if session_str:
        log.info("Using StringSession (Railway mode)")
        return TelegramClient(StringSession(session_str), API_ID, API_HASH)
    log.info("Using file-based session (local mode)")
    return TelegramClient(SESSION_NAME, API_ID, API_HASH)


client = make_client()


async def resolve_channels(channel_list):
    entities = []
    for ch in channel_list:
        try:
            entity = await client.get_entity(ch)
            entities.append(entity)
            log.info(f"Resolved: {ch} -> {getattr(entity, 'title', ch)}")
        except Exception as e:
            log.error(f"Could not resolve '{ch}': {e}")
    return entities


async def generate_session():
    log.info("Creating StringSession for Railway deployment...")
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()
    session_str = client.session.save()
    print("\n" + "=" * 60)
    print("SESSION STRING (copy this to Railway env TELETHON_SESSION):")
    print("=" * 60)
    print(session_str)
    print("=" * 60 + "\n")
    await client.disconnect()


def run_health_server():
    PORT = int(os.environ.get("PORT", 8080))
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, *a):
            pass
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log.info(f"Health server listening on port {PORT}")
    server.serve_forever()


async def main():
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()
    log.info("Starting Telegram forwarder...")
    await client.start()
    log.info("Logged in successfully")

    source_entities = await resolve_channels(SOURCE_CHANNELS)
    dest_entities = await resolve_channels(DEST_CHANNELS)

    if not source_entities or not dest_entities:
        log.error("Could not resolve channels. Exiting.")
        return

    source_ids = [e.id for e in source_entities]

    @client.on(events.NewMessage(chats=source_ids))
    async def handler(event):
        message = event.message
        for dest in dest_entities:
            try:
                await client.send_message(dest, message)
                log.info(f"Forwarded message {message.id} -> {getattr(dest, 'title', dest)}")
            except Exception as e:
                log.error(f"Forward failed for message {message.id}: {e}")

    log.info("Listening... Running 24/7. Press Ctrl+C to stop")
    await client.run_until_disconnected()


if __name__ == "__main__":
    if "--generate-session" in sys.argv:
        asyncio.run(generate_session())
    else:
        asyncio.run(main())
