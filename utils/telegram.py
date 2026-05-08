import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

logger = logging.getLogger(__name__)

def _send_request(endpoint: str, payload: dict) -> dict | None:
    """Helper to send POST requests to Telegram with standard error handling and fallback."""
    url = f"{API_URL}/{endpoint}"
    target_id = payload.get("chat_id") or payload.get("callback_query_id", "unknown")
    
    with httpx.Client(timeout=10.0) as client:
        try:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"[TELEGRAM] {endpoint} successful for target={target_id}")
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "parse_mode" in payload:
                logger.warning(f"[TELEGRAM] Formatting error on {endpoint} for target={target_id}, retrying without parse_mode...")
                del payload["parse_mode"]
                try:
                    resp_fallback = client.post(url, json=payload)
                    resp_fallback.raise_for_status()
                    logger.info(f"[TELEGRAM] {endpoint} successful for target={target_id} (Fallback Plain Text)")
                    return resp_fallback.json()
                except Exception as fallback_err:
                    logger.error(f"[TELEGRAM] Fallback failed on {endpoint} for target={target_id}: {fallback_err}")
                    return None
            else:
                logger.error(f"[TELEGRAM] HTTP error on {endpoint} for target={target_id}: {e.response.text}")
                return None
        except Exception as e:
            logger.error(f"[TELEGRAM] Request failed on {endpoint} for target={target_id}: {e}")
            return None

def send_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> dict | None:
    """
    Send a plain text message to a Telegram chat.
    If parse_mode fails (usually due to AI-generated markdown breaking Telegram parsers),
    it automatically falls back to plain text.
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _send_request("sendMessage", payload)

def send_inline_keyboard(chat_id: int, text: str, buttons: list, parse_mode: str = "Markdown") -> dict | None:
    """
    Send a message with an inline keyboard.
    'buttons' should be a list of lists (rows) of button dicts.
    Example: [[{"text": "Yes", "callback_data": "y"}, {"text": "No", "callback_data": "n"}]]
    If parse_mode fails (usually due to AI-generated markdown breaking Telegram parsers),
    it automatically falls back to plain text.
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": buttons
        }
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _send_request("sendMessage", payload)

def edit_message_text(chat_id: int, message_id: int, text: str, parse_mode: str = "Markdown") -> dict | None:
    """
    Edit an existing message (e.g., to replace inline buttons with confirmation text).
    If parse_mode fails, falls back to plain text.
    """
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _send_request("editMessageText", payload)

def answer_callback_query(callback_query_id: str, text: str = "⏳ Processing...") -> dict | None:
    """
    Acknowledge a callback query to remove the loading spinner on the button.
    """
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return _send_request("answerCallbackQuery", payload)
