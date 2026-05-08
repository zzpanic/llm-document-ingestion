"""FastAPI application for the document ingestion service.

Provides REST endpoints for uploading images, triggering extraction,
checking status, and downloading results. Uses background tasks for
asynchronous processing.

This module implements the API layer described in the implementation spec,
Section 7: FastAPI Application.

Recommended libraries:
    - fastapi>=0.115.0: Web framework with automatic OpenAPI docs
    - uvicorn[standard]>=0.34.0: ASGI server
    - jinja2>=3.1.4: HTML template rendering
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import aiofiles
from fastapi import (
    FastAPI,
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.extraction import extract_single_image
from app.assembler import assemble_document, create_zip_archive
from app.config import settings
from app.models import ProcessRequest, ProcessResponse, UploadResponse, UploadFileResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Template engine for HTML rendering
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# In-memory status tracker: file_id -> {state, markdown_length, error}
_status_tracker: dict[str, dict] = {}
_status_lock = asyncio.Lock()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


async def _process_files(file_ids: list[str]) -> None:
    """Background task that extracts markdown from queued file IDs.

    This function runs asynchronously in the background and updates
    the status tracker as each file is processed.

    Args:
        file_ids: List of file IDs to extract.
    """
    for file_id in file_ids:
        async with _status_lock:
            _status_tracker[file_id] = {"state": "processing"}

        image_path = await _find_image_file(file_id)
        if not image_path:
            async with _status_lock:
                _status_tracker[file_id] = {
                    "state": "failed",
                    "error": f"Image not found: {file_id}"
                }
            continue

        markdown = await extract_single_image(str(image_path))

        if markdown == "FAILED":
            async with _status_lock:
                _status_tracker[file_id] = {
                    "state": "failed",
                    "error": "Extraction returned FAILED"
                }
        else:
            extracted_path = settings.EXTRACTED_DIR / f"page_{file_id}.md"
            try:
                async with aiofiles.open(extracted_path, "w", encoding="utf-8") as f:
                    await f.write(markdown)

                async with _status_lock:
                    _status_tracker[file_id] = {
                        "state": "done",
                        "markdown_length": len(markdown)
                    }
            except IOError as e:
                logger.error(f"Failed to write extracted markdown for {file_id}: {e}")
                async with _status_lock:
                    _status_tracker[file_id] = {
                        "state": "failed",
                        "error": f"Failed to save extracted content: {e}"
                    }


async def _find_image_file(file_id: str) -> Path | None:
    """Find the image file for a given file_id, checking both .png and .jpg extensions.

    Args:
        file_id: The file ID to search for.

    Returns:
        Path to the image file if found, None otherwise.
    """
    for ext in [".png", ".jpg"]:
        image_path = settings.UPLOADS_DIR / f"{file_id}{ext}"
        if image_path.exists():
            return image_path
    return None


async def _cleanup_temp_files() -> None:
    """Periodically delete old temporary zip files."""
    while True:
        try:
            now = datetime.now()
            for f in settings.TEMP_DIR.glob("*.zip"):
                if now - datetime.fromtimestamp(f.stat().st_mtime) > timedelta(days=1):
                    f.unlink()
                    logger.info(f"Deleted old temp file: {f}")
        except Exception as e:
            logger.error(f"Error during temp cleanup: {e}")

        await asyncio.sleep(3600)  # Run cleanup every hour


@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_images(
    request: Request,
    files: List[UploadFile] = File(...)
) -> UploadResponse:
    """Upload document images for subsequent extraction.

    Accepts multiple image files (PNG/JPG), validates them, and stores
    them with unique IDs in the uploads directory.

    Args:
        request: FastAPI Request object (required for rate limiter).
        files: List of image file uploads. Supported formats: PNG, JPG.

    Returns:
        UploadResponse containing list of uploaded file info with IDs.

    Raises:
        HTTPException: If file type is unsupported or size exceeds limit.

    Example:
        # POST /upload with multipart/form-data
        # files=[page1.png, page2.png]
    """
    ext_map = {"image/png": ".png", "image/jpeg": ".jpg"}
    uploaded = []

    # First pass: validate all files before saving any
    for file in files:
        if file.content_type not in ext_map:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Allowed: PNG, JPG"
            )

        file_size = file.size or 0
        max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File size {file_size} exceeds maximum {max_bytes} bytes"
            )

    # Second pass: save all validated files
    for file in files:
        file_id = uuid.uuid4().hex
        ext = ext_map[file.content_type]
        file_path = settings.UPLOADS_DIR / f"{file_id}{ext}"

        try:
            content = await file.read()
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)
            uploaded.append(UploadFileResponse(id=file_id, filename=file.filename))
        except IOError as e:
            logger.error(f"Failed to save uploaded file {file_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to save uploaded file"
            )

    return UploadResponse(uploaded=uploaded)


@router.post("/process", response_model=ProcessResponse)
@limiter.limit("5/minute")
async def trigger_extraction(
    request: Request,
    background_tasks: BackgroundTasks,
    process_request: ProcessRequest
) -> ProcessResponse:
    """Trigger asynchronous extraction of uploaded images.

    Adds the specified file IDs to the processing queue and returns
    immediately. Actual extraction happens in the background.

    Args:
        request: FastAPI Request object (required for rate limiter).
        background_tasks: FastAPI BackgroundTasks for scheduling
            asynchronous extraction.
        process_request: Request body containing validated file_ids list.

    Returns:
        ProcessResponse with "processing_started" status.

    Raises:
        HTTPException: If file_ids are invalid.

    Example:
        # POST /process with {"file_ids": ["abc123...", "def456..."]}
    """
    file_ids = process_request.file_ids

    async with _status_lock:
        for fid in file_ids:
            _status_tracker[fid] = {"state": "pending"}

    background_tasks.add_task(_process_files, file_ids)

    return ProcessResponse(status="processing_started")


@router.get("/status", response_model=dict)
async def check_status() -> dict:
    """Retrieve extraction status for all tracked files.

    Returns the current state of every file ID that has been registered
    in the status tracker.

    Returns:
        Dictionary mapping file IDs to their status objects.

    Example:
        # GET /status
        # Returns: {"status": {"abc123": {"state": "done", ...}}}
    """
    return {"status": _status_tracker}


@router.get("/download/pages/{page_id}")
async def download_page(page_id: str) -> FileResponse:
    """Download the extracted markdown for a single page.

    Args:
        page_id: The unique file ID (UUID hex) of the page to download.

    Returns:
        Markdown file as an attachment download.

    Raises:
        HTTPException: If the page_id is invalid or file does not exist (404).

    Example:
        # GET /download/pages/abc123def456...
        # Returns: page_abc123def456....md as text/markdown
    """
    if not re.match(r"^[a-f0-9]{32}$", page_id):
        raise HTTPException(status_code=404, detail="Invalid page ID format")

    file_path = settings.EXTRACTED_DIR / f"page_{page_id}.md"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")

    if not str(file_path.resolve()).startswith(str(settings.EXTRACTED_DIR.resolve())):
        raise HTTPException(status_code=404, detail="Invalid page path")

    return FileResponse(file_path, filename=f"{page_id}.md", media_type="text/markdown")


@router.get("/download/document")
async def download_document() -> FileResponse:
    """Download the fully assembled document.

    Returns the merged markdown document containing all extracted pages.

    Raises:
        HTTPException: If the document has not been assembled yet (404).

    Example:
        # GET /download/document
        # Returns: document.md as text/markdown
    """
    file_path = settings.OUTPUT_DIR / "document.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(file_path, filename="document.md", media_type="text/markdown")


@router.get("/download/zip")
@limiter.limit("5/minute")
async def download_zip(request: Request) -> FileResponse:
    """Download a zip archive of all extracted files.

    Returns a zip file containing all page markdowns and the merged document.

    Note:
        The zip is created on-demand from cached extracted files.
        Zip files are automatically cleaned up after 24 hours.

    Raises:
        HTTPException: If no files are available for archiving (400).

    Example:
        # GET /download/zip
        # Returns: document_extraction.zip as application/zip
    """
    async with _status_lock:
        done_ids = [
            fid for fid, status in _status_tracker.items()
            if status.get("state") == "done"
        ]

    if not done_ids:
        raise HTTPException(status_code=400, detail="No extracted files to archive")

    zip_path_str = await create_zip_archive(done_ids)
    return FileResponse(zip_path_str, filename="document_extraction.zip", media_type="application/zip")


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


# Create FastAPI app instance
app = FastAPI(
    title="LLM Document Ingestion",
    description="Extract structured markdown from document images using multimodal LLMs",
    version="1.0"
)

app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.on_event("startup")
async def startup_event():
    """Initialize application startup tasks."""
    logger.info("Starting LLM Document Ingestion Service")
    logger.info(f"LM Studio endpoint: {settings.LM_STUDIO_ENDPOINT}")
    logger.info(f"Max image size: {settings.MAX_IMAGE_SIZE_MB} MB")
    asyncio.create_task(_cleanup_temp_files())


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on application shutdown."""
    logger.info("Shutting down LLM Document Ingestion Service")


# Mount static files
app_static_dir = Path(__file__).parent / "static"
if app_static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(app_static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)