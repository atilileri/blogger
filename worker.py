"""
LangGraph AI Worker for the Blogger pipeline.
Processes queued YouTube links, extracts metadata, and executes AI generation steps.
"""
import os
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
        info = ydl.extract_info(url, download=False)
        title = info.get('title', 'Unknown Title')
        channel = info.get('uploader', 'Unknown Channel')
        
    return {"title": title, "channel": channel}

# 3. LangGraph Setup
def build_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("fetch_metadata", fetch_metadata_node)
    workflow.set_entry_point("fetch_metadata")
    workflow.add_edge("fetch_metadata", END)
    return workflow.compile()

# 4.Main function to be triggered from queue
def process_video(url: str):
    app = build_graph()
    initial_state = {"url": url, "title": "", "channel": ""}
    
    result = app.invoke(initial_state)
    
    print("\n" + "="*40)
    print("🚀 TASK COMPLETED!")
    print(f"Channel: {result['channel']}")
    print(f"Title: {result['title']}")
    print("="*40 + "\n")
    return result
