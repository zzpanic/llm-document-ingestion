# LLM Document Ingestion Service

## Overview

A FastAPI-based Docker service for extracting structured markdown with LaTeX math from images using Qwen3.5-9B via LM Studio. Designed for processing technical documents (engineering standards, textbooks, papers) with complex mathematical notation.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Client     │────▶│  FastAPI Service │────▶│  Qwen3.5-9B     │
│   (Upload)   │     │  (app/main.py)   │     │  (LM Studio)    │
└─────────────┘     └──────────────────┘     └─────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │  Assembler       │
                    │  (merge pages)   │
                    └──────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │  Output          │
                    │  (markdown/zip)  │
                    └──────────────────┘
```

## Components

### 1. FastAPI Service (`app/main.py`)
- HTTP endpoint handler
- Manages upload, processing, and download flows
- Orchestrates the extraction pipeline

### 2. Image Extraction (`app/extraction.py`)
- Base64 encodes images
- Sends to LM Studio OpenAI-compatible API
- Parses Qwen3.5-9B markdown+LaTeX response
- Saves per-page output

### 3. Document Assembly (`app/assembler.py`)
- Reads per-page markdown files
- Merges with proper page breaks
- Generates single document output
- Creates zip archive

### 4. Configuration (`app/config.py`)
- Environment variable loading
- Endpoint URLs
- Model parameters

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /upload | Upload multiple images (multipart/form-data) |
| POST | /process | Trigger extraction on uploaded images |
| GET | /download/pages/{page_id} | Download single page markdown |
| GET | /download/document | Download merged document |
| GET | /download/zip | Download all as zip archive |
| GET | /status | Check processing status |

## Data Flow

1. **Upload**: Client sends multiple images via POST `/upload`
2. **Store**: Images saved to `images/` directory with unique IDs
3. **Process**: Client calls POST `/process` to trigger extraction
4. **Extract**: Each image sent to Qwen3.5-9B via LM Studio API
5. **Save**: Per-page markdown saved to `extracted/page_XXX.md`
6. **Assemble**: Merge all page markdowns into single document
7. **Download**: Client downloads individual pages, merged doc, or zip

## File Structure

```
llm-document-ingestion/
├── architectural-plan.md      # This file
├── Dockerfile                 # Container build
├── docker-compose.yml         # Service orchestration
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI routes
│   ├── extraction.py          # LM Studio API client
│   ├── assembler.py           # Document assembly
│   └── config.py              # Configuration
├── uploads/                   # Raw uploaded images
├── extracted/                 # Per-page markdown output
├── output/                    # Merged document
└── temp/                      # Temporary processing files
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LM_STUDIO_ENDPOINT` | `http://192.168.1.81:1234` | LM Studio API endpoint |
| `QWEN_MODEL` | `qwen3.5-9b` | Qwen model identifier |
| `MAX_IMAGES` | `100` | Max images per upload |
| `MAX_IMAGE_SIZE` | `10MB` | Max image file size |
| `OUTPUT_DIR` | `./output` | Output directory |

### Extraction Prompt

```
Extract text from this image as structured markdown. Preserve all mathematical formulas using LaTeX syntax:
- Inline math: $...$
- Block math: $$...$$
Maintain document structure with proper heading levels (h1-h6).
Preserve tables, lists, and other formatting elements.
```

## Docker Configuration

### Service Dependencies
- No external dependencies required
- LM Studio runs separately (configured via endpoint)

### Container Networking
- Service exposes port `8000`
- Connects to LM Studio via host network or custom bridge

### Volume Mounts
- `/app/uploads` - Upload storage
- `/app/extracted` - Per-page output
- `/app/output` - Merged document

## Error Handling

- Invalid file types rejected at upload
- API errors from LM Studio logged and propagated
- Partial processing failures don't stop entire pipeline
- Status endpoint shows processing state per page

## Security Considerations

- Validate file types (only images allowed)
- Rate limiting on endpoints
- Input size limits
- No code execution - pure text processing

## User Interface Architecture

### UI Requirements

The application provides a web-based interface for non-technical users to interact with the document ingestion pipeline. The UI separates HTML structure from presentation via static CSS files.

#### Page 1: Upload
- **Purpose**: Users upload scanned document pages as image files
- **Requirements**:
  - Drag-and-drop file upload area
  - Visual feedback during drag (highlight zone)
  - File type validation indicator (PNG/JPG only)
  - File size validation indicator (max 10MB per file)
  - Upload progress indicator for each file
  - "Upload" button to submit selected files
  - List of uploaded files with individual remove buttons
  - "Process" button to trigger extraction after all files are uploaded

#### Page 2: Status
- **Purpose**: Users monitor extraction progress in real-time
- **Requirements**:
  - Table listing all uploaded pages with their extraction state
  - Color-coded status indicators: Pending (gray), Processing (yellow), Done (green), Failed (red)
  - Per-page error message display if state is "failed"
  - Auto-refresh every 3 seconds while any file is in "processing" state
  - "Download All Pages" button (visible when at least one file is done)
  - "Download Document" button (assembled markdown, visible when all files done)
  - "Download Zip" button (archive of all outputs, visible when all files done)

#### Page 3: Download
- **Purpose**: Users access extracted outputs
- **Requirements**:
  - Summary of processing results (total pages, successful, failed)
  - List of individual page downloads with preview links
  - Single "Download Document" link (assembled markdown)
  - Single "Download Zip Archive" link (all files in one archive)

### Static Assets Structure

```
app/
├── templates/              # Jinja2 HTML templates
│   ├── upload.html         # Upload page template
│   ├── status.html         # Status page template
│   └── download.html       # Download page template
└── static/                 # Static files (separates HTML from presentation)
    ├── css/
    │   └── style.css       # Main stylesheet
    └── js/
        └── app.js          # Client-side JavaScript
```

### Design Principles

1. **Separation of concerns**: HTML templates contain only structure; all styling is in static CSS
2. **Progressive enhancement**: UI works without JavaScript (basic forms), enhanced with JS for interactivity
3. **Responsive design**: Interface usable on desktop browsers
4. **Accessibility**: Semantic HTML, ARIA labels where appropriate

## User Experience Flow

```
┌──────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│  Upload   │────▶│    Status    │────▶│   Download  │────▶│   Done      │
│  Page    │     │   Page       │     │   Page      │     │             │
└──────────┘     └──────────────┘     └─────────────┘     └─────────────┘
```

1. **Upload** → User selects images, sees upload progress
2. **Status** → User clicks "Process", watches extraction progress in real-time
3. **Download** → User downloads individual pages, assembled document, or zip archive
4. **Done** → User can start a new batch by returning to Upload page

## Performance Characteristics

- Extraction time: ~5-30 seconds per image (depends on complexity)
- Memory: Minimal (streaming uploads/downloads)
