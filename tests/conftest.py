import pytest
import os
import json
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
import fakeredis

# --- GLOBAL PATCHING ---
server = fakeredis.FakeServer()
fake_redis = fakeredis.FakeStrictRedis(server=server)
redis_patcher = patch("utils.redis_utils.redis_conn", fake_redis)
redis_patcher.start()

def side_effect_send(chat_id, text, **kwargs):
    # Sanitize for console (remove non-ascii)
    clean_text = text.encode('ascii', 'ignore').decode('ascii')
    print(f"\n[TELEGRAM OUT] Chat {chat_id}: {clean_text}")
    return {"message_id": 1}

def side_effect_kb(chat_id, text, buttons, **kwargs):
    clean_text = text.encode('ascii', 'ignore').decode('ascii')
    print(f"\n[TELEGRAM OUT] Chat {chat_id} (Keyboard): {clean_text}")
    for row in buttons:
        for btn in row:
            btn_text = btn['text'].encode('ascii', 'ignore').decode('ascii')
            print(f"  [{btn_text}] -> {btn['callback_data']}")
    return {"message_id": 1}

tg_send_patcher = patch("utils.telegram.send_message", side_effect=side_effect_send)
tg_kb_patcher = patch("utils.telegram.send_inline_keyboard", side_effect=side_effect_kb)
tg_edit_patcher = patch("utils.telegram.edit_message_text", side_effect=side_effect_send)
tg_answer_patcher = patch("utils.telegram.answer_callback_query")

tg_send_patcher.start()
tg_kb_patcher.start()
tg_edit_patcher.start()
tg_answer_patcher.start()

@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Set up environment variables for testing."""
    monkeypatch.setenv("CHECKPOINT_DB", "test_checkpoints.db")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "12345")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("GOOGLE_API_KEY", "test_key")

@pytest.fixture(autouse=True)
def cleanup_db():
    db_file = "test_checkpoints.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    yield
    if os.path.exists(db_file):
        os.remove(db_file)

@pytest.fixture
def mock_redis():
    return fake_redis

@pytest.fixture
def mock_telegram():
    return {
        "send": tg_send_patcher.target,
        "patch_send": tg_send_patcher
    }

@pytest.fixture
def mock_llm():
    """Mock LangChain LLM invocations."""
    with patch("langchain_google_genai.ChatGoogleGenerativeAI.invoke") as mock_invoke:
        def side_effect(messages, **kwargs):
            # Extract content from messages
            if isinstance(messages, list):
                system_msg = str(messages[0].content).lower()
                human_msg = str(messages[-1].content).lower()
            else:
                system_msg = ""
                human_msg = str(messages).lower()

            # More specific checks first!
            
            if "expert blogger" in system_msg or "write a full" in human_msg:
                blog_data = {
                    "title": "The Future of Agentic AI",
                    "description": "Exploration of autonomous agents.",
                    "tags": ["AI", "Agents"],
                    "content": "Full blog post content in English.",
                    "image_description": "A futuristic lab with AI agents."
                }
                return AIMessage(content=json.dumps(blog_data))

            if "expert translator" in system_msg or "translate and adapt" in human_msg:
                blog_data = {
                    "title": "Ajanli Yapay Zekanin Gelecegi",
                    "description": "Otonom ajanlarin kesfi.",
                    "tags": ["YZ", "Ajanlar"],
                    "content": "Turkce tam blog yazisi icerigi."
                }
                return AIMessage(content=json.dumps(blog_data))

            if "extract structured references" in system_msg:
                return AIMessage(content="1. Concept: Agentic AI\n2. Quote: 'The future is agentic.'\n3. Topic: Autonomous workflows")
            
            if "search query" in human_msg:
                return AIMessage(content="Agentic AI frameworks 2026")
            
            if "diverse blog storylines" in system_msg or "storyline" in human_msg:
                return AIMessage(content="Storyline 1: The Rise of Agents - Summary 1 ---\nStoryline 2: Engineering Autonomy - Summary 2 ---\nStoryline 3: Scalable Intelligence - Summary 3")
            
            if "visual prompt" in human_msg or "pollinations" in human_msg:
                return AIMessage(content="A futuristic lab with AI agents collaborating on complex tasks, 4k, digital art.")

            return AIMessage(content="Simulated LLM response for: " + human_msg[:50])

        mock_invoke.side_effect = side_effect
        yield mock_invoke

@pytest.fixture
def mock_gitops():
    """Mock GitOps file operations."""
    with patch("nodes.gitops.gitops_node") as mock_node:
        def side_effect(state):
            print("\n[GITOPS] Simulating GitHub Push Success")
            return {"status": "completed", "commit_url": "https://github.com/test/blog/pull/1"}
        mock_node.side_effect = side_effect
        yield mock_node
