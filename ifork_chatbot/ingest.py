"""One-off ingest: build Chroma index from knowledge base."""
import sys
from pathlib import Path

# Ensure project root on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ifork_chatbot.config import load_config
from ifork_chatbot.rag import build_index


def main():
    config = load_config()
    if not config.get("openai_api_key"):
        print("ERROR: Set OPENAI_API_KEY in env or .env")
        sys.exit(1)
    n = build_index(config)
    print(f"Indexed {n} chunks. Chroma stored in: {config['chroma_persist_dir']}")


if __name__ == "__main__":
    main()
