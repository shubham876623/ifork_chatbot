"""
Minimal RAG: chunk markdown, embed with OpenAI, store/query Chroma.
No LangChain – direct OpenAI + Chroma for low latency.
"""
import re
from pathlib import Path
from typing import List

import chromadb
from chromadb.config import Settings
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
            # Try to break at paragraph or sentence
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


def build_index(config: dict) -> int:
    """
    Load KB, chunk, embed, persist to Chroma. Returns number of chunks indexed.
    """
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


def query(config: dict, question: str, top_k: int = 5) -> List[str]:
    """
    Embed question, search Chroma, return list of relevant chunk texts.
    """
    api_key = config.get("openai_api_key")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
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
