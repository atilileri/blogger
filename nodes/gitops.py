import os
import logging
import httpx
import base64
import uuid
import re
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
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
    
    slug_en = re.sub(r'[^a-z0-9]+', '-', blog_en["title"].lower()).strip('-')[:50]
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

    # 5. Push to GitHub via Git Data API (Atomic Commit)
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def create_atomic_commit(client, files, message, branch="main"):
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # 1. Get branch ref
        ref_url = f"https://api.github.com/repos/{repo}/git/refs/heads/{branch}"
        ref_resp = await client.get(ref_url, headers=headers)
        ref_resp.raise_for_status()
        latest_commit_sha = ref_resp.json()["object"]["sha"]
        
        # 2. Get base tree
        commit_url = f"https://api.github.com/repos/{repo}/git/commits/{latest_commit_sha}"
        commit_resp = await client.get(commit_url, headers=headers)
        commit_resp.raise_for_status()
        base_tree_sha = commit_resp.json()["tree"]["sha"]
        
        # 3. Create blobs and tree array
        tree_items = []
        for f in files:
            blob_url = f"https://api.github.com/repos/{repo}/git/blobs"
            blob_payload = {
                "content": base64.b64encode(f["content"]).decode() if f["is_binary"] else f["content"],
                "encoding": "base64" if f["is_binary"] else "utf-8"
            }
            blob_resp = await client.post(blob_url, headers=headers, json=blob_payload)
            blob_resp.raise_for_status()
            
            tree_items.append({
                "path": f["path"],
                "mode": "100644",
                "type": "blob",
                "sha": blob_resp.json()["sha"]
            })
            
        # 4. Create Tree
        tree_url = f"https://api.github.com/repos/{repo}/git/trees"
        tree_payload = {
            "base_tree": base_tree_sha,
            "tree": tree_items
        }
        tree_resp = await client.post(tree_url, headers=headers, json=tree_payload)
        tree_resp.raise_for_status()
        
        # 5. Create Commit
        new_commit_url = f"https://api.github.com/repos/{repo}/git/commits"
        new_commit_payload = {
            "message": message,
            "tree": tree_resp.json()["sha"],
            "parents": [latest_commit_sha]
        }
        new_commit_resp = await client.post(new_commit_url, headers=headers, json=new_commit_payload)
        new_commit_resp.raise_for_status()
        
        # 6. Update Ref
        update_ref_payload = {"sha": new_commit_resp.json()["sha"]}
        update_resp = await client.patch(ref_url, headers=headers, json=update_ref_payload)
        update_resp.raise_for_status()
        return True

    async with httpx.AsyncClient() as client:
        files_to_commit = []
        if img_content:
            files_to_commit.append({
                "path": f"{images_path}/{image_filename}",
                "content": img_content,
                "is_binary": True
            })
        files_to_commit.append({
            "path": f"{content_path}/{slug_en}.md",
            "content": post_en_body,
            "is_binary": False
        })
        files_to_commit.append({
            "path": f"{content_path}/{slug_tr}.md",
            "content": post_tr_body,
            "is_binary": False
        })

        try:
            success = await create_atomic_commit(
                client, 
                files_to_commit, 
                f"Blogger AI: Publish '{blog_en['title']}'"
            )
        except Exception as e:
            logger.error(f"[GITOPS] Atomic commit failed: {e}")
            success = False

    if success:
        commit_url = f"https://github.com/{repo}/commits/main"
        await send_message(state["chat_id"], f"🚀 **Success!** Blog posts published to GitHub.\n\n[View Repository]({commit_url})")
        return {"status": "completed", "commit_url": commit_url}
    else:
        await send_message(state["chat_id"], "⚠️ Partial success or failure while pushing to GitHub. Check logs.")
        return {"status": "partial_success"}
