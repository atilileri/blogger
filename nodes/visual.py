import os
import logging
import random
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from utils.state import PipelineState

logger = logging.getLogger(__name__)

async def visual_node(state: PipelineState):
    """
    Step 7: Generates a hero image using Pollinations.ai.
    """
    logger.info(f"[NODE:visual] Generating hero image for {state['chat_id']}")
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")
    
    blog_en = state.get("blog_json_en", {})
    title = blog_en.get("title", "Technology")
    
    # 1. Generate an artistic prompt for Pollinations
    prompt_gen = (
        f"Generate a professional, high-fidelity image prompt for a blog post titled: '{title}'.\n"
        "Style: Cinematic, clean, tech-focused, no text in image.\n"
        "Output ONLY the prompt text, no headers or quotes."
    )
    
    resp = await llm.ainvoke([SystemMessage(content="You are an image prompt engineer."), HumanMessage(content=prompt_gen)])
    image_prompt = resp.content.strip().replace("\n", " ").replace('"', "")
    
    # 2. Build URL (Pollinations handles the generation on-the-fly)
    seed = random.randint(1, 999999)
    # URL Encode the prompt
    import urllib.parse
    encoded_prompt = urllib.parse.quote(image_prompt)
    
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&nologo=true&seed={seed}"
    
    logger.info(f"[VISUAL] Image URL generated: {image_url}")
    
    return {
        "generated_images": [
            {
                "url": image_url,
                "prompt": image_prompt,
                "role": "hero",
                "alt": title
            }
        ]
    }
