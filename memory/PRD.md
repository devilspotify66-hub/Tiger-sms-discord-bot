# Tiger-SMS Discord Bot — PRD

## Original problem statement
> I want to make a discord bot which buys numbers from tiger-sms.com through the api key and send the code it receives.

## Architecture
- **Bot runtime**: `discord.py==2.4.0`, hybrid commands (slash + `!` prefix)
- **SMS API client**: custom async `httpx` wrapper on `https://api.tiger-sms.com/stubs/handler_api.php`
- **Host**: Python bot is started as an asyncio task inside the FastAPI `lifespan` (supervised under the `backend` supervisor service)
- **Persistence**: MongoDB (`tiger_orders` collection) stores activation history
- **Tiny web dashboard**: React page polls `/api/bot/status` and shows live status + recent orders

## Files
- `backend/tiger_sms.py` — async tiger-sms HTTP client (getBalance/getNumber/getStatus/setStatus)
- `backend/tiger_data.py` — popular services & countries lookup
- `backend/bot.py` — Discord bot + all commands + background SMS polling
- `backend/server.py` — FastAPI + lifespan bot launcher + `/api/bot/status`
- `frontend/src/App.js` + `App.css` — status dashboard
- `backend/.env` — `DISCORD_BOT_TOKEN`, `TIGER_SMS_API_KEY`, `DEFAULT_COUNTRY=33` (Colombia), `POLL_INTERVAL_SECONDS=15`, `POLL_TIMEOUT_SECONDS=1200`

## Commands implemented (slash + prefix)
- `/buy service [country]` — purchase number, post phone, poll every 15s (up to 20 min), post code
- `/status <activation_id>` — query current status
- `/cancel <activation_id>` — cancel + refund (setStatus=8)
- `/balance` — account balance
- `/services` — popular service codes
- `/countries` — popular country IDs
- `/tigerhelp` — inline help

## Verified (2026-02-21)
- Discord login OK (`CodeX#2012`), 7 commands synced
- tiger-sms key valid — live balance 21.04 RUB
- `/api/bot/status` returns `bot_running: true`
- Frontend dashboard renders correctly

## Backlog / ideas
- P1: `/prices service country` command using `getPrices`
- P1: Per-order ephemeral DM option (currently channel-only per user request)
- P2: Allow admin-only restriction (role check)
- P2: Persist and resume in-flight polling across bot restarts
