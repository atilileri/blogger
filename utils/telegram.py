import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

logger = logging.getLogger(__name__)

async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    """
    Send a plain text message to a Telegram chat.
    """
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"[TELEGRAM] Sent message to {chat_id}")
            return resp.json()
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send message to {chat_id}: {e}")
            return None

async def send_inline_keyboard(chat_id: int, text: str, buttons: list):
    """
    Send a message with an inline keyboard.
    'buttons' should be a list of lists (rows) of button dicts.
    Example: [[{"text": "Yes", "callback_data": "y"}, {"text": "No", "callback_data": "n"}]]
    """
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": buttons
        },
        "parse_mode": "Markdown"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"[TELEGRAM] Sent inline keyboard to {chat_id}")
            return resp.json()
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send inline keyboard to {chat_id}: {e}")
            return None

async def answer_callback_query(callback_query_id: str, text: str = None):
    """
    Acknowledge a callback query to remove the loading spinner on the button.
    """
    url = f"{API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"[TELEGRAM] Answered callback query {callback_query_id}")
            return resp.json()
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to answer callback query: {e}")
            return None
