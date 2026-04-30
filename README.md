# Blogger

This pipeline automatically extracts information from YouTube links sent via Telegram, transcribes the audio, conducts research, and generates a fully formatted blog post for an Astro-based static site.

## Architecture
- **Webhook Gateway:** Cloudflare Tunnels
- **API & Queue:** FastAPI, Redis, RQ (Redis Queue)
- **AI Worker:** LangGraph, yt-dlp, Whisper, LLM APIs

## Prerequisites
- Proxmox (or similar) environment with LXC/VMs for distributed processing.
- Python 3.10+
- Redis Server
- `ffmpeg` (for audio processing)
- Supported JS runtime (e.g., `deno`) for `yt-dlp`.

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/blogger.git
   cd blogger
   ```

2. **Set up the virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Environment Variables:**
   Copy the example environment file and fill in your secrets.
   ```bash
   cp .env.example .env
   # Edit .env with your favorite editor (e.g., nano .env)
   ```

## Running the Services

### 1. API Server
Run the FastAPI application to listen for Telegram webhooks:
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

### 2. RQ Worker
Run the background worker to process the tasks:
```bash
# Ensure REDIS_HOST is correctly set in your .env
rq worker video_tasks
```
