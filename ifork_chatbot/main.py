"""
FastAPI backend for iFork chatbot. POST /chat with session_id + message; RAG + OpenAI; HubSpot on qualified.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ifork_chatbot.config import load_config
from ifork_chatbot.chat import chat_turn, get_session, is_qualified, mark_submitted
from ifork_chatbot.hubspot_client import create_contact

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config loaded at startup
_config: dict = {}


def _address_from_collected(collected: dict) -> str:
    """Optional address line for HubSpot (e.g. suburb only)."""
    suburb = (collected.get("suburb") or "").strip()
    if suburb:
        return f"Mackay region, {suburb}"
    return ""


def _message_from_collected(collected: dict) -> str:
    """Build a message string from quote details (same idea as form 'message' field)."""
    parts = []
    for key in ("pallet_count", "timeline", "notes"):
        v = (collected.get(key) or "").strip()
        if v:
            parts.append(f"{key.replace('_', ' ').title()}: {v}")
    return " | ".join(parts) if parts else ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config
    _config = load_config()
    yield
    _config = {}


app = FastAPI(title="iFork Chatbot API", lifespan=lifespan)

# CORS: allow Wix site and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to https://www.iforkmackay.com.au in production
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    qualified: bool
    collected: dict
    hubspot_created: bool = False  # True only when a contact was actually created in HubSpot


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.session_id or not (req.message or "").strip():
        raise HTTPException(status_code=400, detail="session_id and message required")
    config = _config
    if not config.get("openai_api_key"):
        raise HTTPException(
            status_code=503,
            detail="Chat not configured",
        )
    try:
        reply, qualified, collected = chat_turn(config, req.session_id, req.message.strip())
    except Exception as e:
        logger.exception("Chat turn failed")
        raise HTTPException(status_code=500, detail="Chat error. Please try again.")

    # If qualified, create HubSpot contact once and return thank-you message
    hubspot_created = False
    session = get_session(req.session_id)
    already_submitted = session.get("submitted", False)
    has_token = bool((config.get("hubspot_access_token") or "").strip())
    if not has_token:
        logger.info("HubSpot: skipped (no hubspot_access_token set; set HUBSPOT_ACCESS_TOKEN on Vercel)")
    if qualified and not already_submitted and config.get("hubspot_enabled") and has_token:
        first = (collected.get("firstname") or "").strip() or "—"
        last = (collected.get("lastname") or "").strip() or "—"
        logger.info("HubSpot: creating contact for qualified lead firstname=%s lastname=%s", first[:20], last[:20])
        ok, res = create_contact(
            access_token=config["hubspot_access_token"],
            firstname=first,
            lastname=last,
            email=(collected.get("email") or "").strip(),
            phone=(collected.get("phone") or "").strip(),
            company=(collected.get("company") or "").strip(),
            address=_address_from_collected(collected),
            message=_message_from_collected(collected),
            lead_source=config.get("hubspot_lead_source", "Chatbot"),
            lead_status=config.get("hubspot_lead_status", "OPEN"),
        )
        if ok:
            mark_submitted(req.session_id)
            hubspot_created = True
            reply = config.get("thank_you_message", "Thanks for your enquiry. We'll be in touch within 24 hours.")
        else:
            logger.warning("HubSpot create failed: %s", res)
    elif qualified and already_submitted:
        reply = config.get("thank_you_message", "Thanks for your enquiry. We'll be in touch within 24 hours.")
    elif qualified and not has_token:
        reply = config.get("thank_you_message", "Thanks for your enquiry. We'll be in touch soon. Is there anything else I can help you with?")

    return ChatResponse(reply=reply, qualified=qualified, collected=collected, hubspot_created=hubspot_created)


@app.get("/")
def root():
    """Root route so GET / returns 200 (avoids 404 in Vercel logs)."""
    return {"service": "iFork Chatbot API", "health": "/health", "chat": "POST /chat"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
