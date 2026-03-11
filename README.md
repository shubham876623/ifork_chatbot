# iFork Chatbot

RAG + FastAPI backend for the iFork Mackay chat widget.

**Deployment:** Use **EC2** (or Railway, Render, Fly.io) — not Vercel. ChromaDB and its dependencies exceed Vercel’s serverless bundle size limit (~250 MB).

## Deploy on EC2 (or similar)

1. **Server:** Launch an EC2 instance (or other VM), install Python 3.10+.

2. **Clone and install:**
   ```bash
   git clone https://github.com/shubham876623/ifork_chatbot.git
   cd ifork_chatbot
   pip install -r requirements.txt
   ```

3. **Environment variables** (e.g. in `.env` or `export`):
   - `OPENAI_API_KEY` – your OpenAI API key (required)
   - `HUBSPOT_ACCESS_TOKEN` – HubSpot private app token (optional; for creating leads)

4. **Run:**
   ```bash
   uvicorn ifork_chatbot.main:app --host 0.0.0.0 --port 8000
   ```
   Use a process manager (systemd, supervisord) or reverse proxy (nginx) for production.

5. **Widget:** Set your chat widget’s `API_BASE` to your server URL (e.g. `http://your-ec2-ip:8000` or your domain).

## Local run

```bash
pip install -r requirements.txt
# Set OPENAI_API_KEY (and optionally HUBSPOT_ACCESS_TOKEN) in .env or env
python -m ifork_chatbot.ingest   # one-off: build Chroma index
uvicorn ifork_chatbot.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/health` and `POST /chat` with body: `{"session_id": "...", "message": "..."}`.

## RAG

The `chroma_ifork/` folder is the pre-built vector index. If you change `ifork_chatbot_knowledge_base.md`, run `python -m ifork_chatbot.ingest` and redeploy with the updated `chroma_ifork/`.
