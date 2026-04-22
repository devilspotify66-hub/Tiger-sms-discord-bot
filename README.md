# Tiger-SMS Discord Bot

A Discord bot that buys virtual phone numbers from [tiger-sms.com](https://tiger-sms.com)
via its public API and posts the received SMS verification code back into the
channel it was invoked from.

Supports both **slash commands** (`/buy`, `/status`, …) and **prefix commands**
(`!buy`, `!status`, …). Every order embed ships with two buttons — **Copy Code**
and **Copy Activation ID** — that return just the raw value ephemerally so you
can triple-click / long-press to copy.

---

## Features

| Command           | What it does                                          |
| ----------------- | ----------------------------------------------------- |
| `/buy <service> [country]` | Buy a number and auto-poll for the SMS code.  |
| `/status <id>`    | Check the current status of an activation.            |
| `/cancel <id>`    | Cancel an activation and refund the balance.          |
| `/balance`        | Show your tiger-sms account balance.                  |
| `/services`       | List popular service codes (`tg`, `wa`, `go`, …).     |
| `/countries`      | List popular country IDs (`33`=Colombia, `187`=USA…). |
| `/tigerhelp`      | Inline cheat-sheet for everything above.              |

- Polls every **15 s** for up to **20 min** per order (configurable via `.env`).
- Stores every activation in MongoDB (`tiger_orders` collection).
- Ships with a small React dashboard that shows live bot state + recent orders.

---

## Project layout

```
/app
├── backend/
│   ├── server.py           # FastAPI app + launches the bot via lifespan
│   ├── bot.py              # discord.py bot + all commands + OrderView buttons
│   ├── tiger_sms.py        # Async HTTP client for tiger-sms.com
│   ├── tiger_data.py       # Popular service / country lookup tables
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                # ← NEVER commit this file
└── frontend/
    └── src/                # React dashboard (status + recent orders)
```

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+** and **Yarn** (only if you want the dashboard)
- **MongoDB** running locally on `mongodb://localhost:27017` (or set `MONGO_URL`)
- A **Discord application + bot** — <https://discord.com/developers/applications>
- A **tiger-sms.com account + API key** (and some RUB on balance) — <https://tiger-sms.com>

---

## 1. Create the Discord application

1. Go to <https://discord.com/developers/applications> → **New Application**.
2. Open the new app → **Bot** → **Reset Token** → copy the token (this is your
   `DISCORD_BOT_TOKEN`).
3. **Privileged Gateway Intents** → enable **MESSAGE CONTENT INTENT** (required
   for prefix commands like `!buy`).
4. **OAuth2 → URL Generator** →
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Send Messages`, `Embed Links`, `Read Message History`,
     `Use Slash Commands`
   - Copy the generated URL, open it in a browser, and invite the bot to your
     server.

---

## 2. Get your tiger-sms API key

1. Sign up / log in at <https://tiger-sms.com>.
2. Top up your balance (numbers cost a few RUB each).
3. Profile page → copy your **API key** — this is `TIGER_SMS_API_KEY`.

---

## 3. Clone & configure

```bash
git clone <your-fork-url> tiger-sms-bot
cd tiger-sms-bot
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```ini
MONGO_URL="mongodb://localhost:27017"
DB_NAME="tiger_sms_bot"
CORS_ORIGINS="*"

DISCORD_BOT_TOKEN="paste-your-bot-token-here"
TIGER_SMS_API_KEY="paste-your-tiger-sms-key-here"

DISCORD_COMMAND_PREFIX="!"
DEFAULT_COUNTRY="33"           # 33 = Colombia, 187 = USA, 22 = India, 6 = Indonesia …
POLL_INTERVAL_SECONDS="15"
POLL_TIMEOUT_SECONDS="1200"    # 1200 s = 20 min
```

> **Never commit `.env`** — it is already in `.gitignore`. Discord's secret
> scanner auto-invalidates any bot token it finds in a public GitHub repo.

---

## 4. Install & run

### Backend + bot

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

On start-up you should see:

```
Starting Discord bot task...
logging in using static token
Synced 7 slash command(s)
Bot ready as <your-bot-name> (id=…)
```

### Frontend dashboard (optional)

```bash
cd frontend
cp .env.example .env             # set REACT_APP_BACKEND_URL if different
yarn install
yarn start
```

Dashboard is now on `http://localhost:3000` and polls `/api/bot/status` every
5 s to show the bot state and recent orders.

---

## 5. Use it in Discord

```
/tigerhelp                         → see all commands
/services                          → list popular service codes
/countries                         → list popular country IDs
/balance                           → your current RUB balance
/buy service:tg                    → buy a Telegram number in the default country
/buy service:go country:187        → buy a Google number in the USA
/status activation_id:99999...     → poll status manually
/cancel activation_id:99999...     → release number & refund balance
```

After `/buy`, the embed shows the phone, activation ID, and two buttons:

- **🔑 Copy Code** — replies ephemerally with the raw SMS code once it arrives
- **🆔 Copy Activation ID** — replies ephemerally with the raw activation ID

The bot automatically calls `setStatus=6` to mark the activation complete when
the code arrives, and `setStatus=8` to cancel when you hit `/cancel`.

---

## 6. Deploy

The easiest path is any Python host that can keep a long-lived process alive
(Railway, Fly.io, a VPS, or this Emergent template). The process just needs:

- `MONGO_URL` pointing at a reachable MongoDB
- The two env vars above
- Outbound HTTPS access to `discord.com` and `api.tiger-sms.com`

On Emergent, the bot is started as an asyncio task inside the FastAPI
`lifespan` hook in `server.py`, so the default supervisor-managed `backend`
service keeps it running.

---

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `LoginFailure: Improper token has been passed.` | Reset the bot token in the Discord Developer Portal, paste it into `.env`, restart backend. Usually caused by a token being leaked on GitHub. |
| Slash commands don't appear | Re-invite the bot with the `applications.commands` scope; global sync can take up to 1 hour on first publish. |
| `NO_BALANCE` from tiger-sms | Top up at <https://tiger-sms.com>. |
| `NO_NUMBERS` from tiger-sms | That `service` × `country` combination is temporarily out of stock. Try a different country (`/countries`) or service (`/services`). |
| `Too Many Requests (429)` | You hit tiger-sms' per-key rate limit; increase `POLL_INTERVAL_SECONDS`. |
| Bot prefix commands ignored | Enable **MESSAGE CONTENT INTENT** in the Developer Portal and restart. |

---

## License

MIT — do what you want, just don't use it to spam.
