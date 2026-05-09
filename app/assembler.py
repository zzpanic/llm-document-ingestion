"""Document assembly — merges per-page markdown files and creates zip archives.

``assemble_document`` concatenates extracted pages into a single markdown
file. It is not called by the web UI workflow but is available for manual
or scripted use.

``create_zip_archive`` packages extracted pages into a timestamped zip and
is called automatically at the end of each extraction batch.
"""

import asyncio
import logging
import zipfile
from pathlib import Path

import aiofiles

from app.config import settings

logger = logging.getLogger(__name__)


async def assemble_document(file_ids: list[str]) -> str:
    """Merge per-page markdown files into a single document.

    Concatenates extracted pages in the order given, separated by
    ``--- Page: {id} ---`` markers for traceability.

    Note:
        This function is not called by the web UI. It is available for
        manual or scripted post-processing.

    Args:
        file_ids: Ordered list of file IDs. Each must have a corresponding
            ``page_{id}.md`` file in ``settings.EXTRACTED_DIR``.

    Returns:
        Absolute path to the assembled ``output/document.md`` file.

    Raises:
        ValueError: If ``file_ids`` is empty.
        IOError: If the output file cannot be written.
    """
    if not file_ids:
        raise ValueError("Cannot assemble an empty file list")

    output_path = settings.OUTPUT_DIR / "document.md"
    pages_dir = settings.EXTRACTED_DIR
    missing: list[str] = []
    count = 0

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise IOError(f"Cannot create output directory: {e}") from e

    async with aiofiles.open(output_path, "w", encoding="utf-8") as out:
        await out.write("# Extracted Document\n\n")
        for page_id in file_ids:
            page_path = pages_dir / f"page_{page_id}.md"
            if not page_path.exists():
                logger.warning(f"Page {page_id} not found, skipping")
                missing.append(page_id)
                continue
            try:
                await out.write(f"\n--- Page: {page_id} ---\n\n")
                async with aiofiles.open(page_path, "r", encoding="utf-8") as src:
                    content = await src.read()
                await out.write(content)
                await out.write("\n")
                count += 1
            except IOError as e:
                logger.error(f"Failed to read page {page_id}: {e}")
                missing.append(page_id)

    if missing:
        logger.warning(
            f"Assembled {count} pages; {len(missing)} missing: {missing}"
        )
    else:
        logger.info(f"Assembled {count} pages → {output_path}")

    return str(output_path)


def _build_zip(
    zip_path: Path,
    pages_dir: Path,
    file_ids: list[str],
    output_doc: Path,
    filename_map: dict[str, str] | None = None,
) -> int:
    """Synchronous zip builder — intended to be run via ``asyncio.to_thread``.

    Args:
        zip_path: Destination path for the zip file.
        pages_dir: Directory containing ``page_{id}.md`` files.
        file_ids: IDs of pages to include.
        output_doc: Path to ``document.md``; included if it exists.
        filename_map: Optional mapping of file_id to original filename.
            When provided, files inside the zip use the original stem
            (e.g. ``AS3610-1995_7.md``) instead of ``page_{id}.md``.

    Returns:
        Number of page files successfully added to the archive.
    """
    added = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for page_id in file_ids:
            page_path = pages_dir / f"page_{page_id}.md"
            if not page_path.exists():
                continue
            try:
                original = (filename_map or {}).get(page_id, "")
                archive_name = (
                    (Path(original).stem + ".md") if original else f"page_{page_id}.md"
                )
                archive.write(page_path, f"pages/{archive_name}")
                added += 1
            except IOError as e:
                logger.warning(f"Could not add page {page_id} to archive: {e}")

        if output_doc.exists():
            try:
                archive.write(output_doc, "document.md")
            except IOError as e:
                logger.warning(f"Could not add document.md to archive: {e}")

    return added


async def create_zip_archive(
    file_ids: list[str],
    filename_map: dict[str, str] | None = None,
    zip_basename: str = "extraction",
) -> str:
    """Create a timestamped zip archive of extracted page files.

    The zip filename is ``{YYYYMMDD-HHMMSS}_{zip_basename}.zip``, e.g.
    ``20260509-093521_AS3610-1995.zip``. The synchronous zip work runs in
    a thread pool so the event loop is not blocked.

    Args:
        file_ids: IDs of done pages to include.
        filename_map: Optional mapping of file_id to original upload filename,
            used to name files inside the zip with their original stems.
        zip_basename: Used in the zip filename. Typically the stem of the
            first file's original name.

    Returns:
        Absolute path to the created zip file as a string.

    Raises:
        IOError: If the zip file cannot be created.
    """
    from datetime import datetime as _dt

    timestamp = _dt.now().strftime("%Y%m%d-%H%M%S")
    zip_path = settings.TEMP_DIR / f"{timestamp}_{zip_basename}.zip"
    pages_dir = settings.EXTRACTED_DIR
    output_doc = settings.OUTPUT_DIR / "document.md"

    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise IOError(f"Cannot create temp directory: {e}") from e

    try:
        added = await asyncio.to_thread(
            _build_zip, zip_path, pages_dir, file_ids, output_doc, filename_map
        )
        logger.info(f"Created zip: {zip_path.name} ({added} pages)")
    except IOError as e:
        logger.error(f"Failed to create zip archive: {e}")
        raise

    return str(zip_path)
