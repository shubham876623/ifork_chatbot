# iFork Chatbot

RAG + FastAPI backend for the iFork Mackay chat widget. Two deployment options:

- **Vercel:** uses pre-built `embeddings.json` (no Chroma at runtime, small bundle).
- **EC2:** uses Chroma (`chroma_ifork/`) for RAG. Client can move to EC2 later.

---

## Deploy on Vercel (embeddings.json)

1. Connect this repo in [Vercel](https://vercel.com) → New Project → Import.
2. **Install command** is set in `vercel.json` to `pip install -r requirements-vercel.txt` (no Chroma, keeps bundle under 250 MB).
3. Set env vars: `OPENAI_API_KEY`, optional `HUBSPOT_ACCESS_TOKEN`.
4. Deploy. The API is at `https://your-project.vercel.app` (`GET /health`, `POST /chat`).
5. Set the widget `API_BASE` to your Vercel URL.

The repo includes a pre-built `embeddings.json`. To regenerate it (e.g. after changing the knowledge base), run locally: `python -m ifork_chatbot.ingest` then `python -m ifork_chatbot.export_embeddings`, or `python -m ifork_chatbot.build_embeddings_from_kb` (no Chroma), then commit the new `embeddings.json`.

---

## Deploy on EC2 (Chroma)

1. Clone the repo, then: `pip install -r requirements.txt` (includes Chroma).
2. Build Chroma once: `python -m ifork_chatbot.ingest` (creates/updates `chroma_ifork/`).
3. Set env vars: `OPENAI_API_KEY`, optional `HUBSPOT_ACCESS_TOKEN`.
4. Run: `uvicorn ifork_chatbot.main:app --host 0.0.0.0 --port 8000`. Use systemd + nginx for production.
5. Set the widget `API_BASE` to your EC2 URL.

---

## Local run

```bash
pip install -r requirements.txt
# Set OPENAI_API_KEY (and optionally HUBSPOT_ACCESS_TOKEN) in .env or env
python -m ifork_chatbot.ingest   # one-off: build Chroma index
uvicorn ifork_chatbot.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/health` and `POST /chat` with body: `{"session_id": "...", "message": "..."}`.

## RAG

- **Vercel:** RAG uses `embeddings.json` (same behaviour as Chroma).
- **EC2 / local:** RAG uses `chroma_ifork/`. After editing `ifork_chatbot_knowledge_base.md`, run `python -m ifork_chatbot.ingest` and redeploy; for Vercel also run `export_embeddings` and commit `embeddings.json`.
