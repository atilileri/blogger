import logging
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import interrupt
from utils.state import PipelineState
from utils.telegram import send_inline_keyboard, send_message

logger = logging.getLogger(__name__)

def creative_node(state: PipelineState):
    """
    Step 6: Generates storylines, waits for selection (HitL), 
    then generates full EN and TR blog content.
    """
    logger.info(f"[NODE:creative] Starting creative phase for {state['chat_id']}")
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

    # 1. Generate 3 Diverse Storylines
    refs = state.get("references", {}).get("raw", "")
    research = "\n".join(state.get("research_snippets", []))
    
    storyline_prompt = (
        "You are a creative lead. Based on the following references and research, "
        "propose 3 diverse storylines for a blog post. Each storyline should have a "
        "unique angle (e.g., Technical Deep Dive, Future Vision, Practical Tutorial).\n\n"
        f"REFERENCES:\n{refs}\n\n"
        f"RESEARCH:\n{research}\n\n"
        "Format: Storyline 1: [Title] - [Summary] ---\n"
        "Storyline 2: [Title] - [Summary] ---\n"
        "Storyline 3: [Title] - [Summary]\n"
    )

    resp = llm.invoke([SystemMessage(content="Generate 3 diverse blog storylines."), HumanMessage(content=storyline_prompt)])
    storylines_raw = resp.content
    storylines_list = [s.strip() for s in storylines_raw.split("---") if s.strip()]

    # 2. Storyline Selection Interruption
    buttons = []
    row = []
    for i in range(len(storylines_list)):
        row.append({"text": f"Story {i+1}", "callback_data": str(i)})
    buttons.append(row)
    buttons.append([{"text": "❌ Cancel", "callback_data": "cancel"}])

    send_inline_keyboard(
        state["chat_id"],
        f"🎭 **Step 3: Choose a Storyline**\n\n{storylines_raw}\n\nWhich angle should we take?",
        buttons
    )

    selection = interrupt("storyline_selection_required")
    
    if selection == "cancel":
        send_message(state["chat_id"], "⏹️ Pipeline cancelled.")
        return {"status": "cancelled"}

    try:
        idx = int(selection)
        chosen_storyline = storylines_list[idx]
    except (ValueError, IndexError):
        logger.error(f"[CREATIVE] Invalid selection: {selection}")
        send_message(state["chat_id"], "⚠️ Invalid selection. Please try starting over.")
        return {"status": "error"}

    logger.info(f"[NODE:creative] Storyline {idx+1} selected. Generating full posts...")
    send_message(state["chat_id"], f"✍️ Storyline {idx+1} selected! Generating full English and Turkish posts... This may take a minute.")

    # 3. Generate EN and TR Posts
    # Prompt for EN
    en_prompt = (
        f"Write a full, high-quality blog post in English based on this storyline: {chosen_storyline}\n\n"
        f"Include context from these references: {refs}\n\n"
        "Output as JSON with keys: title, description, tags (list), content (markdown)."
    )
    
    en_resp = llm.invoke([
        SystemMessage(content="You are an expert blogger. Output strictly JSON."), 
        HumanMessage(content=en_prompt)
    ])
    
    # Prompt for TR (Direct translation/adaptation)
    tr_prompt = (
        f"Translate and adapt the following blog post to Turkish. Maintain the technical accuracy "
        f"and the same professional tone.\n\n"
        f"ENGLISH CONTENT:\n{en_resp.content}\n\n"
        "Output as JSON with keys: title, description, tags (list), content (markdown)."
    )
    
    tr_resp = llm.invoke([
        SystemMessage(content="You are an expert translator and blogger. Output strictly JSON."), 
        HumanMessage(content=tr_prompt)
    ])

    try:
        # Clean potential markdown code blocks from LLM output
        def parse_llm_json(text):
            clean = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)

        blog_en = parse_llm_json(en_resp.content)
        blog_tr = parse_llm_json(tr_resp.content)

        return {
            "storylines": storylines_list,
            "chosen_storyline_index": idx,
            "blog_json_en": blog_en,
            "blog_json_tr": blog_tr,
            "status": "creative_completed"
        }
    except Exception as e:
        logger.error(f"[CREATIVE] JSON parsing failed: {e}")
        send_message(state["chat_id"], "❌ Failed to generate structured content. Please try /cancel and restart.")
        return {"status": "error"}
