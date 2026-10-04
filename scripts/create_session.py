import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

from app.config import proxy_from_env

api_id = int(os.getenv("TG_API_ID") or input("TG_API_ID: "))
api_hash = os.getenv("TG_API_HASH") or input("TG_API_HASH: ").strip()
proxy = proxy_from_env()
if proxy:
    print(f"Using {proxy['proxy_type']} proxy at {proxy['addr']}:{proxy['port']}")
with TelegramClient(StringSession(), api_id, api_hash, proxy=proxy) as client:
    print("\nTG_STRING_SESSION (keep it secret):\n")
    print(client.session.save())
