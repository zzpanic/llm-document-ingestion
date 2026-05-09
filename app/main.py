"""FastAPI application for the document ingestion service.

Provides REST endpoints for uploading images, triggering extraction,
checking status, previewing and downloading results. Uses FastAPI
background tasks for non-blocking extraction.
"""

import asyncio
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import aiofiles
import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.assembler import create_zip_archive
from app.config import settings
from app.extraction import extract_image_batch
from app.models import ProcessRequest, ProcessResponse, UploadFileResponse, UploadResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Inject version from VERSION file into every template as {{ app_version }}
_version_file = settings.BASE_DIR / "VERSION"
templates.env.globals["app_version"] = (
    _version_file.read_text(encoding="utf-8").strip() if _version_file.exists() else "dev"
)

# In-memory state — reset on restart; not safe for multi-process deployments
_status_tracker: dict[str, dict] = {}   # file_id → {state, markdown_length, error}
_status_lock = asyncio.Lock()
_filename_map: dict[str, str] = {}       # file_id → original upload filename

limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

async def _process_files(file_ids: list[str]) -> None:
    """Extract markdown from each queued file and update the status tracker.

    Runs as a FastAPI BackgroundTask. Processes files sequentially so that
    LM Studio is not overwhelmed. A zip is created automatically when the
    batch completes.

    Args:
        file_ids: Ordered list of IDs previously saved by ``upload_images``.
    """
    # Sort by original filename so pages are processed in document order
    file_ids = sorted(file_ids, key=lambda fid: _filename_map.get(fid, fid))

    total = len(file_ids)
    num_batches = (total + settings.BATCH_SIZE - 1) // settings.BATCH_SIZE
    logger.info(
        f"Extraction batch started: {total} file(s) in {num_batches} batch(es) "
        f"of up to {settings.BATCH_SIZE}"
    )
    done = failed = 0
    prior_context = ""

    batches = [
        file_ids[i:i + settings.BATCH_SIZE]
        for i in range(0, total, settings.BATCH_SIZE)
    ]

    for batch_num, batch_ids in enumerate(batches, 1):
        batch_start = (batch_num - 1) * settings.BATCH_SIZE + 1
        batch_end = batch_start + len(batch_ids) - 1
        range_label = f"{batch_start}-{batch_end}"
        logger.info(f"[Batch {batch_num}/{num_batches}] Pages {range_label}")

        async with _status_lock:
            for fid in batch_ids:
                _status_tracker[fid] = {"state": "processing"}

        # Resolve image paths; mark any missing files as failed immediately
        resolved: list[tuple[str, str]] = []
        for fid in batch_ids:
            image_path = await _find_image_file(fid)
            if image_path:
                resolved.append((fid, str(image_path)))
            else:
                logger.warning(f"  {fid[:8]}: image not found")
                async with _status_lock:
                    _status_tracker[fid] = {"state": "failed", "error": "Image not found"}
                failed += 1

        if not resolved:
            logger.warning(f"[Batch {batch_num}] No images found, skipping")
            continue

        markdown = await extract_image_batch(
            [p for _, p in resolved], prior_context=prior_context
        )

        if markdown == "FAILED":
            logger.warning(f"[Batch {batch_num}] Extraction failed")
            async with _status_lock:
                for fid, _ in resolved:
                    _status_tracker[fid] = {"state": "failed", "error": "Extraction returned FAILED"}
            failed += len(resolved)
        else:
            out_path = settings.EXTRACTED_DIR / f"pages_{range_label}.md"
            try:
                async with aiofiles.open(out_path, "w", encoding="utf-8") as f:
                    await f.write(markdown)
                async with _status_lock:
                    for fid, _ in resolved:
                        _status_tracker[fid] = {
                            "state": "done",
                            "batch_file": out_path.name,
                            "markdown_length": len(markdown),
                        }
                done += len(resolved)
                prior_context = markdown
                logger.info(
                    f"[Batch {batch_num}] Done → {out_path.name} ({len(markdown):,} chars)"
                )
            except IOError as e:
                logger.error(f"[Batch {batch_num}] Failed to save output — {e}")
                async with _status_lock:
                    for fid, _ in resolved:
                        _status_tracker[fid] = {
                            "state": "failed",
                            "error": f"Failed to save extracted content: {e}",
                        }
                failed += len(resolved)

    logger.info(
        f"Extraction batch complete: {done} done, {failed} failed out of {total}"
    )

    # Auto-create zip — collect unique batch files in sorted page order
    done_ids = [
        fid for fid in file_ids
        if _status_tracker.get(fid, {}).get("state") == "done"
    ]
    if done_ids:
        seen_bf: set[str] = set()
        ordered_batch_files: list[str] = []
        for fid in file_ids:
            bf = _status_tracker.get(fid, {}).get("batch_file")
            if bf and bf not in seen_bf:
                seen_bf.add(bf)
                ordered_batch_files.append(bf)

        first_original = _filename_map.get(done_ids[0], "")
        zip_basename = Path(first_original).stem if first_original else "extraction"
        try:
            zip_path = await create_zip_archive(
                done_ids,
                filename_map=_filename_map,
                zip_basename=zip_basename,
                batch_files=ordered_batch_files or None,
            )
            logger.info(f"Auto-created zip: {Path(zip_path).name}")
        except Exception as e:
            logger.warning(f"Auto-zip creation failed: {e}")


async def _find_image_file(file_id: str) -> Path | None:
    """Return the uploaded image path for a file ID, or None if not found.

    Checks for both .png and .jpg extensions.
    """
    for ext in (".png", ".jpg"):
        path = settings.UPLOADS_DIR / f"{file_id}{ext}"
        if path.exists():
            return path
    return None


async def _cleanup_temp_files() -> None:
    """Background loop that deletes zip files older than 24 hours every hour."""
    while True:
        try:
            cutoff = datetime.now() - timedelta(days=1)
            for f in settings.TEMP_DIR.glob("*.zip"):
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    logger.info(f"Deleted stale temp file: {f.name}")
        except Exception as e:
            logger.error(f"Error during temp cleanup: {e}")
        await asyncio.sleep(3600)


async def _stream_file(path: Path, chunk_size: int = 65536):
    """Yield file contents in chunks using aiofiles for reliable streaming."""
    async with aiofiles.open(path, "rb") as f:
        while chunk := await f.read(chunk_size):
            yield chunk


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_images(
    request: Request,
    files: list[UploadFile] = File(...),
) -> UploadResponse:
    """Save uploaded images and return their assigned IDs.

    Validates all files before saving any. Supported formats: PNG, JPG.
    Maximum size per file is controlled by ``MAX_IMAGE_SIZE_MB``.

    Args:
        request: Required by the slowapi rate limiter.
        files: One or more image files as multipart/form-data.

    Returns:
        List of ``{id, filename}`` entries, one per saved file.

    Raises:
        HTTPException 400: Unsupported content type or file too large.
        HTTPException 500: I/O error while saving a file.
    """
    ext_map = {"image/png": ".png", "image/jpeg": ".jpg"}
    uploaded = []

    # Validate all files before saving any to avoid partial uploads
    for file in files:
        if file.content_type not in ext_map:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported type: {file.content_type}. Allowed: PNG, JPG",
            )
        file_size = file.size or 0
        max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename!r} exceeds the {settings.MAX_IMAGE_SIZE_MB} MB limit",
            )

    for file in files:
        file_id = uuid.uuid4().hex
        file_path = settings.UPLOADS_DIR / f"{file_id}{ext_map[file.content_type]}"
        try:
            content = await file.read()
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)
            size_kb = len(content) / 1024
            logger.info(f"Uploaded {file_id[:8]} — {file.filename} ({size_kb:.0f} KB)")
            _filename_map[file_id] = file.filename
            uploaded.append(UploadFileResponse(id=file_id, filename=file.filename))
        except IOError as e:
            logger.error(f"Failed to save {file_id[:8]}: {e}")
            raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    logger.info(f"Upload complete: {len(uploaded)} file(s) saved")
    return UploadResponse(uploaded=uploaded)


@router.post("/process", response_model=ProcessResponse)
@limiter.limit("5/minute")
async def trigger_extraction(
    request: Request,
    background_tasks: BackgroundTasks,
    process_request: ProcessRequest,
) -> ProcessResponse:
    """Queue extraction for a set of uploaded files and return immediately.

    File IDs are validated by the ``ProcessRequest`` Pydantic model before
    reaching this function. Extraction runs as a background task.

    Args:
        request: Required by the slowapi rate limiter.
        background_tasks: FastAPI dependency used to schedule the extraction.
        process_request: Validated request body containing ``file_ids``.

    Returns:
        ``{"status": "processing_started"}`` once the task is queued.
    """
    file_ids = process_request.file_ids
    async with _status_lock:
        for fid in file_ids:
            _status_tracker[fid] = {"state": "pending"}

    endpoint = settings.LM_STUDIO_ENDPOINT.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    logger.info(
        f"Processing queued: {len(file_ids)} file(s) "
        f"using {settings.LITELM_API_MODEL} @ {endpoint}"
    )
    background_tasks.add_task(_process_files, file_ids)
    return ProcessResponse(status="processing_started")


@router.get("/status")
async def check_status() -> dict:
    """Return the current extraction state for all tracked files.

    The tracker is reset when the service restarts. States:
    ``pending`` → ``processing`` → ``done`` | ``failed``.
    """
    return {"status": _status_tracker}


@router.get("/download/pages/{page_id}")
async def download_page(page_id: str) -> StreamingResponse:
    """Download a single extracted page as a markdown file.

    The download filename uses the original upload name (e.g.
    ``AS3610-1995_7.md``), falling back to ``{page_id}.md`` if the
    original name is no longer in the in-memory map.

    Args:
        page_id: 32-character hex UUID assigned at upload time.

    Raises:
        HTTPException 404: Invalid ID format or file does not exist.
    """
    if not re.match(r"^[a-f0-9]{32}$", page_id):
        raise HTTPException(status_code=404, detail="Invalid page ID format")
    # Batched extraction stores output as pages_{N}-{M}.md; look that up first.
    batch_file = _status_tracker.get(page_id, {}).get("batch_file")
    if batch_file:
        file_path = settings.EXTRACTED_DIR / batch_file
        download_name = batch_file
    else:
        file_path = settings.EXTRACTED_DIR / f"page_{page_id}.md"
        original = _filename_map.get(page_id, "")
        download_name = (Path(original).stem + ".md") if original else f"{page_id}.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    if not str(file_path.resolve()).startswith(str(settings.EXTRACTED_DIR.resolve())):
        raise HTTPException(status_code=404, detail="Invalid page path")
    return StreamingResponse(
        _stream_file(file_path),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "Content-Length": str(file_path.stat().st_size),
        },
    )


@router.get("/download/document")
async def download_document() -> StreamingResponse:
    """Download the assembled multi-page document.

    Note:
        ``assembler.assemble_document`` is not called automatically by the
        web UI, so this endpoint returns 404 unless the file has been
        created externally (e.g. by calling the assembler directly).

    Raises:
        HTTPException 404: Document has not been assembled.
    """
    file_path = settings.OUTPUT_DIR / "document.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    return StreamingResponse(
        _stream_file(file_path),
        media_type="text/markdown",
        headers={
            "Content-Disposition": 'attachment; filename="document.md"',
            "Content-Length": str(file_path.stat().st_size),
        },
    )


@router.get("/download/zip")
@limiter.limit("5/minute")
async def download_zip(request: Request) -> StreamingResponse:
    """Create and immediately download a zip of all completed pages.

    Generates a timestamped zip in ``temp/`` and streams it to the client.
    Zips older than 24 hours are cleaned up automatically.

    Args:
        request: Required by the slowapi rate limiter.

    Raises:
        HTTPException 400: No pages have completed extraction yet.
    """
    async with _status_lock:
        done_ids = [
            fid for fid, s in _status_tracker.items() if s.get("state") == "done"
        ]
    if not done_ids:
        raise HTTPException(status_code=400, detail="No extracted files to archive")
    # Sort by original filename and collect unique batch files in page order
    done_ids = sorted(done_ids, key=lambda fid: _filename_map.get(fid, fid))
    seen_bf: set[str] = set()
    batch_files: list[str] = []
    for fid in done_ids:
        bf = _status_tracker.get(fid, {}).get("batch_file")
        if bf and bf not in seen_bf:
            seen_bf.add(bf)
            batch_files.append(bf)
    original = _filename_map.get(done_ids[0], "")
    zip_basename = Path(original).stem if original else "extraction"
    zip_path_str = await create_zip_archive(
        done_ids,
        filename_map=_filename_map,
        zip_basename=zip_basename,
        batch_files=batch_files or None,
    )
    zip_path = Path(zip_path_str)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )


@router.get("/temp/zips")
async def list_temp_zips() -> dict:
    """List all zip archives currently in the temp directory.

    Returns:
        ``{"zips": [{filename, size_kb, created}, ...]}`` sorted newest first.
    """
    zips = []
    for f in sorted(
        settings.TEMP_DIR.glob("*.zip"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    ):
        stat = f.stat()
        zips.append({
            "filename": f.name,
            "size_kb": round(stat.st_size / 1024, 1),
            "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return {"zips": zips}


@router.post("/temp/clear")
async def clear_temp_zips() -> dict:
    """Delete all zip archives from the temp directory.

    Returns:
        ``{"deleted": N}`` with the count of files removed.
    """
    deleted = 0
    for f in settings.TEMP_DIR.glob("*.zip"):
        try:
            f.unlink()
            deleted += 1
        except OSError as e:
            logger.warning(f"Could not delete {f.name}: {e}")
    logger.info(f"Cleared {deleted} zip file(s) from temp directory")
    return {"deleted": deleted}


@router.get("/download/zip/{filename}")
async def download_named_zip(filename: str) -> StreamingResponse:
    """Download a specific named zip archive from the temp directory.

    Args:
        filename: Basename of the zip file (e.g.
            ``20260509-093521_AS3610-1995.zip``). Must match
            ``[\\w-]+\\.zip``.

    Raises:
        HTTPException 404: File does not exist or name is invalid.
    """
    if not re.match(r"^[\w\-]+\.zip$", filename):
        raise HTTPException(status_code=404, detail="Invalid filename")
    file_path = settings.TEMP_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Zip not found")
    if not str(file_path.resolve()).startswith(str(settings.TEMP_DIR.resolve())):
        raise HTTPException(status_code=404, detail="Invalid path")
    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=filename,
    )


@router.get("/preview/pages/{page_id}", response_class=PlainTextResponse)
async def preview_page(page_id: str) -> PlainTextResponse:
    """Return extracted markdown as plain text for in-browser rendering.

    Used by the Preview page's JavaScript to fetch page content without
    triggering a file download (unlike ``/download/pages/{page_id}``).

    Args:
        page_id: 32-character hex UUID.

    Raises:
        HTTPException 404: Invalid ID or file does not exist.
    """
    if not re.match(r"^[a-f0-9]{32}$", page_id):
        raise HTTPException(status_code=404, detail="Invalid page ID")
    file_path = settings.EXTRACTED_DIR / f"page_{page_id}.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    return PlainTextResponse(file_path.read_text(encoding="utf-8"))


@router.get("/")
async def root() -> RedirectResponse:
    """Redirect bare root URL to the upload page."""
    return RedirectResponse(url="/ui/upload")


# ---------------------------------------------------------------------------
# Web UI template routes
# ---------------------------------------------------------------------------

@router.get("/ui/upload", response_class=HTMLResponse)
async def render_upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "upload.html")


@router.get("/ui/status", response_class=HTMLResponse)
async def render_status_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "status.html")


@router.get("/ui/preview", response_class=HTMLResponse)
async def render_preview_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "preview.html")


@router.get("/ui/download", response_class=HTMLResponse)
async def render_download_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "download.html")


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

async def _probe_llm_endpoint() -> None:
    """Check whether the configured LLM endpoint is reachable at startup."""
    base = settings.LM_STUDIO_ENDPOINT.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    probe_url = f"{base}/models"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(probe_url)
        logger.info(f"  LM Studio : reachable ({probe_url} → HTTP {r.status_code})")
    except Exception as exc:
        logger.warning(f"  LM Studio : NOT reachable at {probe_url} — {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown tasks for the application."""
    logger.info("=" * 60)
    logger.info("LLM Document Ingestion Service starting")
    logger.info(f"  Model    : {settings.LITELM_API_MODEL}")
    logger.info(f"  Endpoint : {settings.LM_STUDIO_ENDPOINT}")
    logger.info(f"  Max size : {settings.MAX_IMAGE_SIZE_MB} MB per image")
    logger.info(f"  Max batch: {settings.MAX_IMAGES_PER_BATCH} images")
    logger.info(f"  Uploads  : {settings.UPLOADS_DIR}")
    logger.info(f"  Extracted: {settings.EXTRACTED_DIR}")
    await _probe_llm_endpoint()
    logger.info("=" * 60)
    cleanup_task = asyncio.create_task(_cleanup_temp_files())
    yield
    cleanup_task.cancel()
    logger.info("Shutting down")


app = FastAPI(
    title="LLM Document Ingestion",
    description="Extract structured markdown from document images using multimodal LLMs",
    version="0.1.0",
    lifespan=lifespan,
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

app_static_dir = Path(__file__).parent / "static"
if app_static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(app_static_dir)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
