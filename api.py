"""
FastAPI server for the Blogger pipeline.
Receives Telegram webhooks, validates YouTube links, and enqueues tasks to Redis.
"""
import logging
import os
from fastapi import FastAPI, Request
from redis import Redis
from rq import Queue
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Get settings from environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT)
q = Queue('video_tasks', connection=redis_conn)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"Received payload: {data}")

        # Check if it's a standard text message
        if "message" in data and "text" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"]["text"]

            # todo : message can contain more than one url. also some other texts as well.
            # intelligent extraction will be required. maybe some agent can do it.
            # It might be better to send message as it is to the worker and make it do the heavy lifting.
            # here API should just be a relay, and let the worker do all the logic.

            # todo : there will be all kinds of messages, not only youtube in the future.
            # Send link received here. and do validations after. Send validation results as well.

            # Simple validation for YouTube links (todo - move to worker as well)
            if "youtube.com" in text or "youtu.be" in text:

                # Send immediate feedback to user
                requests.post(TELEGRAM_API_URL, json={
                    "chat_id": chat_id,
                    "text": f"✅ Link received! Analysis process starting...\nLink: {text}"
                })

                # Enqueue the task for LXC 3 (Worker)
                job = q.enqueue('worker.process_video', text, chat_id) # todo : not process video, but process message
                logger.info(f"Job successfully enqueued with ID: {job.id}")

                return {"status": "Queued", "job_id": job.id}

        return {"status": "Ignored", "reason": "Not a valid youtube link or text message"} # todo : we should not decide and just relay whatever comes from worker

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}
