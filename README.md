# LLM Document Ingestion Service

A FastAPI web service that extracts structured markdown from scanned document images using multimodal LLMs. Intended for technical documents with mathematical notation, tables, and structured layouts.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)
![License](https://img.shields.io/badge/License-MIT-blue.svg)

---

## What it does

Upload PNG/JPG images of document pages. The service sends each image to a multimodal LLM (via [litellm](https://github.com/BerriAI/litellm)), receives structured markdown back, and saves the results. You can then preview and download the extracted files.

Works with any OpenAI-compatible endpoint — LM Studio running a local model is the intended setup, but cloud APIs (OpenAI, Anthropic) work too.

The extraction prompt is fully customisable via `prompt.txt` at the project root without rebuilding the container.

**What it does not do:** it does not stitch pages into a single merged document in the current UI workflow. Each page is extracted and saved individually.

---

## Web Interface

Four pages, navigable via the header:

| Page | URL | Purpose |
|---|---|---|
| Upload | `/ui/upload` | Drag-and-drop images, single button to upload and start extraction |
| Status | `/ui/status` | Per-file progress with ETA, download links as pages complete |
| Preview | `/ui/preview` | Rendered markdown viewer with KaTeX for LaTeX formulas |
| Download | `/ui/download` | Timestamped zip archives, individual page downloads, clear temp folder |

A zip is created automatically when a batch finishes.

---

## Quick Start

### Local (no Docker)

```bash
git clone https://github.com/zzpanic/llm-document-ingestion.git
cd llm-document-ingestion
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # edit if your LM Studio is not on localhost:1234
python -m uvicorn app.main:app --reload
```

Open `http://localhost:8000` — redirects to the upload page.

### Docker

```bash
git clone https://github.com/zzpanic/llm-document-ingestion.git
cd llm-document-ingestion
docker compose build
docker compose up -d
```

**Networking note:** inside a Docker container `localhost` refers to the container itself. Docker Desktop users: the default endpoint `http://host.docker.internal:1234` reaches the host. Linux users: set `LM_STUDIO_ENDPOINT` to the host's LAN IP in `.env`.

---

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Default | Notes |
|---|---|---|
| `LM_STUDIO_ENDPOINT` | `http://localhost:1234` | Base URL of your LLM API (without `/v1`) |
| `LITELM_API_MODEL` | `qwen3.5-9b` | Model identifier — must match what's loaded |
| `MAX_IMAGES_PER_BATCH` | `100` | Max files per upload |
| `MAX_IMAGE_SIZE_MB` | `10` | Per-file size limit |

### Extraction prompt

Edit `prompt.txt` in the project root to customise how the LLM extracts text. The container reads it at startup — a container restart picks up changes without a rebuild. If `prompt.txt` is absent, the built-in default is used.

---

## REST API

| Method | Path | Description |
|---|---|---|
| POST | `/upload` | Upload images (multipart/form-data, field `files`) |
| POST | `/process` | Start extraction (`{"file_ids": [...]}`) |
| GET | `/status` | Extraction state for all tracked files |
| GET | `/download/pages/{page_id}` | Download a single extracted `.md` file |
| GET | `/download/zip` | Create and download a zip of all done pages |
| GET | `/download/zip/{filename}` | Download a specific named zip from temp/ |
| GET | `/preview/pages/{page_id}` | Return markdown as plain text (for browser preview) |
| GET | `/temp/zips` | List zip archives in temp/ |
| POST | `/temp/clear` | Delete all zips from temp/ |

Rate limits: 10 req/min on `/upload`, 5 req/min on `/process` and `/download/zip`.

API docs (Swagger): `http://localhost:8000/docs`

---

## Project Structure

```
llm-document-ingestion/
├── app/
│   ├── main.py            # FastAPI routes and app setup
│   ├── extraction.py      # LLM calls via litellm
│   ├── assembler.py       # Zip creation and page assembly
│   ├── config.py          # Settings from environment variables
│   ├── models.py          # Pydantic request/response models
│   ├── templates/         # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── upload.html
│   │   ├── status.html
│   │   ├── preview.html
│   │   └── download.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── prompt.txt             # Customisable extraction prompt
├── VERSION                # Current version (read by app at startup)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

Data directories (`uploads/`, `extracted/`, `output/`, `temp/`) are gitignored and mounted as Docker volumes.

---

## Versioning

See [version.md](version.md) for how to bump the version.

---

## License

MIT — see [LICENSE](LICENSE).
