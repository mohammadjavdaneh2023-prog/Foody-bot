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

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
session = os.environ["TG_STRING_SESSION"]
with TelegramClient(StringSession(session), api_id, api_hash, proxy=proxy_from_env()) as client:
    for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            kind = "group" if dialog.is_group else "channel"
            print(f"{dialog.name}\t{dialog.id}\t{kind}")
