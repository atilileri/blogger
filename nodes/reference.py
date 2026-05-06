import logging
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt
from utils.state import PipelineState
from utils.telegram import send_inline_keyboard, send_message

logger = logging.getLogger(__name__)
def reference_node(state: PipelineState):
    """
    Step 4: Extracts key references and waits for user approval (HitL).
    """
    chat_id = state.get("chat_id")
    if not chat_id:
        logger.error("[NODE:reference] Missing chat_id in state.")
        return {"status": "error", "error": "Missing chat_id"}

    logger.info(f"[NODE:reference] Generating references for {chat_id}")
    
    # 1. Generate References via Gemini
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    
    # Combine context from all previous parallel steps
    context_parts = []
    for t in state.get("transcripts", []):
        context_parts.append(f"SOURCE (YouTube): {t['text']}")
    for w in state.get("writer_outputs", []):
        context_parts.append(f"SOURCE (Technical): {w['analysis']}")
    for r in state.get("reader_outputs", []):
        context_parts.append(f"SOURCE (Summary): {r['summary']}")
        
    context = "\n\n".join(context_parts)
    
    prompt = (
        "You are an expert content strategist. Based on the provided context and the user's intent, "
        "identify the most important references for a blog post.\n\n"
        "Please provide:\n"
        "1. Three key concepts or technical terms.\n"
        "2. Two powerful quotes (if available).\n"
        "3. Three main themes/topics to cover.\n\n"
        f"USER INTENT: {state.get('user_intent', 'Write a detailed blog post.')}\n\n"
        f"CONTEXT:\n{context[:10000]}" # Truncate if too long for flash
    )

    resp = llm.invoke([SystemMessage(content="Extract structured references for a blog post."), HumanMessage(content=prompt)])
    refs_text = resp.content

    # 2. Presentation & Interruption
    buttons = [
        [
            {"text": "✅ Approve", "callback_data": "approve"},
            {"text": "📝 Revise", "callback_data": "revise"}
        ],
        [
            {"text": "❌ Cancel", "callback_data": "cancel"}
        ]
    ]
    
    send_inline_keyboard(
        chat_id,
        f"🔍 **Step 1: References & Concepts**\n\n{refs_text}\n\nShould I proceed with these?",
        buttons
    )

    # 3. Wait for Human Decision
    # This will pause the graph. The worker will exit.
    # resume_pipeline or resume_with_text will provide the value for 'decision'
    decision = interrupt("reference_decision_required")
    
    # 4. Process Decision
    if decision == "approve":
        logger.info(f"[NODE:reference] Approved by {chat_id}")
        return {
            "reference_decision": "approve",
            "references": {"raw": refs_text}
        }
    
    if decision == "cancel":
        logger.info(f"[NODE:reference] Cancelled by {chat_id}")
        send_message(chat_id, "⏹️ Pipeline cancelled.")
        return {"reference_decision": "cancel"}
    
    # Revision handling
    # decision will be {"action": "revise", "text": "..."}
    revision_text = decision.get("text", "") if isinstance(decision, dict) else ""
    if not revision_text:
        # User clicked 'Revise' button but hasn't sent text yet
        send_message(chat_id, "✍️ Please send your revision instructions as a text message.")
        # Re-interrupt to wait specifically for the text message
        decision = interrupt("reference_revision_text_required")
        revision_text = decision.get("text", "") if isinstance(decision, dict) else ""

    logger.info(f"[NODE:reference] Revision requested: {revision_text}")
    return {
        "reference_decision": "revise",
        "user_intent": f"{state.get('user_intent', '')}\n\nREVISION: {revision_text}"
    }
