import os
import sys
import asyncio
import aiomysql
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.errors.rpcerrorlist import PeerFloodError, UserPrivacyRestrictedError
from datetime import datetime

# Load environment variables
load_dotenv()

# Delay between adding members to avoid Telegram rate limits / bans
ADD_MEMBER_DELAY_SECONDS = 60

# --- Configuration ---
# Telegram Credentials
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')

SOURCE_GROUP = os.getenv('SOURCE_GROUP')
TARGET_GROUP = os.getenv('TARGET_GROUP')

# AWS MySQL Credentials
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

# Validate that all required environment variables are present
_required_vars = {
    'API_ID': API_ID, 'API_HASH': API_HASH, 'PHONE_NUMBER': PHONE_NUMBER,
    'SOURCE_GROUP': SOURCE_GROUP, 'TARGET_GROUP': TARGET_GROUP,
    'DB_HOST': DB_HOST, 'DB_USER': DB_USER, 'DB_PASSWORD': DB_PASSWORD, 'DB_NAME': DB_NAME,
}
_missing = [name for name, value in _required_vars.items() if not value]
if _missing:
    print(f"Error: Missing required environment variables: {', '.join(_missing)}")
    print("Copy .env.example to .env and fill in the required values.")
    sys.exit(1)

# API_ID must be an integer for Telethon
API_ID = int(API_ID)

client = TelegramClient('session_name', API_ID, API_HASH)

async def connect_db():
    """Establish connection to AWS MySQL.

    Expected table schema:
        CREATE TABLE IF NOT EXISTS scraped_users (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username    VARCHAR(255),
            status      ENUM('pending', 'added', 'failed_privacy', 'failed_flood') DEFAULT 'pending',
            added_at    TIMESTAMP NULL DEFAULT NULL
        );
    """
    return await aiomysql.create_pool(
        host=DB_HOST, port=3306,
        user=DB_USER, password=DB_PASSWORD,
        db=DB_NAME, autocommit=True
    )

async def scrape_and_save(db_pool):
    """Scrape users from source group and save to DB"""
    print(f"Scraping members from {SOURCE_GROUP}...")
    participants = await client.get_participants(SOURCE_GROUP)
    
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            count = 0
            for user in participants:
                if user.username and not user.bot:
                    try:
                        await cur.execute(
                            "INSERT IGNORE INTO scraped_users (telegram_id, username) VALUES (%s, %s)",
                            (user.id, user.username)
                        )
                        if cur.rowcount > 0:
                            count += 1
                    except Exception as e:
                        print(f"DB Error: {e}")
            print(f"Saved {count} NEW users to the database.")

async def add_members_from_db(db_pool):
    """Fetch pending users from DB and add them to target group"""
    async with db_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM scraped_users WHERE status = 'pending'")
            pending_users = await cur.fetchall()
            
            print(f"Found {len(pending_users)} pending users in the database to add.")

            for db_user in pending_users:
                try:
                    print(f"Attempting to add @{db_user['username']}...")
                    
                    await client(InviteToChannelRequest(
                        TARGET_GROUP,
                        [db_user['username']]
                    ))
                    
                    await cur.execute(
                        "UPDATE scraped_users SET status = 'added', added_at = %s WHERE telegram_id = %s",
                        (datetime.now(), db_user['telegram_id'])
                    )
                    print(f"Successfully added @{db_user['username']}")
                    
                    # Wait to avoid Telegram rate limits / bans
                    await asyncio.sleep(ADD_MEMBER_DELAY_SECONDS)
                    
                except PeerFloodError:
                    print("Telegram Flood Error! You are rate-limited. Stopping script.")
                    await cur.execute(
                        "UPDATE scraped_users SET status = 'failed_flood' WHERE telegram_id = %s",
                        (db_user['telegram_id'],)
                    )
                    break 
                    
                except UserPrivacyRestrictedError:
                    print(f"User @{db_user['username']} has strict privacy settings. Skipping.")
                    await cur.execute(
                        "UPDATE scraped_users SET status = 'failed_privacy' WHERE telegram_id = %s",
                        (db_user['telegram_id'],)
                    )
                    
                except Exception as e:
                    print(f"Unexpected error for @{db_user['username']}: {e}")
                    await asyncio.sleep(5)

async def main():
    await client.start(phone=PHONE_NUMBER)
    print("Telegram Client Connected.")

    print("Connecting to AWS MySQL...")
    db_pool = await connect_db()
    try:
        await scrape_and_save(db_pool)
        await add_members_from_db(db_pool)
    finally:
        db_pool.close()
        await db_pool.wait_closed()

if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())
