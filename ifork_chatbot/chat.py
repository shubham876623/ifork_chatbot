"""
Chat logic: session store, RAG retrieval, OpenAI reply, structured extraction, qualification.
Accuracy: strict system prompt – answer only from context; do not invent pricing/areas.
"""
import json
import re
from openai import OpenAI

# Session store: session_id -> { "collected": {...}, "messages": [...] }
_sessions: dict[str, dict] = {}

# Fields we extract from conversation
COLLECTED_KEYS = ("firstname", "lastname", "email", "phone", "company", "suburb", "pallet_count", "timeline", "notes")

SYSTEM_PROMPT = """You are the iFork Mackay chat assistant. You only help with iFork's delivery and transport services in the Mackay region (pallet delivery, Moffett forklift truck, pricing, areas, booking).

Rules:
- Answer ONLY using the CONTEXT below. If the answer is not in the context, say you don't have that detail and suggest they call 0429 355 123 or email hello@iforkmackay.com.au.
- Do NOT invent pricing, areas, or policies. Only state what is in the context.
- Keep replies friendly, clear, and concise.
- If the user asks about something unrelated to iFork (e.g. weather, other businesses), say: "I can only help with iFork delivery and quotes. Would you like a quote or have a question about our services?"
- When the user wants a quote or booking, collect: first name, last name, email, phone, and optionally company, suburb, pallet count, timeline. Ask for one or two things at a time.
- When you have collected at least first name, last name, and (email OR phone), you may say you have everything and will pass their enquiry to the team. Do not make up that you have submitted until you actually have name + (email or phone).

At the end of your reply, if you have learned or confirmed any of these from the user in this turn, output exactly one line:
EXTRACT: {"firstname":"...", "lastname":"...", "email":"...", "phone":"...", "company":"...", "suburb":"...", "pallet_count":"...", "timeline":"...", "notes":"..."}
Only include keys for which you have a real value. Use empty string for missing. No other text on that line."""


def get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {"collected": {k: "" for k in COLLECTED_KEYS}, "messages": [], "submitted": False}
    return _sessions[session_id]


def mark_submitted(session_id: str) -> None:
    if session_id in _sessions:
        _sessions[session_id]["submitted"] = True


def _parse_extract(reply: str) -> dict[str, str]:
    """Parse EXTRACT: {...} line from assistant reply. Return only valid non-empty values."""
    out = {}
    m = re.search(r"EXTRACT:\s*(\{.*?\})\s*$", reply, re.DOTALL)
    if not m:
        return out
    try:
        raw = json.loads(m.group(1))
        for k in COLLECTED_KEYS:
            if k in raw and raw[k] is not None:
                v = str(raw[k]).strip()
                if v and v.lower() not in ("nan", "none"):
                    out[k] = v
    except (json.JSONDecodeError, TypeError):
        pass
    return out


def _merge_collected(session: dict, extracted: dict) -> None:
    for k, v in extracted.items():
        if k in COLLECTED_KEYS and v:
            session["collected"][k] = v


def is_qualified(collected: dict) -> bool:
    """Qualified = at least firstname + (email or phone)."""
    first = (collected.get("firstname") or "").strip()
    last = (collected.get("lastname") or "").strip()
    name_ok = bool(first or last)
    email = (collected.get("email") or "").strip()
    phone = (collected.get("phone") or "").strip()
    return name_ok and (bool(email) or bool(phone))


def _strip_extract_line(reply: str) -> str:
    """Remove the EXTRACT: line from reply so we don't show it to the user."""
    return re.sub(r"\n?EXTRACT:\s*\{.*?\}\s*$", "", reply, flags=re.DOTALL).strip()


def _build_messages(context_chunks: list[str], history: list[dict], user_message: str) -> list[dict]:
    user_content = user_message
    if context_chunks:
        context_block = "\n\n---\n\n".join(context_chunks)
        user_content = f"Context (use only this to answer):\n\n{context_block}\n\n---\n\nUser: {user_message}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-10:]:  # last 10 exchanges
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_content})
    return messages


def chat_turn(
    config: dict,
    session_id: str,
    user_message: str,
) -> tuple[str, bool, dict]:
    """
    Process one user message. Returns (reply_text, qualified, collected).
    If qualified, caller should create HubSpot contact and then return thank_you_message.
    """
    session = get_session(session_id)
    collected = session["collected"]
    history = session["messages"]

    # Retrieve context from RAG
    top_k = config.get("retrieve_top_k", 5)
    try:
        from ifork_chatbot.rag import query as rag_query
        chunks = rag_query(config, user_message, top_k=top_k)
    except Exception:
        chunks = []

    messages = _build_messages(chunks, history, user_message)
    api_key = config.get("openai_api_key")
    if not api_key:
        return "Sorry, the chat service is not configured. Please call 0429 355 123 or email hello@iforkmackay.com.au.", False, collected

    client = OpenAI(api_key=api_key)
    model = config.get("chat_model", "gpt-4o-mini")
    try:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.3, max_tokens=600)
        reply = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return "Something went wrong. Please try again or contact us on 0429 355 123.", False, collected

    # Append to history (without EXTRACT in stored content)
    history.append({"role": "user", "content": user_message})
    reply_clean = _strip_extract_line(reply)
    history.append({"role": "assistant", "content": reply})

    # Extract and merge
    extracted = _parse_extract(reply)
    _merge_collected(session, extracted)
    collected = session["collected"]

    qualified = is_qualified(collected)
    return reply_clean, qualified, collected
