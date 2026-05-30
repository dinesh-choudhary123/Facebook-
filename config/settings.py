"""
Configuration settings for Restaurant Social Media Automation.
Loads all settings from environment variables with sensible defaults.
"""

import os
import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# Load .env file from the project root
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"📄 Loaded environment from: {env_path}")
else:
    print(f"⚠️  No .env file found at: {env_path}")


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        # Base paths
        self.BASE_DIR = Path(__file__).resolve().parent.parent
        self.TEMP_DIR = Path(os.getenv("TEMP_DIR", self.BASE_DIR / "static" / "uploads"))
        self.OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", self.BASE_DIR / "static" / "outputs"))

        # Ensure directories exist
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # --- ComfyUI ---
        self.COMFYUI_HOST = os.getenv("COMFYUI_HOST", "http://127.0.0.1")
        self.COMFYUI_PORT = int(os.getenv("COMFYUI_PORT", "8188"))
        self.comfyui_base_url = f"{self.COMFYUI_HOST}:{self.COMFYUI_PORT}"

        # --- Caption Generation ---
        self.GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1")
        self.OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

        # --- Meta / Facebook ---
        self.META_APP_ID = os.getenv("META_APP_ID", "")
        self.META_APP_SECRET = os.getenv("META_APP_SECRET", "")
        self.META_PAGE_ID = os.getenv("META_PAGE_ID", "")
        self.META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")
        self.META_API_VERSION = os.getenv("META_API_VERSION", "v25.0")

        # --- App ---
        self.APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
        self.APP_PORT = int(os.getenv("APP_PORT", "8000"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def groq_available(self) -> bool:
        return bool(self.GROQ_API_KEY)

    @property
    def gemini_available(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def facebook_configured(self) -> bool:
        return bool(self.META_PAGE_ACCESS_TOKEN and self.META_PAGE_ID)

    def caption_provider(self) -> str:
        """Return the best available caption provider in priority order."""
        if self.groq_available:
            return "groq"
        if self.gemini_available:
            return "gemini"
        return "ollama"

    def get_missing_keys(self) -> list:
        """Return a list of missing but optional API keys for setup guidance."""
        missing = []
        if not self.GROQ_API_KEY:
            missing.append("GROQ_API_KEY")
        if not self.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        if not self.META_PAGE_ACCESS_TOKEN:
            missing.append("META_PAGE_ACCESS_TOKEN (or META_APP_ID + META_APP_SECRET)")
        return missing


# Global singleton
settings = Settings()


def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("restaurant-automation")
