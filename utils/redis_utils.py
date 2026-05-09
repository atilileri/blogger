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

def acquire_lock(chat_id: int, ttl: int = 3600) -> bool:
    """
    Attempts to acquire a lock for the given chat_id.
    Returns True if successful, False if already locked.
    """
    lock_key = get_lock_key(chat_id)
    # nx=True means only set if it doesn't exist
    return bool(redis_conn.set(lock_key, "active", ex=ttl, nx=True))

def release_lock(chat_id: int):
    """Deletes the active session lock for the given chat_id if it exists."""
    lock_key = get_lock_key(chat_id)
    redis_conn.delete(lock_key)
