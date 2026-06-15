import os
import json
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
OUTPUT_FILE = "signals.json"
SESSION_NAME = "scraper_session"

WIN_KEYWORDS = ["✅", "WIN", "win"]
LOSS_KEYWORDS = ["❌", "LOSS", "loss"]

async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    print(f"Connected. Fetching messages from channel {CHANNEL_ID}...")

    messages = []
    count = 0

    async for message in client.iter_messages(CHANNEL_ID, limit=None):
        if not message.text:
            continue

        text = message.text.strip()
        text_lower = text.lower()

        result = None
        if any(k.lower() in text_lower for k in WIN_KEYWORDS):
            result = "WIN"
        elif any(k.lower() in text_lower for k in LOSS_KEYWORDS):
            result = "LOSS"

        messages.append({
            "id": message.id,
            "date": message.date.isoformat(),
            "text": text,
            "result": result,
        })

        count += 1
        if count % 200 == 0:
            print(f"  Fetched {count} messages...")

    print(f"Total messages fetched: {count}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    print(f"Saved to {OUTPUT_FILE}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
