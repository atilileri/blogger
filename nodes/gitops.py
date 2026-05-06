import os
import logging
import httpx
import base64
import uuid
from datetime import datetime
from utils.state import PipelineState
from utils.telegram import send_message

logger = logging.getLogger(__name__)

async def gitops_node(state: PipelineState):
    """
    Step 8: Formats blog posts and pushes them to GitHub along with the hero image.
    """
    logger.info(f"[NODE:gitops] Starting GitHub push for {state['chat_id']}")
    
    # 1. Configuration
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    content_path = os.getenv("BLOG_CONTENT_PATH", "src/content/blog")
    images_path = os.getenv("BLOG_IMAGES_PATH", "public/images/blog")
    
    if not all([token, repo]):
        error_msg = "❌ GITHUB_TOKEN or GITHUB_REPO missing. Cannot publish."
        logger.error(error_msg)
        await send_message(state["chat_id"], error_msg)
        return {"status": "error", "error": "Missing credentials"}

    # 2. Prepare Metadata
    pub_date = datetime.now().strftime("%Y-%m-%d")
    trans_id = str(uuid.uuid4())[:8]
    
    blog_en = state["blog_json_en"]
    blog_tr = state["blog_json_tr"]
    
    slug_en = blog_en["title"].lower().replace(" ", "-").replace("?", "").replace("!", "")[:50]
    slug_tr = f"{slug_en}-tr"
    
    # 3. Handle Hero Image
    image_info = state.get("generated_images", [{}])[0]
    image_url = image_info.get("url")
    image_filename = f"{slug_en}.webp"
    
    # Download image to push to GitHub
    async with httpx.AsyncClient() as client:
        try:
            img_resp = await client.get(image_url, timeout=30)
            img_resp.raise_for_status()
            img_content = img_resp.content
        except Exception as e:
            logger.error(f"[GITOPS] Failed to download hero image: {e}")
            img_content = None

    # 4. Format Frontmatter
    def format_post(data, lang, hero_img_path):
        tags_str = ", ".join([f'"{t}"' for t in data["tags"]])
        return f"""---
title: "{data['title']}"
description: "{data['description']}"
pubDate: {pub_date}
tags: [{tags_str}]
heroImage: "{hero_img_path}"
lang: "{lang}"
translationId: "{trans_id}"
---

{data['content']}
"""

    hero_img_web_path = f"/{images_path}/{image_filename}".replace("//", "/")
    post_en_body = format_post(blog_en, "en", hero_img_web_path)
    post_tr_body = format_post(blog_tr, "tr", hero_img_web_path)

    # 5. Push to GitHub via API
    # We use a single commit with multiple files if possible, or sequential. 
    # For simplicity, sequential PUT requests to the Contents API.
    
    async def push_file(path, content, is_binary=False):
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Get SHA if file exists (to update)
        sha = None
        get_resp = await client.get(url, headers=headers)
        if get_resp.status_code == 200:
            sha = get_resp.json()["sha"]
        
        payload = {
            "message": f"Blogger AI: Publish {path}",
            "content": base64.b64encode(content if is_binary else content.encode()).decode(),
            "branch": "main" # or config
        }
        if sha:
            payload["sha"] = sha
            
        put_resp = await client.put(url, headers=headers, json=payload)
        return put_resp.status_code in [200, 201]

    async with httpx.AsyncClient() as client:
        success = True
        # Upload Image
        if img_content:
            img_success = await push_file(f"{images_path}/{image_filename}", img_content, is_binary=True)
            if not img_success: success = False
        
        # Upload EN Post
        en_success = await push_file(f"{content_path}/{slug_en}.md", post_en_body)
        if not en_success: success = False
        
        # Upload TR Post
        tr_success = await push_file(f"{content_path}/{slug_tr}.md", post_tr_body)
        if not tr_success: success = False

    if success:
        commit_url = f"https://github.com/{repo}/commits/main"
        await send_message(state["chat_id"], f"🚀 **Success!** Blog posts published to GitHub.\n\n[View Repository]({commit_url})")
        return {"status": "completed", "commit_url": commit_url}
    else:
        await send_message(state["chat_id"], "⚠️ Partial success or failure while pushing to GitHub. Check logs.")
        return {"status": "partial_success"}
