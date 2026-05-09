import os
import logging
import asyncio
from typing import Dict, Any

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt, Send
from dotenv import load_dotenv

from utils.state import PipelineState
from utils.telegram import answer_callback_query, edit_message_text, send_message
from utils.redis_utils import release_lock, redis_conn
import functools
import uuid

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

def build_graph(checkpointer):
    """
    Constructs the LangGraph pipeline with SqliteSaver persistence.
    """
    logger.debug("[WORKER] Building graph...")
    # Ensure checkpoint directory exists
    db_dir = os.path.dirname(CHECKPOINT_DB)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    workflow = StateGraph(PipelineState)

    # --- Node Definitions ---
    from nodes.intake import intake_node
    from nodes.transcription import transcription_node
    from nodes.writer import writer_node
    from nodes.reader import reader_node
    from nodes.reference import reference_node
    from nodes.research import research_node
    from nodes.creative import creative_node
    from nodes.visual import visual_node
    from nodes.gitops import gitops_node
    
    workflow.add_node("intake", intake_node)
    workflow.add_node("transcription", transcription_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("reader", reader_node)
    workflow.add_node("reference", reference_node)
    workflow.add_node("research", research_node)
    workflow.add_node("creative", creative_node)
    workflow.add_node("visual", visual_node)
    workflow.add_node("gitops", gitops_node)

    # Node that gathers all parallel results
    def gather_node(state: PipelineState):
        logger.info(f"[NODE:gather] Collected results. Moving to Reference Agent.")
        return {"status": "processing_completed"}

    workflow.add_node("gather", gather_node)

    # --- Graph Edges ---
    workflow.add_edge(START, "intake")

    def route_to_parallel(state: PipelineState):
        """
        Dynamically fans out to parallel nodes using the Send API.
        """
        sends = []
        # Fan out YouTube URLs to transcription
        for url in state.get("youtube_urls", []):
            sends.append(Send("transcription", {"url": url}))
        
        # Fan out Web URLs to both Writer (technical) and Reader (summary)
        for url in state.get("website_urls", []):
            sends.append(Send("writer", {"url": url}))
            sends.append(Send("reader", {"url": url}))
        
        # If no URLs found, go straight to gather
        if not sends:
            return "gather"
            
        return sends

    workflow.add_conditional_edges("intake", route_to_parallel, ["transcription", "writer", "reader", "gather"])
    workflow.add_edge("transcription", "gather")
    workflow.add_edge("writer", "gather")
    workflow.add_edge("reader", "gather")
    workflow.add_edge("gather", "reference")

    def route_after_reference(state: PipelineState):
        decision = state.get("reference_decision")
        if decision == "approve":
            return "research"
        if decision == "cancel":
            return END
        return "reference"

    workflow.add_conditional_edges("reference", route_after_reference, ["reference", "research", END])

    def route_after_research(state: PipelineState):
        decision = state.get("research_decision")
        if decision == "approve":
            return "creative"
        if decision == "cancel":
            return END
        return "research"

    workflow.add_conditional_edges("research", route_after_research, ["research", "creative", END])
    
    # Sequential finish
    workflow.add_edge("creative", "visual")
    workflow.add_edge("visual", "gitops")
    workflow.add_edge("gitops", END)

    return workflow.compile(checkpointer=checkpointer)

def handle_worker_errors(func):
    """
    Decorator to wrap worker entry points. Extracts chat_id, runs task,
    and handles exceptions by notifying the user and releasing the Redis lock.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"[WORKER] Error in {func.__name__}: {e}", exc_info=True)
            
            chat_id = None
            if args:
                msg = args[0]
                if "chat" in msg:
                    chat_id = msg["chat"]["id"]
                elif "message" in msg and "chat" in msg["message"]:
                    chat_id = msg["message"]["chat"]["id"]
            elif kwargs and "message" in kwargs:
                msg = kwargs["message"]
                if "chat" in msg:
                    chat_id = msg["chat"]["id"]
            elif kwargs and "callback_query" in kwargs:
                msg = kwargs["callback_query"]
                if "message" in msg and "chat" in msg["message"]:
                    chat_id = msg["message"]["chat"]["id"]
                    
            if chat_id:
                try:
                    error_msg = f"❌ A pipeline error occurred:\n\n```\n{e}\n```\n\nYour session has been reset."
                    send_message(chat_id, error_msg)
                    release_lock(chat_id)
                except Exception as inner_e:
                    logger.error(f"[WORKER] Failed to handle error for {chat_id}: {inner_e}")
            raise  # Reraise so RQ knows the job failed
    return wrapper

def handle_system_failure(job, connection, type, value, traceback):
    """
    RQ callback invoked when a job completely fails (e.g., process crashes).
    """
    logger.error(f"[WORKER] System failure in job {job.id}: {type} - {value}")
    if job.args:
        msg = job.args[0]
        chat_id = None
        if "chat" in msg:
            chat_id = msg["chat"]["id"]
        elif "message" in msg and "chat" in msg["message"]:
            chat_id = msg["message"]["chat"]["id"]
        
        if chat_id:
            release_lock(chat_id)
            try:
                error_msg = f"⚠️ A system-level worker failure occurred:\n\n```\n{type} - {value}\n```\n\nYour session has been reset."
                send_message(chat_id, error_msg)
            except Exception as e:
                logger.error(f"[WORKER] Failed to notify {chat_id} during system failure: {e}")

# --- Entry Points for RQ Workers ---

@handle_worker_errors
def run_pipeline(message: dict):
    """
    Initial entry point for a new blog request.
    Called by RQ when api.py enqueues a new message.
    """
    chat_id = message["chat"]["id"]
    thread_id = str(uuid.uuid4())
    redis_conn.set(f"thread_{chat_id}", thread_id, ex=3600)
    logger.info(f"[WORKER] run_pipeline: chat_id={chat_id} thread_id={thread_id}")

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

    with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        app = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        logger.debug("[WORKER] Invoking graph for run_pipeline")
        app.invoke(initial_state, config=config)

@handle_worker_errors
def resume_pipeline(callback_query: dict):
    """
    Resumes a graph that is waiting at an interrupt() after a button click.
    """
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    decision = callback_query.get("data")
    callback_id = callback_query.get("id")
    
    thread_id_bytes = redis_conn.get(f"thread_{chat_id}")
    if not thread_id_bytes:
        logger.error(f"[WORKER] No active thread found for chat_id={chat_id}")
        return
    thread_id = thread_id_bytes.decode("utf-8")

    logger.info(f"[WORKER] resume_pipeline: chat_id={chat_id} decision={decision} thread_id={thread_id}")

    # Answer the callback query to remove Telegram's loading spinner
    answer_callback_query(callback_id, text="⏳ Processing your selection...")

    # Edit the original message to reflect the choice and remove buttons
    original_text = callback_query["message"].get("text", "")
    edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=f"{original_text}\n\n✅ **Approved Selection**: {decision}"
    )

    with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        app = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        # Command(resume=...) sends the value back to the specific interrupt() call
        logger.debug(f"[WORKER] Invoking graph with resume={decision}")
        app.invoke(Command(resume=decision), config=config)

@handle_worker_errors
def resume_with_text(message: dict):
    """
    Resumes a graph via a text response (used in the "Revise" loop).
    """
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    
    thread_id_bytes = redis_conn.get(f"thread_{chat_id}")
    if not thread_id_bytes:
        logger.error(f"[WORKER] No active thread found for chat_id={chat_id}")
        return
    thread_id = thread_id_bytes.decode("utf-8")

    logger.info(f"[WORKER] resume_with_text: chat_id={chat_id} thread_id={thread_id}")

    with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        app = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        # Send a dictionary payload that the node's interrupt handler will parse
        logger.debug(f"[WORKER] Invoking graph with revise text")
        app.invoke(Command(resume={"action": "revise", "text": text}), config=config)
