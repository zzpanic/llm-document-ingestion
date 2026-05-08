"""Configuration management for the document ingestion service.

Loads configuration from environment variables with sensible defaults.
Uses python-dotenv for local development .env file support.

Recommended libraries:
    - python-dotenv>=1.0.1: Environment variable management
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
    """Application settings loaded from environment variables.

    All settings support environment variable overrides with sensible
    defaults for local development.
    """

    def __init__(self) -> None:
        """Initialize settings, validating configuration and ensuring directories exist."""
        self.LM_STUDIO_ENDPOINT = os.getenv(
            "LM_STUDIO_ENDPOINT",
            "http://localhost:1234"
        )
        self.LITELM_API_MODEL = os.getenv("LITELM_API_MODEL", "qwen3.5-9b")

        self.MAX_IMAGES_PER_BATCH = int(os.getenv("MAX_IMAGES_PER_BATCH", "100"))
        self.MAX_IMAGE_SIZE_MB = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))

        # Directory Paths (relative to project root)
        self.BASE_DIR = Path(__file__).resolve().parent.parent
        self.UPLOADS_DIR = self.BASE_DIR / "uploads"
        self.EXTRACTED_DIR = self.BASE_DIR / "extracted"
        self.OUTPUT_DIR = self.BASE_DIR / "output"
        self.TEMP_DIR = self.BASE_DIR / "temp"

        self._validate_configuration()
        self._ensure_directories()
        logger.info(f"Settings initialized - endpoint: {self.LM_STUDIO_ENDPOINT}, model: {self.LITELM_API_MODEL}")

    def _validate_configuration(self) -> None:
        """Validate configuration values are reasonable."""
        # Validate endpoint URL
        parsed = urlparse(self.LM_STUDIO_ENDPOINT)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(
                f"Invalid LM_STUDIO_ENDPOINT: '{self.LM_STUDIO_ENDPOINT}' — must be a valid HTTP URL "
                f"(e.g. http://localhost:1234)"
            )
        logger.info(f"Validated LM Studio endpoint: {self.LM_STUDIO_ENDPOINT}")

        # Validate model name is non-empty
        if not self.LITELM_API_MODEL.strip():
            raise ValueError("LITELM_API_MODEL cannot be empty")

        # Validate image constraints
        if self.MAX_IMAGES_PER_BATCH < 1:
            raise ValueError("MAX_IMAGES_PER_BATCH must be >= 1")
        if self.MAX_IMAGE_SIZE_MB < 1:
            raise ValueError("MAX_IMAGE_SIZE_MB must be >= 1")

        logger.info(f"Validated constraints - max images: {self.MAX_IMAGES_PER_BATCH}, max size: {self.MAX_IMAGE_SIZE_MB}MB")

    def _ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        for directory in [
            self.UPLOADS_DIR,
            self.EXTRACTED_DIR,
            self.OUTPUT_DIR,
            self.TEMP_DIR,
        ]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Ensured directory exists: {directory}")
            except OSError as e:
                logger.error(f"Failed to create directory {directory}: {e}")
                raise

    @property
    def litellm_api_base(self) -> str:
        """Return the API base URL for litellm."""
        return self.LM_STUDIO_ENDPOINT


settings = Settings()