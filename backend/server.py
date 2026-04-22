print("🔥 FILE STARTED")
from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
import os
import asyncio
import logging
from pathlib import Path

from bot import run_bot


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

_bot_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bot_task
    token = os.environ.get('DISCORD_BOT_TOKEN')
    api_key = os.environ.get('TIGER_SMS_API_KEY')
    if token and api_key:
        logger.info("Starting Discord bot task...")
        _bot_task = asyncio.create_task(run_bot(db))
    else:
        logger.warning("DISCORD_BOT_TOKEN or TIGER_SMS_API_KEY missing — bot not started.")
    try:
        yield
    finally:
        if _bot_task and not _bot_task.done():
            _bot_task.cancel()
            try:
                await _bot_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        client.close()


app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "Tiger-SMS Discord bot backend"}


@api_router.get("/bot/status")
async def bot_status():
    running = bool(_bot_task and not _bot_task.done())
    last_orders = await db.tiger_orders.find({}, {"_id": 0}).sort("created_at", -1).to_list(10)
    return {
        "bot_running": running,
        "recent_orders": last_orders,
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
