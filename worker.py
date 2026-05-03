"""
LangGraph AI Worker for the Blogger pipeline.
Processes queued YouTube links, extracts metadata, and executes AI generation steps.
"""
import os
import requests
import yt_dlp
from typing import TypedDict
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# 1. Define LangGraph State
class GraphState(TypedDict):
    url: str
    title: str
    channel: str
    error: str

# 2. Node: Pull YouTube Metadata
def fetch_metadata_node(state: GraphState):
    url = state["url"]
    print(f"Fetching data for [{url}]...")
    
    ydl_opts = {
        'quiet': True, 
        'skip_download': True,
        'remote_components': ['ejs:github']
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown Title')
            channel = info.get('uploader', 'Unknown Channel')
            error = ""
        except Exception as e:
            print(f"Failed to fetch metadata: {e}")
            title = ""
            channel = ""
            error = str(e)
        
    return {"title": title, "channel": channel, "error": error}

# 3. LangGraph Setup
def build_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("fetch_metadata", fetch_metadata_node)
    workflow.set_entry_point("fetch_metadata")
    workflow.add_edge("fetch_metadata", END)
    return workflow.compile()

# 4.Main function to be triggered from queue
def process_video(url: str, chat_id: int = None):
    app = build_graph()
    initial_state = {"url": url, "title": "", "channel": "", "error": ""}
    
    result = app.invoke(initial_state)
    
    # todo : check if no error. this is too early to log celebrations
    print("\n" + "="*40)
    print("🚀 TASK COMPLETED!")
    print(f"Channel: {result['channel']}")
    print(f"Title: {result['title']}")
    print("="*40 + "\n")

    # todo : there must always be a chat_id. validate this.
    if chat_id:
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if telegram_token:
            telegram_api_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            if result.get('error'):
                message_text = f"❌ Analysis Failed!\n\nError: {result['error']}"
            else:
                message_text = f"✅ Analysis Completed!\n\n📺 Title: {result['title']}\n👤 Channel: {result['channel']}"
            try:
                requests.post(telegram_api_url, json={
                    "chat_id": chat_id,
                    "text": message_text
                })
            except Exception as e:
                print(f"Failed to send completion message to Telegram: {e}")
    return result
