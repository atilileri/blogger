import os
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt
from utils.state import PipelineState
from utils.telegram import send_inline_keyboard, send_message
from utils.redis_utils import redis_conn
from tavily import TavilyClient
import json

logger = logging.getLogger(__name__)
def research_node(state: PipelineState):
    """
    Step 5: Performs web research based on approved references and waits for HitL approval.
    """
    chat_id = state.get("chat_id")
    if not chat_id:
        logger.error("[NODE:research] Missing chat_id in state.")
        return {"status": "error", "error": "Missing chat_id"}

    logger.info(f"[NODE:research] Starting research for {chat_id}")
    
    # 1. Generate search queries based on references and user intent
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    refs = (state.get("references") or {}).get("raw", "")
    
    snippets = state.get("research_snippets", [])
    decision_state = state.get("research_decision")
    
    thread_id = state.get("thread_id", "")
    cache_key = f"cache_{thread_id}_research"
    
    if not snippets or decision_state == "revise":
        cached = redis_conn.get(cache_key)
        if cached:
            snippets = json.loads(cached.decode("utf-8"))
            research_text = "\n\n---\n\n".join(snippets[:5])
        else:
            query_prompt = (
                f"Based on the following references and user intent, generate 3 high-quality web search queries "
                f"to find more technical details, recent news, or complementary data for a blog post.\n\n"
                f"USER INTENT: {state.get('user_intent', '')}\n"
                f"REFERENCES:\n{refs}\n\n"
                "Output only the queries, one per line."
            )
            
            resp = llm.invoke([SystemMessage(content="Generate research queries."), HumanMessage(content=query_prompt)])
            # Filter out empty lines and markdown code block artifacts
            queries = [
                q.strip("- ").strip() 
                for q in resp.content.split("\n") 
                if q.strip() and not q.strip().startswith("```")
            ][:3]
            
            # 2. Execute Search via Tavily
            tavily_key = os.getenv("TAVILY_API_KEY")
            snippets = []
            
            if tavily_key:
                tavily = TavilyClient(api_key=tavily_key)
                for q in queries:
                    try:
                        search_result = tavily.search(query=q, search_depth="advanced", max_results=2)
                        for res in search_result.get("results", []):
                            snippets.append(f"**{res['title']}**\n{res['content'][:300]}...\nSource: {res['url']}")
                    except Exception as e:
                        logger.error(f"[RESEARCH] Tavily search failed for query '{q}': {e}")
            else:
                logger.warning("[RESEARCH] TAVILY_API_KEY not found. Skipping search.")
                snippets.append("_(No research performed - API key missing)_")

            research_text = "\n\n---\n\n".join(snippets[:5])
            
            if thread_id:
                redis_conn.set(cache_key, json.dumps(snippets), ex=86400)
            
            # 3. Interruption
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
                f"🌐 **Step 2: Web Research Findings**\n\n{research_text}\n\nShould I use these as extra context?",
                buttons
            )
        
    decision = interrupt("research_decision_required")
    
    # 4. Process Decision
    if decision == "approve":
        logger.info(f"[NODE:research] Approved by {chat_id}")
        redis_conn.delete(cache_key)
        return {
            "research_decision": "approve",
            "research_snippets": snippets
        }
    
    if decision == "cancel":
        logger.info(f"[NODE:research] Cancelled by {chat_id}")
        redis_conn.delete(cache_key)
        send_message(chat_id, "⏹️ Pipeline cancelled.")
        return {"research_decision": "cancel"}
    
    # Revision
    revision_text = decision.get("text", "") if isinstance(decision, dict) else ""
    if not revision_text:
        send_message(chat_id, "✍️ Please send your research revision instructions.")
        decision = interrupt("research_revision_text_required")
        revision_text = decision.get("text", "") if isinstance(decision, dict) else ""

    logger.info(f"[NODE:research] Revision requested: {revision_text}")
    redis_conn.delete(cache_key)
    return {
        "research_decision": "revise",
        "user_intent": f"{state.get('user_intent', '')}\n\nRESEARCH REVISION: {revision_text}"
    }
