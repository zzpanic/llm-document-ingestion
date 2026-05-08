# Quick Start Guide - LLM Document Ingestion

## Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- LM Studio running with a multimodal model (e.g., Qwen 3.5-9B)
- pip and venv for Python environment management

---

## Local Development

### 1. Clone and Setup

```bash
git clone https://github.com/zzpanic/llm-document-ingestion.git
cd llm-document-ingestion

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your settings (if needed)
# Default values should work with local LM Studio on localhost:1234
nano .env
```

### 3. Start LM Studio

Make sure LM Studio is running with a multimodal model loaded:
- Visit http://localhost:1234
- Load a model like Qwen 3.5-9B (recommended for technical documents)
- Verify the server is running

### 4. Run the Application

```bash
# Run with auto-reload for development
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Output should show:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 5. Access the Web Interface

Open your browser and navigate to:
- **Upload page**: http://localhost:8000/ui/upload
- **Status page**: http://localhost:8000/ui/status
- **Download page**: http://localhost:8000/ui/download
- **API docs**: http://localhost:8000/docs (Swagger UI)
- **Alternative docs**: http://localhost:8000/redoc (ReDoc)

---

## Docker Deployment

### 1. Clone and Build the Image

```bash
git clone https://github.com/zzpanic/llm-document-ingestion.git
cd llm-document-ingestion
docker compose build
```

### 2. Start the Container

```bash
# Docker Desktop (Mac/Windows) — default endpoint is host.docker.internal:1234
docker-compose up -d

# Linux host or remote LM Studio — set the LAN IP in your .env or inline
LM_STUDIO_ENDPOINT=http://192.168.1.81:1234 docker-compose up -d
```

> **Docker networking note:** `localhost` inside a container refers to the container itself, not your host machine. Docker Desktop exposes the host as `host.docker.internal`. On Linux, use the host's LAN IP instead.

### 3. View Logs

```bash
docker-compose logs -f document-ingestion
```

### 4. Stop the Container

```bash
docker-compose down
```

---

## Testing the API

### Test Upload Endpoint

```bash
# Upload a single image
curl -X POST http://localhost:8000/upload \
  -F "files=@page1.png"

# Response:
{
  "uploaded": [
    {
      "id": "abc123def456...",
      "filename": "page1.png"
    }
  ]
}
```

### Test Process Endpoint

```bash
# Trigger extraction
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "file_ids": ["abc123def456..."]
  }'

# Response:
{
  "status": "processing_started"
}
```

### Check Status

```bash
curl http://localhost:8000/status

# Response:
{
  "status": {
    "abc123def456...": {
      "state": "processing"
    }
  }
}
```

### Download Results

```bash
# Download single page
curl http://localhost:8000/download/pages/abc123def456... \
  -o page.md

# Download assembled document
curl http://localhost:8000/download/document \
  -o document.md

# Download zip archive
curl http://localhost:8000/download/zip \
  -o archive.zip
```

---

## Common Workflows

### Workflow 1: Upload and Extract a Single Document

1. **Open upload page** → http://localhost:8000/ui/upload
2. **Drag and drop** image files or click to select
3. **Verify files** are listed with correct size and type
4. **Click "Upload Selected Files"** — files are saved and a "Process Files" button appears
5. **Click "Process Files"** — extraction starts and you are automatically redirected to the Status page
6. **Watch extraction progress** (auto-refreshes every 3 seconds)
7. **Once complete**, click "Download All Pages" (individual `.md` files) or "Download Zip" (all pages in one archive)

### Workflow 2: Batch Process Multiple Documents

1. Upload all pages for Document A
2. Go to Status page, watch extraction
3. Once done, download Document A
4. Return to Upload page
5. Upload all pages for Document B
6. Repeat as needed

### Workflow 3: Recover from Failed Page

1. **Check Status page** to identify failed pages
2. If a page failed:
   - **Check LM Studio logs** for error messages
   - **Verify image quality** (not too blurry or dark)
   - **Re-upload the page** and process again
3. **Alternative**: Manually edit `extracted/page_{id}.md` with correct content

---

## Troubleshooting

### "Connection refused" to LM Studio

**Issue**: `Failed to connect to LM_STUDIO_ENDPOINT`

**Solutions**:
```bash
# Check LM Studio is running
curl http://localhost:1234/health

# Check endpoint in .env
cat .env | grep LM_STUDIO_ENDPOINT

# Verify network (if using remote server)
ping 192.168.1.81
curl http://192.168.1.81:1234/health
```

### "Invalid configuration" on startup

**Issue**: `ValueError: Invalid LM_STUDIO_ENDPOINT`

**Solutions**:
- Verify LM_STUDIO_ENDPOINT is a valid HTTP(S) URL
- Common mistake: `192.168.1.81:1234` should be `http://192.168.1.81:1234`
- Check for typos in endpoint URL

### Extraction timing out

**Issue**: Pages take >60 seconds to extract

**Solutions**:
```bash
# Reduce image resolution/size
# Increase timeout in extraction.py (currently 60s)
# Try simpler model (smaller parameters)
# Check LM Studio isn't overloaded
```

### Out of disk space

**Issue**: Temp files accumulating

**Solutions**:
```bash
# Manual cleanup
rm temp/*.zip
rm extracted/*.md
rm uploads/*

# Or let auto-cleanup run (1-day retention)
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Range | Notes |
|----------|---------|-------|-------|
| `LM_STUDIO_ENDPOINT` | `http://localhost:1234` | Valid URL | Must be accessible |
| `LITELM_API_MODEL` | `qwen3.5-9b` | Any vision model | Depends on LM Studio |
| `MAX_IMAGES_PER_BATCH` | `100` | 1-1000 | Recommended: 20-100 |
| `MAX_IMAGE_SIZE_MB` | `10` | 1-100 | In megabytes |

### Rate Limits

- `/upload`: 10 requests per minute per IP
- `/process`: 5 requests per minute per IP
- `/download/zip`: 5 requests per minute per IP

### File Retention

- Uploaded images: Kept indefinitely (set `uploads/` volumes)
- Extracted markdown: Kept indefinitely (set `extracted/` volumes)
- Temp zip files: Deleted after 1 day (auto cleanup task)

---

## Performance Tuning

### For Faster Extraction

```bash
# In .env
LITELM_API_MODEL=qwen3.5-9b  # Smaller model
MAX_IMAGE_SIZE_MB=5           # Smaller images = faster processing
```

### For Better Quality

```bash
# In .env
LITELM_API_MODEL=qwen3.5-9b  # Larger model (if available)
MAX_IMAGE_SIZE_MB=20          # Higher resolution = better recognition
```

### For Larger Documents

```bash
# In .env
MAX_IMAGES_PER_BATCH=50       # Process in smaller batches
```

---

## Health Checks

### Application Health

```bash
# Check if application is running
curl http://localhost:8000/docs

# Check if LM Studio is accessible
curl http://localhost:8000/status
```

### Docker Health

```bash
# Check container status
docker-compose ps

# View health status
docker inspect llm-document-ingestion | grep -A 5 "Health"
```

---

## Production Checklist

- [x] Configuration validated on startup
- [x] Logging configured with timestamps
- [x] Rate limiting enabled (prevents abuse)
- [x] Error handling comprehensive (no silent failures)
- [x] Async I/O used throughout (non-blocking)
- [x] Path traversal protection (UUID validation)
- [x] Temp file cleanup (disk space managed)
- [x] CORS enabled for web clients
- [x] Health checks configured
- [x] Database/persistence abstracted (can be extended)

Ready for production deployment! 🚀

---

## Next Steps

1. **Configure production endpoints** in `.env`
2. **Set up monitoring** (logs, metrics)
3. **Configure backups** for `extracted/` and `output/` directories
4. **Set up SSL/TLS** if exposing over network
5. **Configure reverse proxy** (nginx, traefik) for production
6. **Set resource limits** in docker-compose or orchestration platform

---

## Support

For issues or questions:
1. Check logs: `docker-compose logs document-ingestion`
2. Review error messages in `/status` endpoint
3. Check LM Studio logs for extraction failures
4. Verify configuration in `.env`
5. Test connectivity to LM Studio endpoint

Good luck! 🎉
