"""
Vercel entrypoint: expose the iFork chatbot FastAPI app.
Set OPENAI_API_KEY and HUBSPOT_ACCESS_TOKEN in Vercel project Environment Variables.
Pre-build Chroma and commit chroma_ifork/ so it is bundled (or run ingest in build).
"""
from ifork_chatbot.main import app

__all__ = ["app"]
