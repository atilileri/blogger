import os
import uuid
import logging
import json
from unittest.mock import patch
from langchain_core.messages import AIMessage
import fakeredis

# Set up environment for simulator
os.environ["CHECKPOINT_DB"] = "checkpoints_sim.sqlite"
os.environ["ALLOWED_CHAT_IDS"] = "12345"
os.environ["GOOGLE_API_KEY"] = "test_key"

# Mock Redis
server = fakeredis.FakeServer()
fake_redis = fakeredis.FakeStrictRedis(server=server)

# Mock LLM side effect (Improved to match conftest.py)
def llm_side_effect(messages, **kwargs):
    if isinstance(messages, list):
        system_msg = str(messages[0].content).lower()
        human_msg = str(messages[-1].content).lower()
    else:
        system_msg = ""
        human_msg = str(messages).lower()

    if "extract structured references" in system_msg:
        return AIMessage(content="1. Concept: Agentic AI\n2. Quote: 'The future is agentic.'\n3. Topic: Autonomous workflows")
    
    if "search query" in human_msg:
        return AIMessage(content="Agentic AI frameworks 2026")
    
    if "diverse blog storylines" in system_msg or "storyline" in human_msg:
        if "expert blogger" in system_msg: # This is the full post step
            blog_data = {
                "title": "The Future of Agentic AI",
                "description": "Exploration of autonomous agents.",
                "tags": ["AI", "Agents"],
                "content": "Full blog post content in English.",
                "image_description": "A futuristic lab with AI agents."
            }
            return AIMessage(content=json.dumps(blog_data))
        return AIMessage(content="Storyline 1: The Rise of Agents - Summary 1 ---\nStoryline 2: Engineering Autonomy - Summary 2 ---\nStoryline 3: Scalable Intelligence - Summary 3")

    if "expert translator" in system_msg:
        blog_data = {
            "title": "Ajanli Yapay Zekanin Gelecegi",
            "description": "Otonom ajanlarin kesfi.",
            "tags": ["YZ", "Ajanlar"],
            "content": "Turkce tam blog yazisi icerigi."
        }
        return AIMessage(content=json.dumps(blog_data))

    if "visual prompt" in human_msg or "pollinations" in human_msg:
        return AIMessage(content="A futuristic lab with AI agents collaborating on complex tasks, 4k, digital art.")

    return AIMessage(content="Simulated LLM response for: " + human_msg[:50])

def mock_telegram_send(chat_id, text, **kwargs):
    # Sanitize for console
    clean_text = text.encode('ascii', 'ignore').decode('ascii')
    print(f"\n[TELEGRAM] BOT: {clean_text}")

def mock_telegram_kb(chat_id, text, buttons, **kwargs):
    clean_text = text.encode('ascii', 'ignore').decode('ascii')
    print(f"\n[TELEGRAM] BOT (KEYBOARD): {clean_text}")
    options = []
    for row in buttons:
        for btn in row:
            options.append(btn)
            btn_text = btn['text'].encode('ascii', 'ignore').decode('ascii')
            print(f"  [{len(options)-1}] {btn_text}")
    return options

def start_simulator():
    print("Starting Blogger AI Simulator")
    print("--------------------------------")
    
    # Use the correct yt_dlp path if we were actually using it, 
    # but since we don't yet, we can skip or fix it.
    # Fixed path: "yt_dlp.YoutubeDL.YoutubeDL.extract_info"
    
    with patch("utils.redis_utils.redis_conn", fake_redis), \
         patch("utils.telegram.send_message", side_effect=mock_telegram_send), \
         patch("utils.telegram.send_inline_keyboard", side_effect=mock_telegram_kb), \
         patch("utils.telegram.edit_message_text", side_effect=mock_telegram_send), \
         patch("utils.telegram.answer_callback_query"), \
         patch("langchain_google_genai.ChatGoogleGenerativeAI.invoke", side_effect=llm_side_effect):
        
        # Import worker functions inside patch context
        from worker import run_pipeline, resume_pipeline, resume_with_text
        from utils.redis_utils import get_lock_key, acquire_lock
        
        chat_id = 12345
        url = input("Enter a YouTube URL to start: ") or "https://youtube.com/watch?v=sim"
        
        # Simulate api.py lock
        acquire_lock(chat_id)
        
        # 1. Start
        run_pipeline({"chat": {"id": chat_id}, "text": url})
        
        # Simple loop to simulate interactions
        while True:
            if not fake_redis.exists(get_lock_key(chat_id)):
                print("\n--- Pipeline Finished! ---")
                break

            print("\n--- Pipeline Paused (HitL) ---")
            action = input("Choose: [a]pprove, [r]evise, [c]ancel, [0-2] for story index, or [q]uit: ").lower()
            
            if action == 'q':
                break
            elif action == 'a':
                resume_pipeline({"message": {"chat": {"id": chat_id}, "message_id": 1}, "data": "approve"})
            elif action == 'c':
                resume_pipeline({"message": {"chat": {"id": chat_id}, "message_id": 1}, "data": "cancel"})
                break
            elif action == 'r':
                rev_text = input("Enter revision text: ")
                resume_with_text({"chat": {"id": chat_id}, "text": rev_text})
            elif action.isdigit():
                resume_pipeline({"message": {"chat": {"id": chat_id}, "message_id": 1}, "data": action})
            else:
                print("Invalid input.")

if __name__ == "__main__":
    # Clean old checkpoints
    if os.path.exists("checkpoints_sim.sqlite"):
        os.remove("checkpoints_sim.sqlite")
        
    try:
        start_simulator()
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
