import logging
from utils.state import PipelineState

logger = logging.getLogger(__name__)

def intake_node(state: PipelineState):
    """
    Parses the incoming Telegram message to extract URLs and intent.
    Uses Telegram 'entities' for robust URL detection.
    """
    message = state.get("raw_message", {})
    text = message.get("text", "")
    entities = message.get("entities", [])
    
    youtube_urls = []
    website_urls = []
    
    # Extract URLs using entities (handles both plain text URLs and hidden links)
    found_urls = []
    for ent in entities:
        if ent["type"] == "url":
            offset = ent["offset"]
            length = ent["length"]
            found_urls.append(text[offset:offset+length])
        elif ent["type"] == "text_link":
            found_urls.append(ent["url"])

    for url in found_urls:
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            youtube_urls.append(url)
        else:
            website_urls.append(url)

    # Clean duplicates
    youtube_urls = list(set(youtube_urls))
    website_urls = list(set(website_urls))

    # User intent is the remaining text if any, or just the first line
    # For now, we'll store the full text as intent to pass to LLM later
    user_intent = text.strip()

    logger.info(f"[INTAKE] Found {len(youtube_urls)} YT, {len(website_urls)} Web URLs for {state['chat_id']}")

    return {
        "youtube_urls": youtube_urls,
        "website_urls": website_urls,
        "user_intent": user_intent,
        "status": "intake_completed"
    }
