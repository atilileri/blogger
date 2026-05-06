import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

logger = logging.getLogger(__name__)

def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    """
    Send a plain text message to a Telegram chat.
    If parse_mode fails (usually due to AI-generated markdown breaking Telegram parsers),
    it automatically falls back to plain text.
    """
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    with httpx.Client() as client:
        try:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"[TELEGRAM] Sent message to {chat_id}")
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "parse_mode" in payload:
                logger.warning(f"[TELEGRAM] Formatting error for {chat_id}, retrying without parse_mode...")
                del payload["parse_mode"]
                try:
                    resp_fallback = client.post(url, json=payload)
                    resp_fallback.raise_for_status()
                    logger.info(f"[TELEGRAM] Sent message to {chat_id} (Fallback Plain Text)")
                    return resp_fallback.json()
                except Exception as fallback_err:
                    logger.error(f"[TELEGRAM] Fallback failed: {fallback_err}")
                    return None
            else:
                logger.error(f"[TELEGRAM] HTTP error sending message: {e}")
                return None
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send message to {chat_id}: {e}")
            return None

def send_inline_keyboard(chat_id: int, text: str, buttons: list, parse_mode: str = "Markdown"):
    """
    Send a message with an inline keyboard.
    'buttons' should be a list of lists (rows) of button dicts.
    Example: [[{"text": "Yes", "callback_data": "y"}, {"text": "No", "callback_data": "n"}]]
    If parse_mode fails (usually due to AI-generated markdown breaking Telegram parsers),
    it automatically falls back to plain text.
    """
    url = f"{API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": buttons
        }
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    with httpx.Client() as client:
        try:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"[TELEGRAM] Sent inline keyboard to {chat_id}")
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "parse_mode" in payload:
                logger.warning(f"[TELEGRAM] Formatting error for {chat_id}, retrying without parse_mode...")
                del payload["parse_mode"]
                try:
                    resp_fallback = client.post(url, json=payload)
                    resp_fallback.raise_for_status()
                    logger.info(f"[TELEGRAM] Sent inline keyboard to {chat_id} (Fallback Plain Text)")
                    return resp_fallback.json()
                except Exception as fallback_err:
                    logger.error(f"[TELEGRAM] Fallback failed: {fallback_err}")
                    return None
            else:
                logger.error(f"[TELEGRAM] HTTP error sending inline keyboard: {e}")
                return None
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to send inline keyboard to {chat_id}: {e}")
            return None

def answer_callback_query(callback_query_id: str, text: str = None):
    """
    Acknowledge a callback query to remove the loading spinner on the button.
    """
    url = f"{API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    with httpx.Client() as client:
        try:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"[TELEGRAM] Answered callback query {callback_query_id}")
            return resp.json()
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed to answer callback query: {e}")
            return None
