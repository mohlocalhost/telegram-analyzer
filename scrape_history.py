import os, json, asyncio
from dotenv import load_dotenv
from telethon import TelegramClient, errors

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
OUTPUT_FILE = "signals.json"
SESSION_NAME = "scraper_session"

WIN_KEYWORDS = ["✅", "WIN", "win"]
LOSS_KEYWORDS = ["❌", "LOSS", "loss"]

def load_existing():
    if not os.path.exists(OUTPUT_FILE):
        return {}, 0
    with open(OUTPUT_FILE) as f:
        data = json.load(f)
    by_id = {m["id"]: m for m in data}
    return by_id, len(data)

def save_all(messages):
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUTPUT_FILE)
    print(f"  Saved {len(messages)} messages")

async def fetch_new(client, existing, last_id):
    messages = list(existing.values())
    count = len(messages)
    last_save = count

    kwargs = {"limit": None}
    if last_id:
        kwargs["min_id"] = last_id + 1

    while True:
        try:
            async for message in client.iter_messages(CHANNEL_ID, **kwargs, wait_time=2):
                if not message.text:
                    continue
                text = message.text.strip()
                text_lower = text.lower()

                if text.startswith("📊 Last Hour Results"):
                    count += 1
                    if count % 200 == 0:
                        print(f"  Fetched {count} messages...")
                    continue

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
                if count - last_save >= 500:
                    save_all(messages)
                    last_save = count
            break
        except (errors.FloodWaitError, errors.RPCError,
                asyncio.TimeoutError, ConnectionError, OSError) as e:
            print(f"  Connection issue: {e}. Retrying in 10s...")
            await asyncio.sleep(10)

    save_all(messages)
    print(f"Done. Total: {count} messages")
    return messages

async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    existing, prev_count = load_existing()
    last_id = max(existing) if existing else None
    print(f"Existing: {prev_count} messages, last ID: {last_id}")

    print(f"Connected. Fetching from channel {CHANNEL_ID}...")
    messages = await fetch_new(client, existing, last_id)
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
