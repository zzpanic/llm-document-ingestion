"""Image extraction module using multimodal LLMs via litellm.

Provides functions for extracting markdown text from document images
using any supported LLM provider. Uses litellm as a uniform abstraction
layer over diverse LLM APIs including OpenAI, Anthropic, Ollama, and LM Studio.

This module implements the extraction step described in the algorithm specification,
Phase 2: AI Extraction.

Recommended libraries:
    - litellm>=1.57.0: Universal LLM API abstraction
"""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Dict

import aiofiles
import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# System prompt instructing the model to produce structured markdown with LaTeX math.
# See algorithm.md, Appendix B for document-type-specific prompt variations.
EXTRACTION_PROMPT: str = (
    "You are extracting text from a technical document image. Produce structured "
    "markdown output that preserves:\n\n"
    "1. DOCUMENT STRUCTURE:\n"
    "   - Main section titles as level-1 headings (#)\n"
    "   - Subsection titles as level-2 headings (##)\n"
    "   - Preserve all lists, tables, and footnotes\n\n"
    "2. MATHEMATICAL FORMULAS:\n"
    "   - Inline math MUST use single dollar signs: $E = mc^2$\n"
    "   - Displayed equations MUST use double dollar signs: $$...$$\n"
    "   - Do NOT use Unicode symbols -- always use LaTeX commands\n\n"
    "3. TABLES:\n"
    "   - Preserve table structure using markdown table syntax\n"
    "   - Maintain column alignments and merged cells if visible\n\n"
    "4. PRIORITY: Structure over prose."
)


async def extract_single_image(image_path: str) -> str:
    """Extract markdown text from a single document image.

    Reads the image file, encodes it as base64, and sends it to the
    configured LLM via litellm for extraction.

    Args:
        image_path: Filesystem path to the image file to extract.
            Expected to be a PNG or JPG file.

    Returns:
        Extracted markdown text if successful, or 'FAILED' on error.

    Raises:
        Specific exceptions (FileNotFoundError, TimeoutError) are logged
        with warnings. Unexpected exceptions are logged but not raised
        to allow partial batch processing. All error cases return 'FAILED'.

    Example:
        >>> result = await extract_single_image("uploads/page_001.png")  # doctest: +SKIP
        >>> if result != "FAILED":
        ...     print(f"Extracted {len(result)} characters")
    """
    try:
        # Read and encode image as base64 (non-blocking)
        async with aiofiles.open(image_path, "rb") as image_file:
            image_data = await image_file.read()
            base64_image = base64.b64encode(image_data).decode("utf-8")

        # Construct multi-modal message for litellm
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

        # Call LLM via litellm (works with any provider) with timeout
        response = await litellm.acompletion(
            model=settings.LITELM_API_MODEL,
            messages=messages,
            api_base=settings.LM_STUDIO_ENDPOINT,
            max_tokens=4096,
            temperature=0,
            timeout=60,
        )

        # Extract markdown from response
        markdown = response["choices"][0]["message"]["content"]
        logger.info(f"Successfully extracted {len(markdown)} chars from {image_path}")
        return markdown

    except FileNotFoundError as exc:
        logger.warning(f"Image file not found: {image_path}")
        return "FAILED"
    except TimeoutError as exc:
        logger.warning(f"Extraction timeout for {image_path}: {exc}")
        return "FAILED"
    except (ValueError, KeyError) as exc:
        logger.warning(f"Invalid response format from LLM for {image_path}: {exc}")
        return "FAILED"
    except Exception as exc:
        logger.error(f"Unexpected error during extraction for {image_path}: {exc}")
        return "FAILED"


async def extract_batch(image_paths: list[str]) -> Dict[str, str]:
    """Extract markdown from multiple images concurrently.

    Processes a batch of image paths using asyncio.gather and returns
    a mapping of file paths to their extracted markdown content.

    Args:
        image_paths: List of filesystem paths to image files.
            Each path should point to a valid PNG or JPG file.

    Returns:
        Dictionary mapping image paths to extracted markdown strings.
        Failed extractions map to the string "FAILED".

    Raises:
        No exceptions are raised. Individual page failures return
        "FAILED" in the result dictionary.

    Example:
        >>> paths = ["uploads/p1.png", "uploads/p2.png"]  # doctest: +SKIP
        >>> results = await extract_batch(paths)  # doctest: +SKIP
        >>> for path, md in results.items():
        ...     print(f"{path}: {len(md)} chars")
    """
    import asyncio

    results: Dict[str, str] = {}

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