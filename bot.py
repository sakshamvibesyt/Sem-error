import os
import asyncio
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.tl.types import User

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.environ["OWNER_ID"])
MONGO_URI = os.environ["MONGO_URI"]

PREFIX = os.getenv("PREFIX", ".")
TAG_DELAY = float(os.getenv("TAG_DELAY", "1.2"))
BROADCAST_DELAY = float(os.getenv("BROADCAST_DELAY", "2.0"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("DesiMovieFinder")

mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = mongo["desi_movie_finder"]
settings = db["settings"]
users = db["users"]
groups = db["groups"]

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient("bot_session", API_ID, API_HASH) if BOT_TOKEN else None

tag_tasks = {}

DEFAULT_SETTINGS = {
    "pmguard": False,
    "autoreact": False,
    "autoreply": False,
    "autoreply_text": "Thanks for your message ❤️",
    "approved": [],
}

def is_owner(event):
    return event.sender_id == OWNER_ID

def get_settings():
    doc = settings.find_one({"_id": OWNER_ID})
    if not doc:
        doc = {"_id": OWNER_ID, **DEFAULT_SETTINGS}
        settings.insert_one(doc)
    return doc

def set_setting(key, value):
    settings.update_one({"_id": OWNER_ID}, {"$set": {key: value}}, upsert=True)

def help_text():
    return """⚙️ **ALL COMMANDS ACTIVE** ⚙️

🔹 `.ping` — Check response speed
🔹 `.alive` — Check bot status
🔹 `.onetag` — Tag members with dialogues
🔹 `.tagall [text]` — 5-5 members ko tag karein
🔹 `.broadcast [text]` — Saved groups me bhejein
🔹 `.stop` — Tag loop ko rokein

🔹 `.pmguard on/off` — PM Guard
🔹 `.approve` — PM user approve
🔹 `.disapprove` — PM user remove

🔹 `.autoreact on/off` — Auto react
🔹 `.autoreply on/off` — Auto reply
🔹 `.autoreply set [text]` — Reply text set

🔹 `.clone` — Apne profile ke selected fields ko save
🔹 `.reclone` — Saved profile ko restore

⚠️ Owner-only commands: broadcast, settings, profile tools."""

async def save_group(event):
    if not event.is_group:
        return
    try:
        chat = await event.get_chat()
        groups.update_one(
            {"chat_id": event.chat_id},
            {"$set": {
                "chat_id": event.chat_id,
                "title": getattr(chat, "title", str(event.chat_id)),
                "updated_at": datetime.now(timezone.utc),
            }},
            upsert=True
        )
    except Exception as e:
        log.warning("save_group: %s", e)

async def get_members(chat):
    result = []
    async for u in client.iter_participants(chat):
        if isinstance(u, User) and not u.bot and not u.deleted:
            result.append(u)
    return result

async def mention_block(users_list, text):
    chunks = [users_list[i:i+5] for i in range(0, len(users_list), 5)]
    for chunk in chunks:
        mentions = []
        for u in chunk:
            name = (u.first_name or "User").replace("\n", " ")
            mentions.append(f"[{name}](tg://user?id={u.id})")
        yield (text + "\n\n" + " • ".join(mentions)).strip()
        await asyncio.sleep(TAG_DELAY)

@client.on(events.NewMessage)
async def command_handler(event):
    await save_group(event)

    text = (event.raw_text or "").strip()
    if not text.startswith(PREFIX):
        return

    parts = text.split(maxsplit=2)
    cmd = parts[0][1:].lower()
    arg = parts[1] if len(parts) > 1 else ""
    rest = parts[2] if len(parts) > 2 else ""

    if cmd == "help":
        await event.reply(help_text())
        return

    if cmd == "ping":
        import time
        start = time.perf_counter()
        msg = await event.reply("🏓 Pinging...")
        ms = round((time.perf_counter() - start) * 1000)
        await msg.edit(f"🏓 **Pong!** `{ms} ms`")
        return

    if cmd == "alive":
        await event.reply("🟢 **DesiMovieFinder is alive!**\n⚡ Online & ready.")
        return

    if cmd in {"pmguard", "autoreact"}:
        if not is_owner(event):
            return
        if arg.lower() not in {"on", "off"}:
            await event.reply(f"Usage: `{PREFIX}{cmd} on/off`")
            return
        set_setting(cmd, arg.lower() == "on")
        await event.reply(f"✅ `{cmd}` → **{arg.upper()}**")
        return

    if cmd == "autoreply":
        if not is_owner(event):
            return
        if arg.lower() == "set":
            if not rest:
                await event.reply(f"Usage: `{PREFIX}autoreply set <text>`")
                return
            set_setting("autoreply_text", rest)
            await event.reply("✅ Auto-reply text updated.")
            return
        if arg.lower() in {"on", "off"}:
            set_setting("autoreply", arg.lower() == "on")
            await event.reply(f"✅ `autoreply` → **{arg.upper()}**")
            return
        await event.reply(f"Usage: `{PREFIX}autoreply on/off` or `{PREFIX}autoreply set <text>`")
        return

    if cmd == "approve":
        if not is_owner(event):
            return
        uid = event.sender_id
        settings.update_one({"_id": OWNER_ID}, {"$addToSet": {"approved": uid}}, upsert=True)
        await event.reply("✅ You are approved.")
        return

    if cmd == "disapprove":
        if not is_owner(event):
            return
        uid = event.sender_id
        settings.update_one({"_id": OWNER_ID}, {"$pull": {"approved": uid}}, upsert=True)
        await event.reply("✅ Access removed.")
        return

    if cmd == "stop":
        task = tag_tasks.pop(event.chat_id, None)
        if task:
            task.cancel()
            await event.reply("🛑 Tag loop stopped.")
        else:
            await event.reply("ℹ️ No active tag loop.")
        return

    if cmd in {"tagall", "onetag"}:
        if not event.is_group:
            await event.reply("❌ Ye command group me use karo.")
            return
        members = await get_members(event.chat_id)
        if not members:
            await event.reply("❌ Members fetch nahi ho paaye.")
            return

        if cmd == "onetag":
            text = arg or "📢 Attention everyone!"
            users_to_tag = members[:]
            task = asyncio.current_task()
            tag_tasks[event.chat_id] = task
            try:
                for u in users_to_tag:
                    await event.reply(f"{text}\n\n[{u.first_name or 'User'}](tg://user?id={u.id})")
                    await asyncio.sleep(TAG_DELAY)
            except asyncio.CancelledError:
                pass
            finally:
                tag_tasks.pop(event.chat_id, None)
            return

        text_to_use = "📢 Attention everyone!"
        if arg:
            text_to_use = text.split(maxsplit=1)[1]
        task = asyncio.current_task()
        tag_tasks[event.chat_id] = task
        try:
            async for message in mention_block(members, text_to_use):
                await event.reply(message, parse_mode="md")
        except asyncio.CancelledError:
            pass
        finally:
            tag_tasks.pop(event.chat_id, None)
        return

    if cmd == "broadcast":
        if not is_owner(event):
            return
        message = text[len(PREFIX + cmd):].strip()
        if not message:
            await event.reply(f"Usage: `{PREFIX}broadcast <text>`")
            return
        chat_ids = [x["chat_id"] for x in groups.find({}, {"chat_id": 1})]
        sent = failed = 0
        for cid in chat_ids:
            try:
                await client.send_message(cid, message)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(BROADCAST_DELAY)
        await event.reply(f"📢 **Broadcast finished**\n\n✅ Sent: `{sent}`\n❌ Failed: `{failed}`")
        return

    # Safe profile snapshot/restore: only the currently logged-in account.
    if cmd == "clone":
        if not is_owner(event):
            return
        me = await client.get_me()
        snapshot = {
            "first_name": me.first_name,
            "last_name": me.last_name,
            "about": (await client.get_entity("me")).about if hasattr((await client.get_entity("me")), "about") else "",
        }
        settings.update_one({"_id": OWNER_ID}, {"$set": {"profile_snapshot": snapshot}}, upsert=True)
        await event.reply("✅ Current account profile snapshot saved.\nUse `.reclone` to restore it later.")
        return

    if cmd == "reclone":
        if not is_owner(event):
            return
        doc = get_settings()
        snap = doc.get("profile_snapshot")
        if not snap:
            await event.reply("❌ No saved profile snapshot.")
            return
        try:
            await client(functions.account.UpdateProfileRequest(
                first_name=snap.get("first_name") or "",
                last_name=snap.get("last_name") or "",
                about=snap.get("about") or "",
            ))
            await event.reply("✅ Saved profile restored.")
        except Exception as e:
            await event.reply(f"❌ Restore failed: `{type(e).__name__}`")
        return

@client.on(events.NewMessage(incoming=True))
async def incoming_handler(event):
    if event.raw_text and event.raw_text.startswith(PREFIX):
        return

    st = get_settings()

    # PM guard
    if event.is_private and not event.out:
        if st.get("pmguard"):
            approved = set(st.get("approved", []))
            if event.sender_id != OWNER_ID and event.sender_id not in approved:
                try:
                    await event.reply("🔒 **PM Guard active.**\nPlease wait for approval.")
                except Exception:
                    pass
                return

        if st.get("autoreply") and event.sender_id != OWNER_ID:
            try:
                await event.reply(st.get("autoreply_text", "Thanks for your message ❤️"))
            except Exception:
                pass

    # Lightweight auto-react: uses a normal Telegram reaction if available.
    if st.get("autoreact") and not event.out:
        try:
            await client(functions.messages.SendReactionRequest(
                peer=event.peer_id,
                msg_id=event.id,
                reaction=[types.ReactionEmoji(emoticon="❤️")],
                big=False,
                add_to_recent=False
            ))
        except Exception:
            pass

async def main():
    await client.start()
    me = await client.get_me()
    log.info("Logged in as %s (%s)", me.first_name, me.id)
    if me.id != OWNER_ID:
        log.warning("OWNER_ID does not match logged-in account id.")

    if bot_client:
        try:
            await bot_client.start(bot_token=BOT_TOKEN)
            log.info("Bot API client started.")
        except Exception as e:
            log.warning("BOT_TOKEN could not start: %s", e)

    print(help_text())
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
