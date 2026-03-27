from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="TeleBot Admin API")

# Store the client globally (for a single-user system)
client = TelegramClient('admin_session', int(os.getenv('API_ID')), os.getenv('API_HASH'))

# Dictionary to temporarily store the phone hash between sending code and logging in
auth_state = {}

class TransferRequest(BaseModel):
    source_group: str
    target_group: str
    delay_seconds: int = 60

class SendCodeRequest(BaseModel):
    phone_number: str

class LoginRequest(BaseModel):
    phone_number: str
    code: str

@app.on_event("startup")
async def startup_event():
    # Connect to Telegram on server start
    await client.connect()
    if not await client.is_user_authorized():
        print("User is not authorized. Please use /api/auth/send-code to login.")

@app.post("/api/auth/send-code")
async def send_code(req: SendCodeRequest):
    """Request a login code to be sent to the phone number"""
    try:
        if not await client.is_connected():
            await client.connect()
            
        # Send the code
        result = await client.send_code_request(req.phone_number)
        
        # We need to save the phone_code_hash to complete the login later
        auth_state[req.phone_number] = result.phone_code_hash
        
        return {"message": "Code sent successfully", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Complete the login process by submitting the code"""
    try:
        if req.phone_number not in auth_state:
            raise HTTPException(status_code=400, detail="Please call /api/auth/send-code first")
            
        phone_code_hash = auth_state[req.phone_number]
        
        # Sign in
        await client.sign_in(
            phone=req.phone_number,
            code=req.code,
            phone_code_hash=phone_code_hash
        )
        
        # Clear state after successful login
        del auth_state[req.phone_number]
        
        return {"message": "Login successful", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/groups")
async def get_groups():
    """Fetch all groups the user is an admin/member of"""
    if not await client.is_user_authorized():
        raise HTTPException(status_code=401, detail="Unauthorized. Please login first.")
        
    dialogs = await client.get_dialogs()
    groups = [{"id": d.id, "name": d.name} for d in dialogs if d.is_group or d.is_channel]
    return {"groups": groups}

@app.post("/api/transfer")
async def start_transfer(req: TransferRequest, background_tasks: BackgroundTasks):
    """Starts the scraping and adding process in the background"""
    if not await client.is_user_authorized():
        raise HTTPException(status_code=401, detail="Unauthorized. Please login first.")
        
    # We pass the heavy lifting to a background task so the API responds instantly
    background_tasks.add_task(run_transfer_engine, req.source_group, req.target_group, req.delay_seconds)
    
    return {"message": "Transfer engine started in the background", "status": "running"}

async def run_transfer_engine(source: str, target: str, delay: int):
    """The background engine that scrapes and adds (similar to our previous script)"""
    # 1. Scrape to DB
    # 2. Loop through DB and Add
    # 3. Apply `delay`
    pass
