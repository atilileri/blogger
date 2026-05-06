import os
import logging
import asyncio
from typing import Dict, Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt, Send
from dotenv import load_dotenv

from utils.state import PipelineState
from utils.telegram import answer_callback_query

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", "checkpoints.sqlite")

def build_graph():
    """
    Constructs the LangGraph pipeline with SqliteSaver persistence.
    """
    # Ensure checkpoint directory exists
    db_dir = os.path.dirname(CHECKPOINT_DB)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    # Use checkpointer for persistence across interrupts
    checkpointer = SqliteSaver.from_conn_string(CHECKPOINT_DB)
    workflow = StateGraph(PipelineState)

    # --- Node Definitions ---
    from nodes.intake import intake_node
    
    workflow.add_node("intake", intake_node)

    # --- Graph Edges ---
    workflow.add_edge(START, "intake")
    workflow.add_edge("intake", END)

    return workflow.compile(checkpointer=checkpointer)

# --- Entry Points for RQ Workers ---

def run_pipeline(message: dict):
    """
    Initial entry point for a new blog request.
    Called by RQ when api.py enqueues a new message.
    """
    chat_id = message["chat"]["id"]
    thread_id = str(chat_id)
    logger.info(f"[WORKER] run_pipeline: chat_id={chat_id}")

    app = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    
    # Initialize state
    initial_state = {
        "chat_id": chat_id,
        "thread_id": thread_id,
        "raw_message": message,
        "status": "in_progress",
        "youtube_urls": [],
        "website_urls": [],
        "transcripts": [],
        "writer_outputs": [],
        "reader_outputs": [],
        "generated_images": []
    }

    try:
        app.invoke(initial_state, config=config)
    except Exception as e:
        logger.error(f"[WORKER] Error in run_pipeline: {e}")

def resume_pipeline(callback_query: dict):
    """
    Resumes a graph that is waiting at an interrupt() after a button click.
    """
    chat_id = callback_query["message"]["chat"]["id"]
    decision = callback_query.get("data")
    callback_id = callback_query.get("id")
    thread_id = str(chat_id)

    logger.info(f"[WORKER] resume_pipeline: chat_id={chat_id} decision={decision}")

    # Answer the callback query to remove Telegram's loading spinner
    asyncio.run(answer_callback_query(callback_id))

    app = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Command(resume=...) sends the value back to the specific interrupt() call
        app.invoke(Command(resume=decision), config=config)
    except Exception as e:
        logger.error(f"[WORKER] Error in resume_pipeline: {e}")

def resume_with_text(message: dict):
    """
    Resumes a graph via a text response (used in the "Revise" loop).
    """
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    thread_id = str(chat_id)

    logger.info(f"[WORKER] resume_with_text: chat_id={chat_id}")

    app = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # Send a dictionary payload that the node's interrupt handler will parse
        app.invoke(Command(resume={"action": "revise", "text": text}), config=config)
    except Exception as e:
        logger.error(f"[WORKER] Error in resume_with_text: {e}")
