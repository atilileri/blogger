from utils.redis_utils import acquire_lock
import os
import logging
import asyncio
from datetime import timedelta
from typing import List

from fastapi import FastAPI, Request
from redis import Redis
from rq import Queue
from dotenv import load_dotenv
import httpx

from utils.telegram import send_message
from utils.redis_utils import get_lock_key

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Blogger API Gateway")

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
ALLOWED_CHAT_IDS_STR = os.getenv("ALLOWED_CHAT_IDS", "")
ALLOWED_CHAT_IDS = [int(i.strip()) for i in ALLOWED_CHAT_IDS_STR.split(",") if i.strip()]

# Redis & RQ
redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT)
q = Queue("blogger_tasks", connection=redis_conn)

def is_allowed(chat_id: int) -> bool:
    return chat_id in ALLOWED_CHAT_IDS

def check_session_timeout(chat_id: int):
    """
    RQ Job: Checks if a session lock still exists after 24h.
    If it does, notifies user and clears it.
    This function is enqueued via q.enqueue_in.
    """
    lock_key = get_lock_key(chat_id)
    if redis_conn.exists(lock_key):
        redis_conn.delete(lock_key)
        logger.info(f"[TIMEOUT] Session expired for chat_id={chat_id}")
        
        try:
            send_message(chat_id, "⚠️ Session expired due to 1h timeout. State cleared.")
        except Exception as e:
            logger.error(f"[TIMEOUT] Failed to notify {chat_id}: {e}")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    
    # 1. Callback Query Handling
    if "callback_query" in payload:
        cq = payload["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        
        if not is_allowed(chat_id):
            logger.warning(f"[AUTH] Unauthorized callback from {chat_id}")
            return {"status": "rejected"}
            
        logger.info(f"[CALLBACK] chat_id={chat_id} data={cq.get('data')}")
        q.enqueue("worker.resume_pipeline", cq, on_failure="worker.handle_system_failure")
        return {"status": "callback_queued"}

    # 2. Message Handling
    if "message" in payload:
        msg = payload["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        if not is_allowed(chat_id):
            logger.warning(f"[AUTH] Unauthorized message from {chat_id}")
            # Optional: send a one-time rejection if not already enqueued
            # await send_message(chat_id, "🚫 You are not authorized to use this bot.")
            return {"status": "rejected"}

        logger.info(f"[MESSAGE] chat_id={chat_id} text={text[:50]}...")

        # Command: /cancel or /reset
        if text.startswith(("/cancel", "/reset")):
            redis_conn.delete(get_lock_key(chat_id))
            redis_conn.delete(f"thread_{chat_id}")
            logger.info(f"[LOCK] Manual reset for {chat_id}")
            await asyncio.to_thread(send_message, chat_id, "🔓 Session reset. You can start a new request.")
            return {"status": "reset"}

        # Command: /state
        if text.startswith("/state"):
            logger.info(f"[STATE] Querying state for {chat_id}")
            q.enqueue("worker.send_pipeline_state", chat_id)
            return {"status": "state_queued"}

        # Command: /help
        if text.startswith("/help"):
            help_text = (
                "🤖 **Blogger AI Bot Help**\n\n"
                "Simply send a YouTube or Website URL to start a new blog post pipeline.\n\n"
                "**Commands:**\n"
                "• /cancel - Reset your session and unlock the bot\n"
                "• /state - Check the detailed status of your current pipeline\n"
                "• /help - Show this message"
            )
            await asyncio.to_thread(send_message, chat_id, help_text)
            return {"status": "help_sent"}

        # Start New Session
        if not acquire_lock(chat_id):
            # If it's a text message (not a command), it might be a "revise" input
            if text and not text.startswith("/"):
                logger.info(f"[REVISE] Forwarding text for {chat_id}")
                q.enqueue("worker.resume_with_text", msg, on_failure="worker.handle_system_failure")
                return {"status": "revise_queued"}

            logger.info(f"[LOCK] Busy for {chat_id}")
            await asyncio.to_thread(send_message, chat_id, "⏳ Bot is busy processing your previous request. Use /cancel to reset if stuck.")
            return {"status": "locked"}

        logger.info(f"[LOCK] New session started for {chat_id}")
        
        # Schedule Timeout Job
        q.enqueue_in(timedelta(hours=1), check_session_timeout, chat_id)
        
        # Relay to Worker
        q.enqueue("worker.run_pipeline", msg, on_failure="worker.handle_system_failure")
        await asyncio.to_thread(send_message, chat_id, "✅ Request received! Analyzing and starting the pipeline...")
        return {"status": "queued"}

    return {"status": "ignored"}

@app.get("/health")
async def health():
    try:
        redis_conn.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as e:
        return {"status": "error", "redis": str(e)}
