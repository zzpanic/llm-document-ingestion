# Quick Start — LLM Document Ingestion

## Prerequisites

- LM Studio (or any OpenAI-compatible API) running a multimodal model
- Enable the LM Studio API server and set it to listen on `0.0.0.0` (not just localhost), then load a vision-capable model
- Python 3.11+ **or** Docker

---

## Local Setup

```bash
git clone https://github.com/zzpanic/llm-document-ingestion.git
cd llm-document-ingestion

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
cp .env.example .env         # edit LM_STUDIO_ENDPOINT if not localhost:1234

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

---

## Docker Setup

```bash
git clone https://github.com/zzpanic/llm-document-ingestion.git
cd llm-document-ingestion
docker compose build
docker compose up -d
```

Set `LM_STUDIO_ENDPOINT` in `.env` before starting:

- **Docker Desktop (Mac/Windows):** `http://host.docker.internal:1234`
- **Linux:** use the host's LAN IP, e.g. `http://192.168.1.81:1234`
- `localhost` will not work inside a container

View logs: `docker compose logs -f document-ingestion`

---

## Using the Web Interface

### Upload → Status → Preview → Download

**1. Upload** (`/ui/upload`)

Drag images onto the drop zone or click to select. Supported formats: PNG, JPG, max 10 MB each.
Click **Upload & Process** — files are uploaded and extraction starts immediately. You are redirected to the Status page.

**2. Status** (`/ui/status`)

Shows each file's state: Pending → Processing → Done / Failed.
Refreshes every 3 seconds. An ETA is shown once the first page completes.
When all pages are done, a zip is created automatically and a **Go to Downloads** button appears.

**3. Preview** (`/ui/preview`)

Select any extracted page from the list on the left to view its rendered markdown on the right.
LaTeX formulas render via KaTeX.

**4. Download** (`/ui/download`)

Lists all zip archives in the temp folder (named by timestamp and first filename).
Individual page downloads are listed below.
**Clear Temp Folder** deletes all zips.

---

## Customising the Extraction Prompt

Edit `prompt.txt` in the project root. Restart the container (no rebuild needed) to pick up changes.
If `prompt.txt` is absent the built-in default is used.

---

## Configuration

All settings go in `.env` (copy from `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `LM_STUDIO_ENDPOINT` | `http://localhost:1234` | Base URL — do not include `/v1` |
| `LITELM_API_MODEL` | `qwen3.5-9b` | Must match the model loaded in LM Studio |
| `MAX_IMAGES_PER_BATCH` | `100` | Maximum files per upload |
| `MAX_IMAGE_SIZE_MB` | `10` | Per-file limit in MB |

---

## Troubleshooting

**"Connection error" during extraction**
LM Studio is not reachable. Check:
- The API server is started in LM Studio (not just a model loaded)
- It is bound to `0.0.0.0`, not `127.0.0.1`
- The endpoint in `.env` is correct
- Test: `curl http://<endpoint>/v1/models`

**"Error in response object" or empty extraction**
The model may be in thinking mode (Qwen3). The service sends `enable_thinking: false` automatically — if this fails with your model, check the LM Studio console for error details.

**"Invalid configuration" on startup**
`LM_STUDIO_ENDPOINT` must be a full URL including scheme: `http://192.168.1.81:1234` not `192.168.1.81:1234`.

**Pages extracting but content looks wrong**
Edit `prompt.txt` and adjust the extraction instructions. Restart the container.

**Temp folder growing large**
Use the Clear Temp Folder button on the Download page, or delete `temp/*.zip` manually.
Zips older than 24 hours are deleted automatically.
