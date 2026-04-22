import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

from bot import run_bot


async def main():
    print("🔥 SERVER STARTED")

    # Get Mongo URI
    mongo_uri = os.environ.get("MONGODB_URI")
    if not mongo_uri:
        raise RuntimeError("❌ MONGODB_URI not set")

    print("🔌 Connecting to MongoDB...")

    # Connect to Mongo
    client = AsyncIOMotorClient(mongo_uri)

    # ⚠️ IMPORTANT: explicitly select DB (your URI has none)
    db = client["tigerbot"]

    print("🚀 Starting bot...")

    # Run bot
    await run_bot(db)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ FATAL ERROR: {e}")
