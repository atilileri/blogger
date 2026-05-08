import os
from redis import Redis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Shared Redis connection for utilities
redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT)

def get_lock_key(chat_id: int) -> str:
    """Returns the Redis key used to lock a chat session."""
    return f"pipeline_active_{chat_id}"

def release_lock(chat_id: int):
    """Deletes the active session lock for the given chat_id if it exists."""
    lock_key = get_lock_key(chat_id)
    if redis_conn.exists(lock_key):
        redis_conn.delete(lock_key)
