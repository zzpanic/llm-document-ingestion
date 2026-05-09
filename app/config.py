"""Configuration management for the document ingestion service.

Loads settings from environment variables with sensible defaults.
Call ``load_dotenv()`` before importing this module (done here at
module level) so that a ``.env`` file is picked up automatically.
"""

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file if present (local development)
load_dotenv()


class Settings:
    """Application settings loaded from environment variables at startup.

    Instantiated once as the module-level ``settings`` singleton.
    Raises ``ValueError`` on invalid configuration so problems surface
    immediately at startup rather than during a request.
    """

    def __init__(self) -> None:
        self.LM_STUDIO_ENDPOINT: str = os.getenv(
            "LM_STUDIO_ENDPOINT",
            "http://localhost:1234",
        )
        self.LITELM_API_MODEL: str = os.getenv("LITELM_API_MODEL", "qwen3.5-9b")
        self.MAX_IMAGES_PER_BATCH: int = int(os.getenv("MAX_IMAGES_PER_BATCH", "100"))
        self.MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))

        # Absolute paths derived from the project root (two levels up from this file)
        self.BASE_DIR: Path = Path(__file__).resolve().parent.parent
        self.UPLOADS_DIR: Path = self.BASE_DIR / "uploads"
        self.EXTRACTED_DIR: Path = self.BASE_DIR / "extracted"
        self.OUTPUT_DIR: Path = self.BASE_DIR / "output"
        self.TEMP_DIR: Path = self.BASE_DIR / "temp"

        self._validate()
        self._ensure_directories()
        logger.info(
            f"Settings initialised — endpoint: {self.LM_STUDIO_ENDPOINT}, "
            f"model: {self.LITELM_API_MODEL}"
        )

    def _validate(self) -> None:
        """Raise ValueError for any obviously invalid setting."""
        parsed = urlparse(self.LM_STUDIO_ENDPOINT)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                f"Invalid LM_STUDIO_ENDPOINT: '{self.LM_STUDIO_ENDPOINT}' "
                f"— must be a full HTTP URL, e.g. http://localhost:1234"
            )
        if not self.LITELM_API_MODEL.strip():
            raise ValueError("LITELM_API_MODEL cannot be empty")
        if self.MAX_IMAGES_PER_BATCH < 1:
            raise ValueError("MAX_IMAGES_PER_BATCH must be >= 1")
        if self.MAX_IMAGE_SIZE_MB < 1:
            raise ValueError("MAX_IMAGE_SIZE_MB must be >= 1")

        logger.info(
            f"Config validated — max images: {self.MAX_IMAGES_PER_BATCH}, "
            f"max size: {self.MAX_IMAGE_SIZE_MB} MB"
        )

    def _ensure_directories(self) -> None:
        """Create runtime data directories if they do not already exist."""
        for directory in (
            self.UPLOADS_DIR,
            self.EXTRACTED_DIR,
            self.OUTPUT_DIR,
            self.TEMP_DIR,
        ):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Directory ready: {directory}")
            except OSError as e:
                logger.error(f"Cannot create directory {directory}: {e}")
                raise


settings = Settings()
