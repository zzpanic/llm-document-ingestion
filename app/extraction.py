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
import time
from typing import Dict

import aiofiles
import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# Default system prompt — used when no prompt.txt file is present.
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


def _load_prompt() -> str:
    """Load extraction prompt from prompt.txt if present, else use built-in default."""
    prompt_file = settings.BASE_DIR / "prompt.txt"
    if prompt_file.exists():
        text = prompt_file.read_text(encoding="utf-8").strip()
        if text:
            logger.info(f"Loaded extraction prompt from {prompt_file}")
            return text
    return EXTRACTION_PROMPT


ACTIVE_PROMPT: str = _load_prompt()


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
    short_id = image_path.split("/")[-1].split(".")[0][:8]
    try:
        # Read and encode image as base64 (non-blocking)
        async with aiofiles.open(image_path, "rb") as image_file:
            image_data = await image_file.read()
            base64_image = base64.b64encode(image_data).decode("utf-8")

        size_kb = len(image_data) / 1024

        # Derive MIME type from file extension so JPGs are sent correctly
        mime_type = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"

        # litellm requires a provider prefix for custom OpenAI-compatible endpoints
        # (LM Studio, vLLM, Ollama). Auto-add "openai/" if not already present.
        model = settings.LITELM_API_MODEL
        if "/" not in model:
            model = f"openai/{model}"

        # openai client appends /chat/completions to api_base, so the base
        # must include /v1 to reach LM Studio's OpenAI-compatible endpoint.
        api_base = settings.LM_STUDIO_ENDPOINT.rstrip("/")
        if not api_base.endswith("/v1"):
            api_base = f"{api_base}/v1"

        logger.info(
            f"Extracting {short_id} ({size_kb:.0f} KB, {mime_type}) "
            f"→ {model} @ {api_base}"
        )

        # Construct multi-modal message for litellm
        messages = [
            {
                "role": "system",
                "content": ACTIVE_PROMPT
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": f"data:{mime_type};base64,{base64_image}"
                    }
                ]
            }
        ]

        t0 = time.monotonic()
        # api_key is required by the openai client even for local endpoints;
        # LM Studio accepts any non-empty value.
        # enable_thinking=False: Qwen3 thinking models put output in reasoning_content
        # and leave content empty, which breaks litellm's response parser.
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            api_base=api_base,
            api_key="not-needed",
            max_tokens=16384,
            temperature=0,
            timeout=60,
            extra_body={"enable_thinking": False},
        )
        elapsed = time.monotonic() - t0

        # Extract markdown from response (ModelResponse object, not dict)
        markdown = response.choices[0].message.content
        logger.info(
            f"Done {short_id} → {len(markdown):,} chars in {elapsed:.1f}s"
        )
        return markdown

    except FileNotFoundError:
        logger.warning(f"File not found: {image_path}")
        return "FAILED"
    except TimeoutError:
        logger.warning(f"Timeout extracting {short_id} (>{60}s) — consider smaller images")
        return "FAILED"
    except (ValueError, KeyError) as exc:
        logger.warning(f"Unexpected response format for {short_id}: {exc}")
        return "FAILED"
    except Exception as exc:
        logger.error(f"Extraction failed for {short_id}: {type(exc).__name__}: {exc}")
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