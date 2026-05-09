"""Image extraction module — sends document page images to a multimodal LLM
and returns structured markdown.

Supports any OpenAI-compatible endpoint (LM Studio, vLLM, cloud APIs)
via litellm's provider abstraction.

The extraction prompt is loaded from ``prompt.txt`` at the project root
on module import. If the file is absent or empty the built-in
``EXTRACTION_PROMPT`` constant is used as a fallback.
"""

import asyncio
import base64
import logging
import time

import aiofiles
import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# Built-in fallback prompt — override by editing prompt.txt at the project root.
# Container restart (no rebuild) picks up prompt.txt changes.
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
    """Return the contents of prompt.txt, or EXTRACTION_PROMPT if absent."""
    prompt_file = settings.BASE_DIR / "prompt.txt"
    if prompt_file.exists():
        text = prompt_file.read_text(encoding="utf-8").strip()
        if text:
            logger.info(f"Loaded extraction prompt from {prompt_file}")
            return text
    return EXTRACTION_PROMPT


ACTIVE_PROMPT: str = _load_prompt()


async def extract_image_batch(
    image_paths: list[str],
    prior_context: str = "",
) -> str:
    """Extract markdown from a batch of document page images in one API call.

    All images are sent together in a single user message, optionally preceded
    by the full markdown output of the previous batch as a text context element.
    This lets the model maintain formatting consistency across batches.

    Args:
        image_paths: Ordered list of absolute paths to PNG or JPG image files.
        prior_context: Complete markdown from the previous batch. Passed as a
            text part before the images so the model can continue section
            numbering, table style, and notation conventions. Empty = no context.

    Returns:
        Extracted markdown text on success, or ``"FAILED"`` on any error.
        Errors are logged; no exception is raised so a failed batch does not
        abort the rest of a run.
    """
    if not image_paths:
        return "FAILED"

    first_id = image_paths[0].replace("\\", "/").split("/")[-1].split(".")[0][:8]

    try:
        user_content: list[dict] = []

        if prior_context:
            user_content.append({
                "type": "text",
                "text": (
                    "The following is the extracted markdown from the preceding batch "
                    "of document pages. Use it for formatting consistency — continue "
                    "section numbering, table style, and notation conventions.\n\n"
                    + prior_context
                ),
            })

        total_kb = 0.0
        for image_path in image_paths:
            async with aiofiles.open(image_path, "rb") as f:
                image_data = await f.read()
            total_kb += len(image_data) / 1024
            base64_image = base64.b64encode(image_data).decode("utf-8")
            mime_type = (
                "image/jpeg"
                if image_path.lower().endswith((".jpg", ".jpeg"))
                else "image/png"
            )
            user_content.append({
                "type": "image_url",
                "image_url": f"data:{mime_type};base64,{base64_image}",
            })

        # litellm requires the "openai/" provider prefix for OpenAI-compatible
        # endpoints. Model names like "qwen/qwen2.5-vl-7b" contain a slash but
        # are not provider-prefixed — check the prefix explicitly.
        model = settings.LITELM_API_MODEL
        if not model.startswith("openai/"):
            model = f"openai/{model}"

        # The openai client appends /chat/completions to api_base, so /v1
        # must be present in the base URL to reach LM Studio correctly.
        api_base = settings.LM_STUDIO_ENDPOINT.rstrip("/")
        if not api_base.endswith("/v1"):
            api_base = f"{api_base}/v1"

        logger.info(
            f"Extracting {len(image_paths)} image(s) ({total_kb:.0f} KB total)"
            + (f" [+{len(prior_context):,} chars context]" if prior_context else "")
            + f" → {model} @ {api_base}"
        )

        messages = [
            {"role": "system", "content": ACTIVE_PROMPT},
            {"role": "user", "content": user_content},
        ]

        t0 = time.monotonic()
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            api_base=api_base,
            # api_key is required by the openai client even for local endpoints;
            # LM Studio accepts any non-empty value.
            api_key="not-needed",
            max_tokens=settings.MAX_OUTPUT_TOKENS,
            temperature=0,
            timeout=300,
            num_retries=0,
            # Qwen3 thinking models put reasoning in reasoning_content and
            # leave content empty, which breaks litellm's response parser.
            extra_body={"enable_thinking": False},
        )
        elapsed = time.monotonic() - t0

        markdown = response.choices[0].message.content
        logger.info(
            f"Done ({len(image_paths)} images) → {len(markdown):,} chars in {elapsed:.1f}s"
        )
        return markdown

    except FileNotFoundError:
        logger.warning(f"File not found in batch starting with {first_id}")
        return "FAILED"
    except TimeoutError:
        logger.warning(f"Timeout extracting batch starting with {first_id}")
        return "FAILED"
    except (ValueError, KeyError) as exc:
        logger.warning(f"Unexpected response format for batch: {exc}")
        return "FAILED"
    except Exception as exc:
        logger.error(f"Extraction failed for batch: {type(exc).__name__}: {exc}")
        return "FAILED"


async def extract_single_image(image_path: str) -> str:
    """Extract markdown from a single image. Thin wrapper around extract_image_batch."""
    return await extract_image_batch([image_path])
