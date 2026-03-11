"""
Export existing Chroma collection to embeddings.json (for Vercel deploy).
Run from project root: python -m ifork_chatbot.export_embeddings
Requires chromadb and existing chroma_ifork/ (e.g. after python -m ifork_chatbot.ingest).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    persist_dir = ROOT / "chroma_ifork"
    if not persist_dir.exists():
        print("ERROR: chroma_ifork/ not found. Run: python -m ifork_chatbot.ingest")
        sys.exit(1)
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        print("ERROR: pip install chromadb")
        sys.exit(1)
    client = chromadb.PersistentClient(path=str(persist_dir), settings=Settings(anonymized_telemetry=False))
    try:
        coll = client.get_collection("ifork_kb")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    data = coll.get(include=["documents", "embeddings"])
    if not data or not data["documents"]:
        print("ERROR: No documents in collection")
        sys.exit(1)
    docs = data["documents"]
    embs = data.get("embeddings")
    if embs is None:
        embs = []
    # Chroma may return list of lists or list of arrays; convert to list for JSON
    out = [
        {"text": doc, "embedding": list(emb) if hasattr(emb, "__iter__") and not isinstance(emb, str) else emb}
        for doc, emb in zip(docs, embs)
    ]
    out_path = ROOT / "embeddings.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Wrote {len(out)} chunks to {out_path}")


if __name__ == "__main__":
    main()
