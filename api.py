import os
from fastapi import FastAPI, Request
from redis import Redis
from rq import Queue
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
    data = await request.json()
    
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]
        
        if "youtube.com" in text or "youtu.be" in text:
            requests.post(TELEGRAM_API_URL, json={
                "chat_id": chat_id,
                "text": f"✅ Link received! Analysis process starting...\nLink: {text}"
            })
            
            job = q.enqueue('worker.process_video', text)
            return {"status": "Queued"}
            
    return {"status": "Ignored"}
