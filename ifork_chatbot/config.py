"""Load chatbot config from YAML and env."""
import os
import shutil
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Project root (parent of ifork_chatbot package)
ROOT = Path(__file__).resolve().parent.parent
# Load .env from project root and from ifork_chatbot/ (so either location works)
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "ifork_chatbot" / ".env")
CONFIG_PATH = ROOT / "chatbot_config.yaml"


def _chroma_dir_for_vercel() -> Path:
    """On Vercel, filesystem is read-only; copy bundled Chroma DB to /tmp once."""
    if os.environ.get("VERCEL") != "1":
        return ROOT / "chroma_ifork"
    tmp_dir = Path("/tmp/chroma_ifork")
    if tmp_dir.exists():
        return tmp_dir
    src = ROOT / "chroma_ifork"
    if src.exists():
        try:
            shutil.copytree(src, tmp_dir)
        except Exception:
            pass
    return tmp_dir if tmp_dir.exists() else src


def load_config():
    """Load chatbot_config.yaml and override with env where applicable."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Paths
    cfg["knowledge_base_path"] = ROOT / cfg.get("knowledge_base_path", "ifork_chatbot_knowledge_base.md")
    cfg["chroma_persist_dir"] = _chroma_dir_for_vercel()
    cfg["embeddings_json_path"] = ROOT / cfg.get("embeddings_json_path", "embeddings.json")

    # Env overrides
    cfg["openai_api_key"] = (os.environ.get("OPENAI_API_KEY") or "").strip()
    cfg["hubspot_access_token"] = (os.environ.get("HUBSPOT_ACCESS_TOKEN") or "").strip()
    if not cfg["hubspot_access_token"] and os.environ.get("HUBSPOT_ACCESS_TOKEN") is None:
        # Allow loading from lead scraper config for local dev (optional)
        try:
            scrap = ROOT / "lead_scraping_config.yaml"
            if scrap.exists():
                with open(scrap, "r", encoding="utf-8") as f:
                    scrap_cfg = yaml.safe_load(f) or {}
                t = (scrap_cfg.get("hubspot_access_token") or "").strip()
                if t and cfg.get("hubspot_enabled", True):
                    cfg["hubspot_access_token"] = t
        except Exception:
            pass

    return cfg
