# iFork Chatbot

RAG + FastAPI backend for the iFork Mackay chat widget. Deploy to Vercel.

## Deploy on Vercel

1. **Connect this repo** in [Vercel](https://vercel.com) → New Project → Import `shubham876623/ifork_chatbot`.

2. **Environment variables** (Project → Settings → Environment Variables):
   - `OPENAI_API_KEY` – your OpenAI API key (required)
   - `HUBSPOT_ACCESS_TOKEN` – HubSpot private app token (optional; for creating leads)

3. **Deploy.** The API will be at `https://your-project.vercel.app`.
   - `GET /health` – health check
   - `POST /chat` – body: `{"session_id": "...", "message": "..."}`

4. **Widget:** Set your chat widget’s `API_BASE` to your Vercel URL (e.g. `https://your-project.vercel.app`).

## Local run

```bash
pip install -r requirements.txt
# Set OPENAI_API_KEY (and optionally HUBSPOT_ACCESS_TOKEN) in .env or env
python -m ifork_chatbot.ingest   # one-off: build Chroma index
uvicorn ifork_chatbot.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/health` and `POST /chat` as above.

## RAG

The `chroma_ifork/` folder is the pre-built vector index. If you change `ifork_chatbot_knowledge_base.md`, run `python -m ifork_chatbot.ingest` and commit the updated `chroma_ifork/` to redeploy with new content.
