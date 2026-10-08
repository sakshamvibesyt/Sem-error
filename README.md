# DesiMovieFinder — Render Ready

A Telethon-based Telegram automation/userbot with MongoDB persistence.

## Features

- `.help`
- `.ping`
- `.alive`
- `.tagall [text]` — 5 members per message
- `.onetag [text]`
- `.stop`
- `.broadcast [text]`
- `.pmguard on/off`
- `.approve` / `.disapprove`
- `.autoreact on/off`
- `.autoreply on/off`
- `.autoreply set [text]`
- `.clone` — saves your own logged-in account profile snapshot
- `.reclone` — restores that snapshot

## Required environment variables

```text
API_ID=
API_HASH=
SESSION_STRING=
OWNER_ID=
MONGO_URI=
BOT_TOKEN=
PREFIX=.
TAG_DELAY=1.2
BROADCAST_DELAY=2.0
```

`BOT_TOKEN` is optional in this version.

## Getting Telegram API credentials

Use Telegram's official API development page to create an API ID and API hash. Do not put these values directly into `bot.py`.

## Creating SESSION_STRING

Generate a Telethon StringSession locally on your own device. Never publish it in GitHub, screenshots, or chat. A session string gives access to the Telegram account it belongs to.

## MongoDB

Create a MongoDB database and put its connection URI in `MONGO_URI`.

The bot stores:
- group IDs/titles
- settings
- approved PM users
- profile snapshot

## Render

1. Push this folder to a private GitHub repository.
2. In Render, create a **Background Worker** from the repository.
3. Render can use `render.yaml`, or add the environment variables manually.
4. Build command:
   `pip install -r requirements.txt`
5. Start command:
   `python bot.py`

## Important

Use this only with accounts/groups you control or have permission to manage. Telegram can rate-limit accounts that send too many messages. Keep tag/broadcast delays reasonable.
