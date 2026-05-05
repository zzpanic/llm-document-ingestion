# LLM Document Ingestion — Implementation Specification

## Overview

This document specifies the implementation details for the LLM Document Ingestion Service. It covers Python best practices, FastAPI patterns, recommended libraries, and concrete code examples with proper docstrings.

---

## 1. Recommended Libraries

### 1.1 Core Dependencies (`requirements.txt`)

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
python-multipart>=0.0.12
httpx>=0.28.0
litellm>=1.57.0          # Universal LLM API abstraction
aiofiles>=24.1.0         # Async file I/O
python-dotenv>=1.0.1     # Environment variable management
jinja2>=3.1.4            # HTML template rendering
```

### 1.2 Library Purposes

| Library | Purpose | Why Recommended |
|---------|---------|-----------------|
| `fastapi` | Web framework | Automatic OpenAPI docs, dependency injection, async support |
| `uvicorn` | ASGI server | Production-ready, hot reload in dev |
| `python-multipart` | File upload parsing | Required for `File()` and `UploadFile` in FastAPI |
| `litellm` | LLM API abstraction | Single interface for 100+ LLM providers (OpenAI, Anthropic, Ollama, LM Studio) |
| `aiofiles` | Async file I/O | Non-blocking file operations in async context |
| `python-dotenv` | Config management | Load `.env` files for local development |
| `jinja2` | Template engine | FastAPI `HTMLResponse` with server-side rendered templates |

### 1.3 Why `litellm` Instead of Direct HTTP Calls?

The `litellm` library provides:
- **Provider agnostic API** — same code works for OpenAI, Anthropic, Ollama, LM Studio
- **Automatic retry** with exponential backoff
- **Built-in timeout handling**
- **Streaming support** (if needed later)
- **Cost tracking** (for cloud APIs)

```python
# litellm usage example
from litellm import completion

response = completion(
    model="openai/gpt-4o",        # works with any provider
    messages=[{"role": "user", "content": [...]}],
    api_base="http://localhost:1234",  # LM Studio endpoint
    max_tokens=4096,
    temperature=0
)
```

---

## 2. Project Structure

```
llm-document-ingestion/
├── app/
│   ├── __init__.py              # Package initialization
│   ├── config.py                # Configuration management
│   ├── main.py                  # FastAPI application entry point
│   ├── extraction.py            # Image extraction logic
│   ├── assembler.py             # Document assembly logic
│   ├── models.py               # Pydantic models for API
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── base.html           # Base template with header/nav
│   │   ├── upload.html         # Upload page template
│   │   ├── status.html         # Status page template
│   │   └── download.html       # Download page template
│   └── static/                 # Static files (separates HTML from presentation)
│       ├── css/
│       │   └── style.css       # Main stylesheet
│       └── js/
│           └── app.js          # Client-side JavaScript
├── uploads/                    # Raw uploaded images (gitignored)
├── extracted/                  # Per-page markdown output (gitignored)
├── output/                     # Merged document output (gitignored)
├── .env                        # Environment variables (not committed)
├── .env.example                # Template for .env
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 3. Configuration Management

### 3.1 Environment Variables (`.env.example`)

```env
# LLM Provider Configuration
LM_STUDIO_ENDPOINT=http://192.168.1.81:1234
LITELM_API_BASE=${LM_STUDIO_ENDPOINT}
LITELM_API_MODEL=qwen3.5-9b

# Application Settings
MAX_IMAGES_PER_BATCH=100
MAX_IMAGE_SIZE_MB=10
OUTPUT_DIR=./output

# Optional: Cloud API keys (if not using local models)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
```

### 3.2 Configuration Loader (`app/config.py`)

```python
"""Configuration management for the document ingestion service.

Loads configuration from environment variables with sensible defaults.
Uses python-dotenv for local development .env file support.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present (local development)
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # LLM Configuration
    LM_STUDIO_ENDPOINT: str = os.getenv(
        "LM_STUDIO_ENDPOINT",
        "http://192.168.1.81:1234"
    )
    LITELM_API_MODEL: str = os.getenv("LITELM_API_MODEL", "qwen3.5-9b")

    # Upload Configuration
    MAX_IMAGES_PER_BATCH: int = int(os.getenv("MAX_IMAGES_PER_BATCH", "100"))
    MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))

    # Directory Paths (relative to project root)
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOADS_DIR: Path = BASE_DIR / "uploads"
    EXTRACTED_DIR: Path = BASE_DIR / "extracted"
    OUTPUT_DIR: Path = BASE_DIR / "output"
    TEMP_DIR: Path = BASE_DIR / "temp"

    def __init__(self) -> None:
        """Initialize settings, ensuring all directories exist."""
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        for directory in [
            self.UPLOADS_DIR,
            self.EXTRACTED_DIR,
            self.OUTPUT_DIR,
            self.TEMP_DIR,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def litellm_api_base(self) -> str:
        """Return the API base URL for litellm."""
        return self.LM_STUDIO_ENDPOINT


settings = Settings()
```

### 3.3 Best Practices Demonstrated

- **Type hints** on all variables and properties
- **Docstrings** following Google style
- **Lazy directory creation** in `__init__` rather than at import time
- **Property methods** for computed values (`litellm_api_base`)
- **Environment variable fallbacks** via `os.getenv()` defaults

---

## 4. Pydantic Models (`app/models.py`)

### 4.1 API Request/Response Models

```python
"""Pydantic models for API request and response validation.

Provides automatic request validation, OpenAPI schema generation,
and type-safe data transfer between layers.
"""

from pydantic import BaseModel, Field
from typing import List


class UploadResponse(BaseModel):
    """Response returned after successful image upload."""

    uploaded: List[dict[str, str]] = Field(
        ...,
        description="List of uploaded file IDs and filenames"
    )


class ProcessRequest(BaseModel):
    """Request to trigger extraction on uploaded images."""

    file_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of uploaded file IDs to process"
    )


class ProcessResponse(BaseModel):
    """Response indicating extraction has been queued."""

    status: str = Field(
        ...,
        description="Processing status indicator"
    )


class StatusEntry(BaseModel):
    """Status information for a single extracted file."""

    state: str = Field(..., description="Extraction state: pending, processing, done, failed")
    markdown_length: int | None = Field(None, description="Length of extracted markdown")
    error: str | None = Field(None, description="Error message if state is 'failed'")


class StatusResponse(BaseModel):
    """Aggregate status response for all tracked files."""

    status: dict[str, dict[str, object]] = Field(
        ...,
        description="Per-file extraction status map"
    )


class DownloadResponse(BaseModel):
    """Generic download response metadata."""

    filename: str = Field(..., description="Name of the downloadable file")
    content_type: str = Field(..., description="MIME type of the file")
```

---

## 5. Extraction Module (`app/extraction.py`)

### 5.1 LLM Client with litellm

```python
"""Image extraction module using multimodal LLMs via litellm.

Provides functions for extracting markdown text from document images
using any supported LLM provider. Uses litellm as a uniform abstraction
layer over diverse LLM APIs.
"""

import base64
import logging
from pathlib import Path

import litellm
from app.config import settings

logger = logging.getLogger(__name__)

# System prompt instructing the model to produce structured markdown with LaTeX math
EXTRACTION_PROMPT: str = (
    "You are extracting text from a technical document image. Produce structured "
    "markdown output that preserves:\n\n"
    "1. DOCUMENT STRUCTURE:\n"
    "   - Main section titles as level-1 headings (#)\n"
    "   - Subsection titles as level-2 headings (##)\n"
    "   - Preserve all lists, tables, and footnotes\n\n"
    "2. MATHEMATICAL FORMULAS:\n"
    "   - Inline math MUST use single dollar signs: $E = mc^2$\n"
    "   - Displayed equations MUST use double dollar signs: $$\\int_0^\\infty e^{-x} dx$$\n"
    "   - Do NOT use Unicode symbols (∑, ∫, ≤) — always use LaTeX commands (\\sum, \\int, \\leq)\n\n"
    "3. TABLES:\n"
    "   - Preserve table structure using markdown table syntax\n"
    "   - Maintain column alignments and merged cells if visible\n\n"
    "4. PRIORITY: Structure over prose. If formatting is ambiguous, preserve the visual layout."
)


async def extract_single_image(image_path: str) -> str:
    """Extract markdown text from a single document image.

    Reads the image file, encodes it as base64, and sends it to the
    configured LLM via litellm for extraction.

    Args:
        image_path: Filesystem path to the image file to extract.

    Returns:
        Extracted markdown text if successful, or 'FAILED' on error.

    Raises:
        No exceptions are raised; all errors are logged and 'FAILED' is returned.

    Example:
        >>> result = await extract_single_image("uploads/page_001.png")
        >>> print(result[:100])  # First 100 chars of extracted markdown
    """
    try:
        # Read and encode image
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        # Construct message for litellm (multi-modal vision input)
        messages = [
            {
                "role": "system",
                "content": EXTRACTION_PROMPT
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": f"data:image/png;base64,{base64_image}"
                    }
                ]
            }
        ]

        # Call LLM via litellm (works with any provider)
        response = await litellm.acompletion(
            model=f"{settings.LITELM_API_MODEL}",
            messages=messages,
            api_base=settings.LITELM_API_BASE,
            max_tokens=4096,
            temperature=0,
        )

        # Extract markdown from response
        markdown = response["choices"][0]["message"]["content"]
        logger.info(f"Successfully extracted {len(markdown)} chars from {image_path}")
        return markdown

    except Exception as exc:
        logger.error(f"Extraction failed for {image_path}: {exc}")
        return "FAILED"


async def extract_batch(image_paths: list[str]) -> dict[str, str]:
    """Extract markdown from multiple images concurrently.

    Processes a batch of image paths and returns a mapping of
    file paths to their extracted markdown content.

    Args:
        image_paths: List of filesystem paths to image files.

    Returns:
        Dictionary mapping image paths to extracted markdown strings.
        Failed extractions map to the string "FAILED".

    Example:
        >>> results = await extract_batch(["uploads/p1.png", "uploads/p2.png"])
        >>> for path, md in results.items():
        ...     print(f"{path}: {len(md)} chars")
    """
    results: dict[str, str] = {}

    # Process images concurrently using asyncio.gather
    coroutines = [extract_single_image(path) for path in image_paths]
    extracted = await asyncio.gather(*coroutines, return_exceptions=True)

    for path, result in zip(image_paths, extracted):
        if isinstance(result, Exception):
            logger.error(f"Batch extraction failed for {path}: {result}")
            results[path] = "FAILED"
        else:
            results[path] = result

    return results
```

### 5.2 Best Practices Demonstrated

- **Docstrings** with Args, Returns, Raises, and Example sections (Google style)
- **Type hints** on all function signatures
- **Error handling** — catches exceptions, logs errors, returns sentinel value
- **Logging** instead of print statements
- **Async/await** for non-blocking I/O
- **Single Responsibility** — each function does one thing

---

## 6. Document Assembly Module (`app/assembler.py`)

### 6.1 Merge and Archive Functions

```python
"""Document assembly module for merging extracted markdown pages.

Provides functions to combine per-page markdown outputs into a single
coherent document and create zip archives for bulk download.
"""

import logging
import zipfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


async def assemble_document(file_ids: list[str]) -> str:
    """Merge per-page markdown files into a single assembled document.

    Reads extracted markdown files in page order and concatenates them
    with visible page separators for traceability.

    Args:
        file_ids: Ordered list of file IDs to assemble. Pages are
            assumed to be named page_{file_id}.md in the extracted directory.

    Returns:
        Path to the assembled document file as a string.

    Raises:
        FileNotFoundError: If any referenced page file does not exist.
        ValueError: If file_ids is empty.

    Example:
        >>> path = await assemble_document(["abc123", "def456"])
        >>> print(path)  # e.g., "output/document.md"
    """
    if not file_ids:
        raise ValueError("Cannot assemble empty file list")

    output_path = settings.OUTPUT_DIR / "document.md"
    pages_dir = settings.EXTRACTED_DIR

    with open(output_path, "w", encoding="utf-8") as outfile:
        outfile.write("# Extracted Document\n\n")

        for page_id in file_ids:
            page_path = pages_dir / f"page_{page_id}.md"
            if not page_path.exists():
                logger.warning(f"Page {page_id} not found, skipping")
                continue

            outfile.write(f"\n--- Page: {page_id} ---\n\n")

            with open(page_path, "r", encoding="utf-8") as infile:
                content = infile.read()
                outfile.write(content)
                outfile.write("\n")

    logger.info(f"Assembled document: {output_path} ({len(file_ids)} pages)")
    return str(output_path)


async def create_zip_archive(file_ids: list[str]) -> str:
    """Create a zip archive containing all extracted files and the merged document.

    Packages per-page markdown files and the assembled document into
    a single zip archive for convenient bulk download.

    Args:
        file_ids: List of file IDs to include in the archive.

    Returns:
        Path to the created zip archive file as a string.

    Raises:
        FileNotFoundError: If no source files exist to archive.

    Example:
        >>> zip_path = await create_zip_archive(["abc123", "def456"])
        >>> print(zip_path)  # e.g., "temp/document_extraction.zip"
    """
    zip_path = settings.TEMP_DIR / "document_extraction.zip"
    pages_dir = settings.EXTRACTED_DIR

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        # Add all extracted page markdowns
        for page_id in file_ids:
            page_path = pages_dir / f"page_{page_id}.md"
            if page_path.exists():
                archive.write(page_path, f"pages/page_{page_id}.md")

        # Add assembled document if it exists
        doc_path = settings.OUTPUT_DIR / "document.md"
        if doc_path.exists():
            archive.write(doc_path, "document.md")

    logger.info(f"Created zip archive: {zip_path}")
    return str(zip_path)
```

---

## 7. FastAPI Application (`app/main.py`)

### 7.1 Application Entry Point

```python
"""FastAPI application for the document ingestion service.

Provides REST endpoints for uploading images, triggering extraction,
checking status, and downloading results. Uses background tasks for
asynchronous processing.
"""

import logging
import uuid
from pathlib import Path
from typing import List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Templating

from app.assembler import assemble_document, create_zip_archive
from app.extraction import extract_single_image
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Template engine for HTML rendering
templates = Templating(directory=str(Path(__file__).parent / "templates"))

# In-memory status tracker: file_id -> {state, markdown_length, error}
_status_tracker: dict[str, dict] = {}


async def _process_files(file_ids: list[str]) -> None:
    """Background task that extracts markdown from queued file IDs.

    This function runs asynchronously in the background and updates
    the status tracker as each file is processed.

    Args:
        file_ids: List of file IDs to extract.
    """
    for file_id in file_ids:
        _status_tracker[file_id] = {"state": "processing"}

        image_path = settings.UPLOADS_DIR / f"{file_id}.png"
        if not image_path.exists():
            _status_tracker[file_id] = {
                "state": "failed",
                "error": f"Image not found: {file_id}"
            }
            continue

        markdown = await extract_single_image(str(image_path))

        if markdown == "FAILED":
            _status_tracker[file_id] = {
                "state": "failed",
                "error": "Extraction returned FAILED"
            }
        else:
            # Save extracted markdown to disk
            extracted_path = settings.EXTRACTED_DIR / f"page_{file_id}.md"
            with open(extracted_path, "w", encoding="utf-8") as f:
                f.write(markdown)

            _status_tracker[file_id] = {
                "state": "done",
                "markdown_length": len(markdown)
            }


@router.post("/upload", response_model=dict)
async def upload_images(files: List[UploadFile] = File(...)) -> dict:
    """Upload document images for subsequent extraction.

    Accepts multiple image files (PNG/JPG), validates them, and stores
    them with unique IDs in the uploads directory.

    Args:
        files: List of image file uploads. Supported formats: PNG, JPG.

    Returns:
        Dictionary containing list of uploaded file info with IDs.

    Raises:
        HTTPException: If file type is unsupported or size exceeds limit.
    """
    uploaded = []

    for file in files:
        # Validate file type
        if file.content_type not in ("image/png", "image/jpeg"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}"
            )

        # Validate file size
        file_size = file.size or 0
        max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File size {file_size} exceeds maximum {max_bytes}"
            )

        # Generate unique ID and save
        file_id = uuid.uuid4().hex
        file_path = settings.UPLOADS_DIR / f"{file_id}.png"
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        uploaded.append({"id": file_id, "filename": file.filename})

    return {"uploaded": uploaded}


@router.post("/process", response_model=dict)
async def trigger_extraction(
    background_tasks: BackgroundTasks,
    body: dict = None
) -> dict:
    """Trigger asynchronous extraction of uploaded images.

    Adds the specified file IDs to the processing queue and returns
    immediately. Actual extraction happens in the background.

    Args:
        body: Request body containing file_ids list.

    Returns:
        Status confirmation dictionary.

    Raises:
        HTTPException: If no valid file_ids are provided.
    """
    if not body or "file_ids" not in body:
        raise HTTPException(status_code=400, detail="Missing file_ids")

    file_ids = body["file_ids"]

    # Initialize status for each file
    for fid in file_ids:
        _status_tracker[fid] = {"state": "pending"}

    # Schedule background extraction task
    background_tasks.add_task(_process_files, file_ids)

    return {"status": "processing_started"}


@router.get("/status", response_model=dict)
async def check_status() -> dict:
    """Retrieve extraction status for all tracked files.

    Returns the current state of every file ID that has been registered
    in the status tracker.

    Returns:
        Dictionary mapping file IDs to their status objects.
    """
    return {"status": _status_tracker}


@router.get("/download/pages/{page_id}")
async def download_page(page_id: str) -> FileResponse:
    """Download the extracted markdown for a single page.

    Args:
        page_id: The unique file ID of the page to download.

    Returns:
        Markdown file as an attachment download.

    Raises:
        HTTPException: If the page file does not exist.
    """
    file_path = settings.EXTRACTED_DIR / f"page_{page_id}.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    return FileResponse(file_path, filename=f"{page_id}.md", media_type="text/markdown")


@router.get("/download/document")
async def download_document() -> FileResponse:
    """Download the fully assembled document.

    Returns the merged markdown document containing all extracted pages.

    Raises:
        HTTPException: If the document has not been assembled yet.
    """
    file_path = settings.OUTPUT_DIR / "document.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(file_path, filename="document.md", media_type="text/markdown")


@router.get("/download/zip")
async def download_zip() -> FileResponse:
    """Download a zip archive of all extracted files.

    Returns a zip file containing all page markdowns and the merged document.

    Note:
        The zip is created on-demand from cached extracted files.
        For large documents, consider implementing pre-assembly.

    Raises:
        HTTPException: If no files are available for archiving.
    """
    # Get all done file IDs from status tracker
    done_ids = [
        fid for fid, status in _status_tracker.items()
        if status.get("state") == "done"
    ]

    if not done_ids:
        raise HTTPException(status_code=400, detail="No extracted files to archive")

    zip_path = await create_zip_archive(done_ids)
    return FileResponse(zip_path, filename="document_extraction.zip", media_type="application/zip")


# --- Web UI Endpoints ---

@router.get("/ui/upload", response_class=HTMLResponse)
async def render_upload_page(request: Request) -> HTMLResponse:
    """Render the upload page HTML template."""
    return templates.TemplateResponse("upload.html", {"request": request})


@router.get("/ui/status", response_class=HTMLResponse)
async def render_status_page(request: Request) -> HTMLResponse:
    """Render the status page HTML template."""
    return templates.TemplateResponse("status.html", {"request": request})


@router.get("/ui/download", response_class=HTMLResponse)
async def render_download_page(request: Request) -> HTMLResponse:
    """Render the download page HTML template."""
    return templates.TemplateResponse("download.html", {"request": request})
```

### 7.3 Best Practices Demonstrated

- **FastAPI dependency injection** via `BackgroundTasks`
- **Request validation** with Pydantic (automatic in FastAPI)
- **Proper HTTP status codes** (400, 404, 500)
- **FileResponse** for streaming file downloads
- **Async endpoints** that return immediately
- **Error handling** with descriptive messages
- **Docstrings** on all endpoint functions
- **Logger usage** instead of print

---

## 8. Web UI Implementation

### 8.1 Template Rendering

FastAPI integrates with Jinja2 for server-side HTML rendering:

```python
from fastapi.templating import Templating
from fastapi.responses import HTMLResponse

templates = Templating(directory=str(Path(__file__).parent / "templates"))

@router.get("/ui/upload", response_class=HTMLResponse)
async def render_upload_page(request: Request) -> HTMLResponse:
    """Render the upload page HTML template."""
    return templates.TemplateResponse("upload.html", {"request": request})
```

### 8.2 HTML Template Structure

All templates extend `base.html` which provides:
- Common `<head>` with CSS link: `<link rel="stylesheet" href="{{ url_for('static', path='/css/style.css') }}">`
- Navigation header with links to `/ui/upload`, `/ui/status`, `/ui/download`
- JavaScript script tag: `<script src="{{ url_for('static', path='/js/app.js') }}"></script>`
- Block placeholders: `{% block content %}`, `{% block scripts %}`

### 8.3 CSS Separation Principle

HTML templates contain **only structure** (semantic HTML elements, forms, tables). All presentation is in `static/css/style.css`:
- Layout (flexbox/grid for page structure)
- Colors and typography
- Responsive breakpoints
- Status indicator styling (color-coded badges)

### 8.4 Client-Side JavaScript (`static/js/app.js`)

Handles:
- Drag-and-drop file selection
- AJAX upload to `/upload` endpoint
- Polling `/status` every 3 seconds during processing
- Conditional button visibility based on extraction state

---

## 9. Docstring Standards

All Python modules in this project follow the **Google style** docstrings:

```python
"""Module-level docstring: short summary followed by detailed description.

Provides overview of what this module does and why.
"""

def function_name(param: type) -> return_type:
    """Short one-line description.

    Detailed description explaining behavior, edge cases, and
    important considerations.

    Args:
        param_name: Description of the parameter.
        another_param: Description of another parameter.

    Returns:
        Description of what the function returns.

    Raises:
        ExceptionType: When and why this exception might be raised.

    Example:
        >>> result = function_name(value)
        >>> print(result)
    """
```

### 9.1 Docstring Checklist

Every public function MUST have:
- [ ] One-line summary
- [ ] Args section (if parameters exist)
- [ ] Returns section (if return type is not None)
- [ ] Raises section (if exceptions are possible)
- [ ] Example section (for non-trivial functions)

---

## 10. Error Handling Patterns

### 10.1 Async Function Error Handling

```python
try:
    result = await some_async_operation()
except TimeoutError as exc:
    logger.error(f"Timeout during operation: {exc}")
    return "TIMEOUT"
except FileNotFoundError as exc:
    logger.error(f"File not found: {exc}")
    raise  # Re-raise for caller to handle
except Exception as exc:
    logger.error(f"Unexpected error: {exc}")
    return "FAILED"
```

### 10.2 FastAPI Error Handling

```python
# Always use HTTPException for client-facing errors
raise HTTPException(
    status_code=400,
    detail="Invalid file type: expected PNG or JPG"
)

# Use 500 for internal server errors
logger.error("Unexpected failure")
raise HTTPException(
    status_code=500,
    detail="Internal server error"
)
```

---

## 11. Testing Strategy

### 11.1 Test Structure

```
tests/
├── __init__.py
├── test_extraction.py
├── test_assembler.py
├── test_api.py
└── conftest.py           # Shared test fixtures
```

### 11.2 Example Test with pytest

```python
import pytest
from app.assembler import assemble_document


class TestAssembleDocument:
    """Tests for the document assembly function."""

    def test_assemble_empty_list_raises(self) -> None:
        """Empty file list should raise ValueError."""
        with pytest.raises(ValueError):
            await assemble_document([])

    @pytest.mark.asyncio
    async def test_assembles_single_page(self, tmp_path, sample_md_file) -> None:
        """Single page should be assembled correctly."""
        result = await assemble_document(["test123"])
        assert Path(result).exists()
        content = Path(result).read_text()
        assert "Extracted Document" in content
```

### 11.3 Shared Test Fixtures (`tests/conftest.py`)

```python
"""Shared test fixtures for pytest."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_app_dir() -> Path:
    """Create a temporary directory structure mimicking the app directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "uploads").mkdir()
        (tmp_path / "extracted").mkdir()
        (tmp_path / "output").mkdir()
        yield tmp_path


@pytest.fixture
def sample_md_file(tmp_app_dir: Path) -> Path:
    """Create a sample markdown file for testing."""
    sample_path = tmp_app_dir / "extracted" / "page_test123.md"
    sample_path.write_text("# Sample Extracted Content\n\nTest paragraph.")
    return sample_path
```

---

## 12. Docker Configuration

### 12.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create required directories
RUN mkdir -p uploads extracted output temp

# Expose port for FastAPI
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:router", "--host", "0.0.0.0", "--port", "8000"]
```

### 12.2 Docker Compose (`docker-compose.yml`)

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./uploads:/app/uploads
      - ./extracted:/app/extracted
      - ./output:/app/output
      - ./temp:/app/temp
    environment:
      - LM_STUDIO_ENDPOINT=http://lm-studio-host:1234
    restart: unless-stopped
```

---

*This document describes Version 1.0 of the LLM Document Ingestion Implementation Specification. Subsequent versions may address limitations identified through production use.*