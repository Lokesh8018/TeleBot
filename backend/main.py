from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="TeleBot Admin API")

# Store the client globally (for a single-user system)
# For multi-account (Future Enhancement), this would be a dictionary of clients
client = TelegramClient('admin_session', int(os.getenv('API_ID')), os.getenv('API_HASH'))

class TransferRequest(BaseModel):
    source_group: str
    target_group: str
    delay_seconds: int = 60

@app.on_event("startup")
async def startup_event():
    # Connect to Telegram on server start
    await client.connect()
    if not await client.is_user_authorized():
        print("User is not authorized. Need to implement /api/auth endpoint.")

@app.get("/api/groups")
async def get_groups():
    """Fetch all groups the user is an admin/member of"""
    dialogs = await client.get_dialogs()
    groups = [{"id": d.id, "name": d.name} for d in dialogs if d.is_group or d.is_channel]
    return {"groups": groups}

@app.post("/api/transfer")
async def start_transfer(req: TransferRequest, background_tasks: BackgroundTasks):
    """Starts the scraping and adding process in the background"""

    # We pass the heavy lifting to a background task so the API responds instantly
    background_tasks.add_task(run_transfer_engine, req.source_group, req.target_group, req.delay_seconds)

    return {"message": "Transfer engine started in the background", "status": "running"}

async def run_transfer_engine(source: str, target: str, delay: int):
    """The background engine that scrapes and adds (similar to our previous script)"""
    # 1. Scrape to DB
    # 2. Loop through DB and Add
    # 3. Apply `delay`
    pass
