"""
Minimal RAG: chunk markdown, embed with OpenAI.
- EC2 / local: store and query via Chroma (build_index + query).
- Vercel: use pre-built embeddings.json + numpy (no Chroma dependency at runtime).
"""
import json
import re
from pathlib import Path
from typing import List

from openai import OpenAI


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> List[str]:
    """Split text into overlapping chunks (by characters)."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            break_at = text.rfind("\n\n", start, end + 1)
            if break_at == -1:
                break_at = text.rfind(". ", start, end + 1)
            if break_at == -1:
                break_at = text.rfind(" ", start, end + 1)
            if break_at > start:
                end = break_at + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if overlap < end - start else end
    return chunks


def load_knowledge_base(path: Path) -> str:
    """Read knowledge base file as plain text."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def embed_chunks(client: OpenAI, model: str, chunks: List[str]) -> List[List[float]]:
    """Get embeddings for chunks. OpenAI returns 1536-dim for text-embedding-3-small."""
    if not chunks:
        return []
    out = client.embeddings.create(input=chunks, model=model)
    return [item.embedding for item in sorted(out.data, key=lambda x: x.index)]


# --- Chroma path (EC2 / local) ---

def build_index(config: dict) -> int:
    """
    Load KB, chunk, embed, persist to Chroma. For EC2/local. Returns number of chunks indexed.
    """
    import chromadb
    from chromadb.config import Settings

    kb_path = config["knowledge_base_path"]
    if not isinstance(kb_path, Path):
        kb_path = Path(kb_path)
    if not kb_path.exists():
        raise FileNotFoundError(f"Knowledge base not found: {kb_path}")

    text = load_knowledge_base(kb_path)
    chunk_size = config.get("chunk_size", 500)
    overlap = config.get("chunk_overlap", 80)
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return 0

    api_key = config.get("openai_api_key")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)
    model = config.get("embedding_model", "text-embedding-3-small")
    embeddings = embed_chunks(client, model, chunks)

    persist_dir = config["chroma_persist_dir"]
    if not isinstance(persist_dir, Path):
        persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    client_chroma = chromadb.PersistentClient(path=str(persist_dir), settings=Settings(anonymized_telemetry=False))
    try:
        client_chroma.delete_collection("ifork_kb")
    except Exception:
        pass
    collection = client_chroma.create_collection(name="ifork_kb", metadata={"description": "iFork knowledge base"})
    ids = [f"c{i}" for i in range(len(chunks))]
    collection.add(ids=ids, embeddings=embeddings, documents=chunks)
    return len(chunks)


# --- Embeddings JSON path (Vercel; no Chroma) ---

_embeddings_cache: List[dict] | None = None


def _load_embeddings_json(path: Path) -> List[dict]:
    """Load embeddings.json; cache in module for reuse (e.g. serverless cold start)."""
    global _embeddings_cache
    if _embeddings_cache is not None:
        return _embeddings_cache
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    _embeddings_cache = [x for x in data if isinstance(x, dict) and "text" in x and "embedding" in x]
    return _embeddings_cache


def _query_embeddings_json(config: dict, question: str, top_k: int) -> List[str]:
    """Use embeddings.json + numpy for similarity. Used on Vercel (no Chroma)."""
    import numpy as np

    path = config.get("embeddings_json_path")
    if not path or not Path(path).exists():
        return []
    rows = _load_embeddings_json(Path(path))
    if not rows:
        return []
    api_key = config.get("openai_api_key")
    if not api_key:
        return []
    client = OpenAI(api_key=api_key)
    model = config.get("embedding_model", "text-embedding-3-small")
    q_emb = client.embeddings.create(input=[question], model=model)
    query_vec = np.array(q_emb.data[0].embedding, dtype=np.float32)
    top_k = min(top_k, 20, len(rows))
    scores = []
    for row in rows:
        emb = row.get("embedding")
        if not emb:
            scores.append(-1e9)
            continue
        vec = np.array(emb, dtype=np.float32)
        score = float(np.dot(query_vec, vec))
        scores.append(score)
    idxs = np.argsort(scores)[::-1][:top_k]
    return [rows[i]["text"] for i in idxs if rows[i].get("text")]


def _query_chroma(config: dict, question: str, top_k: int) -> List[str]:
    """Query Chroma (EC2/local). Chroma imported only here so Vercel can skip it."""
    import chromadb
    from chromadb.config import Settings

    api_key = config.get("openai_api_key")
    if not api_key:
        return []
    client = OpenAI(api_key=api_key)
    model = config.get("embedding_model", "text-embedding-3-small")
    q_emb = client.embeddings.create(input=[question], model=model)
    query_embedding = q_emb.data[0].embedding

    persist_dir = config["chroma_persist_dir"]
    if not isinstance(persist_dir, Path):
        persist_dir = Path(persist_dir)
    if not persist_dir.exists():
        return []
    client_chroma = chromadb.PersistentClient(path=str(persist_dir), settings=Settings(anonymized_telemetry=False))
    try:
        collection = client_chroma.get_collection("ifork_kb")
    except Exception:
        return []
    results = collection.query(query_embeddings=[query_embedding], n_results=min(top_k, 20))
    docs = results.get("documents")
    if not docs or not docs[0]:
        return []
    return list(docs[0])


def query(config: dict, question: str, top_k: int = 5) -> List[str]:
    """
    Embed question, retrieve top-k chunks.
    - On Vercel: use embeddings.json + numpy (no Chroma).
    - Else: use Chroma if available; otherwise embeddings.json if present.
    """
    import os

    top_k = min(top_k, 20)
    json_path = config.get("embeddings_json_path")
    json_path = Path(json_path) if json_path else None
    use_json = os.environ.get("VERCEL") == "1" or (json_path and json_path.exists())

    if use_json and json_path and json_path.exists():
        return _query_embeddings_json(config, question, top_k)
    persist_dir = config.get("chroma_persist_dir")
    if persist_dir and Path(persist_dir).exists():
        return _query_chroma(config, question, top_k)
    if json_path and json_path.exists():
        return _query_embeddings_json(config, question, top_k)
    return []
