# Technical Document Conversion — Step-by-Step Procedure

## A Detailed Guide to Converting Scanned Documents into Machine-Readable Markdown

---

**Version 1.0 — May 2026**

---

## Overview

This document provides detailed procedural steps for converting scanned technical documents into clean markdown with properly formatted mathematical formulas. It expands on the methodology described in the architectural whitepaper, providing specific guidance on how to execute each step regardless of which AI model or tool you choose.

The procedure is organized into five phases corresponding to the whitepaper's workflow: **Preparation**, **Extraction**, **Verification**, **Assembly**, and **Review**. Each phase contains discrete, actionable steps.

---

## Phase 1: Image Preparation

### Step 1.1: Obtain Source Images

**Input:** A multi-page PDF or physical document.

**Action:** Convert each page to a separate image file.

**Details:**
- If you have a PDF, use a PDF-to-image tool to extract each page as an individual image.
- If you have a physical document, use a scanner to create digital images.
- Name files sequentially: `page_001.png`, `page_002.png`, etc.

**Validation:** Ensure every page of the source document has exactly one corresponding image file. No pages should be missing or duplicated.

### Step 1.2: Set Scan Resolution

**Target:** 300–400 DPI (dots per inch).

**Why this range:**
- Below 300 DPI: Fine mathematical symbols (subscripts, small fractions) become pixelated and are misrecognized by AI models.
- Above 400 DPI: Processing time increases with no accuracy benefit for text recognition.

**How to verify:** A standard US Letter page (8.5" × 11") at 300 DPI produces an image approximately 2550 × 3300 pixels. At 400 DPI, approximately 3400 × 4400 pixels.

### Step 1.3: Choose Image Format

**Recommended:** PNG (lossless compression).

**Alternatives:**
- TIFF: Larger files, slightly better quality, useful for archival.
- JPEG: Acceptable if compressed at high quality (90%+), but lossy compression can introduce artifacts that confuse vision models.

**Avoid:** WebP, BMP, GIF — not all AI models accept these formats natively.

### Step 1.4: Clean Scan Artifacts

**Action:** Before feeding images to the AI model, remove visual noise that degrades extraction quality.

**Specific cleanup operations:**
1. **Deskew.** Rotate scanned pages that are tilted. A tilt of more than 2 degrees noticeably reduces recognition accuracy.
2. **Crop margins.** Remove white borders and scanner frame artifacts.
3. **Adjust contrast.** Ensure text is dark against a light background. Low contrast causes missed characters; high contrast causes broken glyphs.
4. **Remove stains.** If the source document has coffee stains or age discoloration, use image editing to lighten affected areas without affecting text.

**Tool suggestions:** Any image editor with basic adjustment capabilities (GIMP, ImageMagick, Preview on macOS).

---

## Phase 2: AI Extraction

### Step 2.1: Select a Multimodal Model

**Criteria for selection:**
- The model accepts image input (vision-language capability).
- The model has been tested on technical document extraction.
- The model can output text in Markdown format.

**Common model categories:**
- **Cloud API models:** GPT-4o, Gemini Pro, Claude — accessible via REST API, pay per image.
- **Open-source models:** Qwen-VL, LLaVA, MiniMax — self-hosted, free but require GPU.
- **Specialized OCR engines:** Azure Form Recognizer, AWS Textract — optimized for document structure but weaker on complex math.

**Verification step:** Before committing to a model, extract 5 diverse pages (including pages with heavy math, tables, and multi-column text) and evaluate output quality.

### Step 2.2: Construct the Prompt

**The prompt is the single most important factor in extraction quality.** A well-crafted prompt can compensate for a weaker model; a poor prompt wastes even the best models.

**Prompt structure:** All effective prompts contain these elements:

1. **Role assignment.** Tell the model what it is doing: "You are a technical document transcriber..."
2. **Output format specification.** Explicitly describe markdown formatting requirements.
3. **Math formatting rules.** Instruct the model to use LaTeX syntax for all formulas.
4. **Structure preservation.** Require headings, lists, and tables to be preserved.

**Base prompt template:**

```
You are extracting text from a technical document image. Produce structured markdown output that preserves:

1. DOCUMENT STRUCTURE:
   - Main section titles as level-1 headings (#)
   - Subsection titles as level-2 headings (##)
   - Sub-subsections as level-3 headings (###)
   - Preserve all lists, tables, and footnotes

2. MATHEMATICAL FORMULAS:
   - Inline math MUST use single dollar signs: $E = mc^2$
   - Displayed equations MUST use double dollar signs: $$\int_0^\infty e^{-x} dx$$
   - Do NOT use Unicode symbols (∑, ∫, ≤) — always use LaTeX commands (\sum, \int, \leq)

3. TABLES:
   - Preserve table structure using markdown table syntax
   - Maintain column alignments and merged cells if visible

4. PRIORITY: Structure over prose. If formatting is ambiguous, preserve the visual layout rather than converting to prose description.
```

**Prompt variations by document type:**

| Document Type | Prompt Adjustment |
|---|---|
| Engineering standard | Add: "Preserve clause numbers and cross-references exactly as shown" |
| Academic paper | Add: "Preserve author names, affiliations, and abstract structure" |
| Textbook chapter | Add: "Preserve worked examples and their step-by-step solutions" |
| Specification document | Add: "Preserve all normative references and appendix designations" |

### Step 2.3: Configure Model Parameters

**For API-based models:**

- **Temperature.** Set to 0 or very low (0.1). You want deterministic, consistent output, not creative variation.
- **Max tokens.** Set generously (4096+). Technical pages with dense formulas can produce long outputs; truncation causes incomplete extraction.
- **Top_p.** Set to 0.9–1.0. Higher values allow more vocabulary diversity, which can help with rare mathematical symbols.

**For self-hosted models:**

- **Context window.** Ensure the model's context window is large enough for a full page (typically 2000–4000 tokens per page).
- **Quantization.** Use NF4 or Q8 quantization for best quality; avoid Q4 which degrades math extraction.

### Step 2.4: Execute Extraction

**Batch processing strategy:**

1. **Start with the first 10 pages.** Extract and immediately review these to catch prompt issues early.
2. **Adjust prompt if needed.** If the first batch shows systematic errors (e.g., all formulas using Unicode instead of LaTeX), refine the prompt before continuing.
3. **Process remaining pages in batches of 20–50.** Larger batches reduce overhead; smaller batches enable finer quality control.
4. **Save each page's output separately.** Do not merge during extraction — keep per-page markdown files for later assembly.

**Handling timeouts and failures:**

- If the model times out on a dense page, retry with:
  - Higher `max_tokens` setting
  - Cropped image (extract just the math section rather than the full page)
  - A different model if the current one consistently fails
- **Retry policy:** Maximum 3 retry attempts per page. After 3 failures, mark the page as "failed" and proceed with remaining pages.
- **Failed page handling:** Log all failures with timestamps for manual review at the end. Failed pages can be re-extracted individually after the batch completes.

---

## Phase 3: Verification

### Step 3.1: Completeness Check

**Action:** Compare extracted page count with source document page count.

**Procedure:**
```
source_pages = count_files("page_*.png")
extracted_pages = count_files("page_*.md")
if source_pages != extracted_pages:
    report "MISMATCH: expected {source_pages}, got {extracted_pages}"
```

**Missing pages** indicate extraction failures that must be retried.

### Step 3.2: Formula Validation

**Action:** Spot-check mathematical formulas for correct LaTeX syntax.

**Common failure patterns:**

| Failure | Example | Fix |
|---|---|---|
| Unicode instead of LaTeX | `σ_y` should be `\sigma_y` | Prompt needs stronger math instruction |
| Missing dollar signs | `E = mc^2` should be `$E = mc^2$` | Prompt needs explicit format rules |
| Broken subscripts | `M_b_b` should be `M_{b,b}` | Model confused by multiple subscripts |
| Sign errors | `-` instead of `\leq` for "less than or equal" | Model misread glyph |

**Verification procedure:**
1. Open the source image and extracted markdown side by side.
2. Check every formula on the first 5 pages thoroughly.
3. Check every formula on pages 10, 20, 30 as random samples.
4. Flag any page with incorrect formulas for manual correction.

### Step 3.3: Structure Validation

**Action:** Verify that heading hierarchy matches the source document's actual structure.

**Common errors:**
- All headings extracted as h1 (model defaults to largest visual size)
- Subsections extracted as h1 when they should be h2
- Table of contents entries not preserved as links or structured text

**Fix procedure:** Manual heading correction is often faster than perfect extraction on the first pass. Use a markdown editor with heading visualization.

### Step 3.4: Table Integrity Check

**Action:** Verify that extracted tables have correct column counts and row alignments.

**Common failures:**
- Merged cells split into separate rows
- Multi-line cell content collapsed to single line
- Column headers misaligned with data columns

---

## Phase 4: Document Assembly

### Step 4.1: Merge Pages in Order

**Action:** Concatenate per-page markdown files into a single document, preserving original page order.

**Procedure:**
```
output = "# Extracted Document\n\n"
for page_number from 1 to N:
    page_file = "page_" + pad(page_number) + ".md"
    if page_file exists:
        content = read(page_file)
        output += "\n--- Page " + page_number + " ---\n\n"
        output += content
write("document.md", output)
```

**Page separator:** Use `--- Page N ---` as a visible delimiter. This enables:
- Quick navigation to specific pages
- Identification of which extracted page contains an error
- Traceability back to the source image

### Step 4.2: Regenerate Table of Contents

**Action:** If the source document had a TOC, verify it is present in the extracted output. If not, generate one from heading structure.

**TOC generation algorithm:**
```
toc = "## Table of Contents\n\n"
for each heading in document:
    indent = (heading_level - 1) * 2 spaces
    toc += indent + "- **Heading Text**\n"
write(toc, at_start_of_document)
```

**Note:** A model-generated TOC is more accurate than a simple heading list. If the source had a numbered TOC (e.g., "5.2.1 Stress limitations"), preserve that numbering exactly.

### Step 4.3: Consolidate Appendices

**Action:** Verify that appendix pages appear at the end of the assembled document, not at their original scan position.

**If appendices were scanned out of order** (common with physical documents):
1. Identify pages labeled as "Appendix A," "Appendix B," etc.
2. Move them to the end of the assembled document.
3. Update any cross-references if needed.

---

## Phase 5: Quality Review

### Step 5.1: Prioritized Review Order

**Review the extracted document in this order for maximum efficiency:**

1. **First 10 pages.** Catch systematic prompt issues early. If the prompt is wrong, you'll see it repeated across many pages.
2. **Pages with heavy math.** These are highest value and most error-prone. Give them thorough attention.
3. **Cross-reference points.** Verify that "see Section X" references resolve correctly in the extracted document.
4. **Appendices.** Often overlooked by AI models due to non-linear content; verify completeness.

### Step 5.2: Formula Verification

**Action:** For each formula in the extracted document, compare against the source image.

**Checklist:**
- [ ] LaTeX syntax is valid (can be parsed by a LaTeX renderer)
- [ ] Variable names match source (subscripts, superscripts correct)
- [ ] Operators are correct (`\leq` not `<`, `\times` not `×`)
- [ ] No formulas are missing (especially displayed equations centered on their own line)
- [ ] Inline math is properly delimited with single `$` not double `$$`

### Step 5.3: Section Numbering Verification

**Action:** Cross-check clause/section numbers in the extracted document against the source.

**Example:** If source has "Clause 5.2.1 — Design strength" and extracted output has "Clause 5.2.2 — Design strength," the section number is wrong.

**Common numbering errors:**
- Section numbers skipped (5.1, 5.3 but no 5.2)
- Subsection numbering reset at column boundaries
- Appendix letters assigned incorrectly (Appendix C labeled as Appendix B)

### Step 5.4: Final Quality Gate

**Before considering the extraction complete, verify:**

| Check | How to Verify |
|---|---|
| All pages extracted | Page count matches source |
| Formulas use valid LaTeX | No Unicode math symbols remain |
| Heading hierarchy correct | h1 > h2 > h3 nesting is consistent |
| Tables intact | Column counts match source images |
| Cross-references resolve | "See Section X" points to correct section |
| Appendices complete | All appendix pages present and in order |
| TOC accurate | TOC entries match actual headings |

---

## Web Interface User Algorithm

### Step W.1: User Navigates to Upload Page

**Action:** User opens the FastAPI web application in a browser (typically `http://localhost:8000/ui/upload`).

**UI behavior:**
- The upload page displays a drag-and-drop zone for file selection
- Visual indicators show supported file types (PNG, JPG) and size limits (10MB per file)
- Users can select multiple files at once via the file picker

### Step W.2: User Selects or Drags Files

**Action:** User adds images to the upload queue.

**UI behavior:**
- Selected files appear in a list with their names and sizes
- Each file has an individual "remove" button
- The "Upload" button becomes enabled when at least one file is selected
- Drag-over state highlights the drop zone visually

### Step W.3: User Clicks Upload

**Action:** The browser sends a POST request to `/upload` with the selected files as multipart/form-data.

**Server-side processing:**
1. Validate each file's content type (must be `image/png` or `image/jpeg`)
2. Validate each file's size (must not exceed 10MB)
3. Generate unique IDs for each file
4. Save files to the `uploads/` directory

**Response:** Server returns a JSON response with the assigned file IDs.

### Step W.4: User Navigates to Status Page

**Action:** After upload, the user is directed to `/ui/status` (or clicks the Status tab).

**UI behavior:**
- A table displays each uploaded page with its current extraction state
- Color-coded indicators: Pending (gray), Processing (yellow), Done (green), Failed (red)
- Error messages appear for any failed extractions
- Auto-refresh polls `/status` every 3 seconds while any file is still processing

### Step W.5: Extraction Runs in Background

**Server-side behavior:**
1. When the user triggers extraction, a background task begins processing each image
2. Each image is sent to the LLM via internal extraction functions (not an API endpoint)
3. The status tracker updates in real-time: `pending` → `processing` → `done` or `failed`
4. Extracted markdown is saved to `extracted/page_{file_id}.md`
5. **Retry logic:** Failed pages are retried up to 3 times with increasing `max_tokens` before marking as "failed"

### Step W.6: User Downloads Results

**Action:** Once extraction completes, the user can download results via three options:

| Download Option | Endpoint | Description |
|---|---|---|
| Individual Pages | `/download/pages/{page_id}` | Single page markdown as text file |
| Assembled Document | `/download/document` | Merged markdown of all pages |
| Zip Archive | `/download/zip` | All files packaged in one zip |

**UI behavior:**
- Download buttons appear conditionally based on extraction state
- "Download All Pages" visible when at least one file is done
- "Download Document" and "Download Zip" visible when all files are done
- Failed pages are excluded from downloads

### Step W.7: User Returns to Upload for New Batch

**Action:** After completing downloads, the user can start a new batch by returning to the Upload page.

**UI behavior:**
- The upload form resets to its initial empty state
- No residual data from the previous batch remains

### Step W.8: Client-Side Status Polling Algorithm

```
function startPolling(fileIds):
    while any file is in "processing" state:
        fetch GET /status
        update table with new states
        if no files are processing:
            stop polling
            show download buttons
        wait 3 seconds
```

**Stop conditions:**
- All files are in "done" or "failed" state
- User navigates away from the Status page

### Step W.9: Error Handling in the Web Interface

| Scenario | User-Facing Behavior |
|---|---|
| Invalid file type | Inline error message: "Unsupported file type. Only PNG and JPG images are accepted." |
| File too large | Inline error message: "File exceeds 10MB limit." |
| LLM API timeout | Status shows "failed" with error message; user can retry that page |
| Network interruption | Upload resumes from last successful file; no data loss |

---

## Appendix A: Troubleshooting Guide

### A.1 Model Returns Garbled Output

**Symptoms:** Extracted text contains random characters, mixed languages, or nonsensical structure.

**Causes and fixes:**
- **Scan quality too poor.** Rescan at higher DPI (400 instead of 300).
- **Prompt too generic.** Add explicit format rules (LaTeX for math, heading levels for sections).
- **Model too small.** Switch to a larger model (7B+ parameters).

### A.2 Formulas Are Missing or Incomplete

**Symptoms:** Text extraction works but formulas appear as `[IMAGE]` placeholders or are skipped entirely.

**Causes and fixes:**
- **Model doesn't support math.** Not all vision models extract formulas; test with a known formula page first.
- **Max tokens too low.** Dense pages with many formulas produce long output; increase max_tokens.
- **Image too small.** Formula glyphs are too small at low resolution; rescan at 400 DPI.

### A.3 Multi-Column Documents Read Wrong Order

**Symptoms:** Text from right column appears before left column, or columns are interleaved.

**Causes and fixes:**
- **Model reads right-to-left.** Some models default to RTL reading order; instruct the prompt to "read left-to-right, top-to-bottom."
- **Column break not detected.** The model treats column breaks as continuous text; crop each column separately and extract independently.

### A.4 Extraction is Too Slow

**Symptoms:** Processing a 200-page document takes hours.

**Causes and fixes:**
- **Image resolution too high.** Reduce to 300 DPI; models don't need more than that for accurate recognition.
- **Processing one page at a time.** If your model supports batch input, feed 5–10 pages per API call.
- **Model on slow hardware.** Self-hosted models on CPU are significantly slower than GPU; consider cloud API for large documents.

### A.5 Page Extraction Failed Permanently

**Symptoms:** A page shows "failed" status after all retries exhausted.

**Causes and fixes:**
- **Heavily stained or faded page.** Rescan at higher DPI (400+) with better contrast adjustment.
- **Handwritten annotations.** AI models often fail on handwritten content; manual transcription required.
- **Extremely small font (< 6pt).** No AI model can reliably recognize this; manual transcription required.
- **Corrupted source image.** The scan was damaged; rescan the original page.

**Manual correction workflow:**
1. Open the source image in an image viewer
2. Manually transcribe the content into `extracted/page_{file_id}.md`
3. Mark the page as "done" in the status tracker after manual correction

---

## Appendix B: Prompt Templates by Document Type

### B.1 Engineering Standard

```
You are extracting text from an engineering standard document. Produce structured markdown output that preserves:

1. DOCUMENT STRUCTURE:
   - Clause numbers (e.g., "5.2.1") must be preserved exactly
   - Cross-references (e.g., "see Clause 6.3") must be preserved
   - Main clauses as h1, subclauses as h2, sub-subclauses as h3

2. MATHEMATICAL FORMULAS:
   - ALL formulas MUST use LaTeX syntax
   - Inline: $M_b \leq \phi_b k_b M_s$
   - Displayed: $$\phi_s A_{st} (d_1 - d_s)$$
   - Never use Unicode symbols (∑, ∫, ≤)

3. TABLES OF VALUES:
   - Preserve all column headers and data rows
   - Maintain units as shown in source

4. PRIORITY: Structural accuracy over prose fluency. If a line is ambiguous, preserve the visual layout.
```

### B.2 Academic Paper

```
You are extracting text from an academic research paper. Produce structured markdown output that preserves:

1. PAPER METADATA:
   - Title as h1
   - Author names and affiliations
   - Abstract as a distinct block
   - Keywords

2. MATHEMATICAL FORMULAS:
   - ALL derived formulas MUST use LaTeX
   - Equation numbers (e.g., "(1)") must be preserved beside displayed equations

3. FIGURE CAPTIONS:
   - Preserve figure captions exactly
   - Note: "Figure 3.2 shows..." should become markdown text, not be ignored

4. CITATIONS:
   - Preserve citation markers ([1], (Smith et al., 2020))
```

### B.3 Textbook Chapter

```
You are extracting text from a textbook chapter. Produce structured markdown output that preserves:

1. CHAPTER STRUCTURE:
   - Chapter title as h1
   - Section titles as h2
   - Learning objectives box content
   - Worked examples with step-by-step solutions

2. MATHEMATICAL FORMULAS:
   - ALL formulas in worked examples MUST use LaTeX
   - Preserve equation numbering if shown

3. BOXED CONTENT:
   - Key points, summaries, and highlights should be marked as blockquotes (>)
   - Do not merge boxed content into main text

4. PRACTICE PROBLEMS:
   - Preserve problem numbers and all sub-parts (a, b, c)
```

---

*This document describes Version 1.0 of the Technical Document Conversion Procedure. Subsequent versions may address limitations identified through production use.*