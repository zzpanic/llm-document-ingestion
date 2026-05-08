"""Document assembly module for merging extracted markdown pages.

Provides functions to combine per-page markdown outputs into a single
coherent document and create zip archives for bulk download.

This module implements the document assembly step described in the algorithm
specification, Phase 4: Document Assembly.

Recommended libraries:
    - zipfile (stdlib): For creating zip archives
    - aiofiles>=24.1.0: Async file I/O
"""

import asyncio
import logging
import zipfile
from pathlib import Path

import aiofiles

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
        ValueError: If file_ids is empty.
        IOError: If the output document cannot be written.

    Example:
        >>> path = await assemble_document(["abc123", "def456"])  # doctest: +SKIP
        >>> print(path)  # doctest: +SKIP
    """
    if not file_ids:
        raise ValueError("Cannot assemble empty file list")

    output_path = settings.OUTPUT_DIR / "document.md"
    pages_dir = settings.EXTRACTED_DIR
    missing_pages = []
    assembled_count = 0

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create output directory: {e}")
        raise IOError(f"Cannot create output directory: {e}")

    try:
        async with aiofiles.open(output_path, "w", encoding="utf-8") as outfile:
            await outfile.write("# Extracted Document\n\n")

            for page_id in file_ids:
                page_path = pages_dir / f"page_{page_id}.md"
                if not page_path.exists():
                    logger.warning(f"Page {page_id} not found, skipping")
                    missing_pages.append(page_id)
                    continue

                try:
                    await outfile.write(f"\n--- Page: {page_id} ---\n\n")
                    async with aiofiles.open(page_path, "r", encoding="utf-8") as infile:
                        content = await infile.read()
                    await outfile.write(content)
                    await outfile.write("\n")
                    assembled_count += 1
                except IOError as e:
                    logger.error(f"Failed to read page {page_id}: {e}")
                    missing_pages.append(page_id)
                    continue

    except IOError as e:
        logger.error(f"Failed to write assembled document: {e}")
        raise

    if missing_pages:
        logger.warning(f"Assembled {assembled_count} pages, {len(missing_pages)} missing: {missing_pages}")
    else:
        logger.info(f"Successfully assembled document: {output_path} ({assembled_count} pages)")

    return str(output_path)


def _build_zip(zip_path: Path, pages_dir: Path, file_ids: list[str], output_doc: Path) -> int:
    """Synchronous helper that builds the zip archive; run via asyncio.to_thread."""
    added_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for page_id in file_ids:
            page_path = pages_dir / f"page_{page_id}.md"
            if page_path.exists():
                try:
                    archive.write(page_path, f"pages/page_{page_id}.md")
                    added_count += 1
                except IOError as e:
                    logger.warning(f"Failed to add page {page_id} to archive: {e}")

        if output_doc.exists():
            try:
                archive.write(output_doc, "document.md")
            except IOError as e:
                logger.warning(f"Failed to add assembled document to archive: {e}")

    return added_count


async def create_zip_archive(file_ids: list[str]) -> str:
    """Create a zip archive containing all extracted files and the merged document.

    Packages per-page markdown files and the assembled document into
    a single zip archive for convenient bulk download. The synchronous
    zipfile work runs in a thread pool to avoid blocking the event loop.

    Args:
        file_ids: List of file IDs to include in the archive.

    Returns:
        Path to the created zip archive file as a string.

    Raises:
        IOError: If the zip archive cannot be created.

    Example:
        >>> zip_path = await create_zip_archive(["abc123", "def456"])  # doctest: +SKIP
        >>> print(zip_path)  # doctest: +SKIP
    """
    zip_path = settings.TEMP_DIR / "document_extraction.zip"
    pages_dir = settings.EXTRACTED_DIR
    output_doc = settings.OUTPUT_DIR / "document.md"

    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create temp directory: {e}")
        raise IOError(f"Cannot create temp directory: {e}")

    try:
        added_count = await asyncio.to_thread(
            _build_zip, zip_path, pages_dir, file_ids, output_doc
        )
        logger.info(f"Created zip archive: {zip_path} ({added_count} pages)")
    except IOError as e:
        logger.error(f"Failed to create zip archive: {e}")
        raise

    return str(zip_path)
