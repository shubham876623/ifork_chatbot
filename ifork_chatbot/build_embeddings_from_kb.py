"""
Build embeddings.json from the knowledge base (no Chroma). For Vercel or when Chroma isn't installed.
Run from project root: python -m ifork_chatbot.build_embeddings_from_kb
Requires OPENAI_API_KEY. Writes embeddings.json at project root.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ifork_chatbot.config import load_config
from ifork_chatbot.rag import chunk_text, load_knowledge_base, embed_chunks
from openai import OpenAI


def main():
    config = load_config()
    api_key = (os.environ.get("OPENAI_API_KEY") or config.get("openai_api_key") or "").strip()
    if not api_key:
        print("ERROR: Set OPENAI_API_KEY in env or .env")
        sys.exit(1)
    kb_path = config.get("knowledge_base_path") or ROOT / "ifork_chatbot_knowledge_base.md"
    kb_path = Path(kb_path)
    if not kb_path.exists():
        print(f"ERROR: Knowledge base not found: {kb_path}")
        sys.exit(1)
    text = load_knowledge_base(kb_path)
    chunk_size = config.get("chunk_size", 500)
    overlap = config.get("chunk_overlap", 80)
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        print("ERROR: No chunks from knowledge base")
        sys.exit(1)
    client = OpenAI(api_key=api_key)
    model = config.get("embedding_model", "text-embedding-3-small")
    embeddings = embed_chunks(client, model, chunks)
    out = [{"text": c, "embedding": e} for c, e in zip(chunks, embeddings)]
    out_path = ROOT / "embeddings.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Wrote {len(out)} chunks to {out_path}")


if __name__ == "__main__":
    main()
