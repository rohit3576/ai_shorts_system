# AI Shorts Automation System

Local-first AI agent pipeline for monitoring YouTube channels, detecting new uploads, downloading videos, transcribing speech, finding viral moments with Ollama, rendering vertical Shorts with FFmpeg/OpenCV, generating subtitles and metadata, queueing uploads, and tracking analytics.

The default setup uses only local/open-source tools plus the YouTube API for optional upload/analytics OAuth. Uploads are disabled by default.

For a beginner-friendly, Windows-first operating manual, read [docs/REAL_CREATOR_SYSTEM_GUIDE.md](docs/REAL_CREATOR_SYSTEM_GUIDE.md).

## Truth Mode

The platform now separates metrics by source:

- `REAL`: collected from YouTube Data API / YouTube Analytics API or from explicit human review actions.
- `PREDICTED`: local retention, hook, pacing, and virality scores before upload.
- `ESTIMATED`: derived values such as revenue estimates from real views and configured RPM.
- `DEMO`: not used in dashboard analytics.

If no real YouTube analytics has been collected, the dashboard says: `No real analytics collected yet.`

## Architecture

```text
app/
  scraper/        YouTube RSS and yt-dlp channel resolution
  downloader/     yt-dlp video download and FFmpeg audio extraction
  transcription/  whisper.cpp JSON transcription normalization
  clip_detector/  Ollama viral moment detector and ranking
  captions/       Ollama metadata generation and ASS subtitle rendering
  editor/         OpenCV focus detection and FFmpeg 9:16 MP4 rendering
  uploader/       YouTube upload queue and OAuth uploader
  analytics/      YouTube Data/Analytics API snapshots with truth labels
  jobs/           Durable persisted jobs and stage tracking
  importer/       Backfills existing final_short/preview MP4s into the DB
  storage/        Media lifecycle inventory, cleanup, and archive mode
  scheduler/      APScheduler recurring automation that queues durable jobs
  dashboard/      Dark FastAPI/Jinja operations UI
database/         SQLAlchemy models and SQLite schema
data/             Local media/transcript/clip outputs
models/           whisper.cpp model files
temp/             Scratch space
```

## Local Setup

```powershell
cd ai_shorts_system
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Install local binaries:

- FFmpeg: make `ffmpeg` and `ffprobe` available on `PATH`.
- Ollama: install Ollama, then run `ollama pull qwen2.5:7b`.
- whisper.cpp: build or install `whisper-cli`, then place a GGML model at `models/ggml-base.en.bin` or update `WHISPER_MODEL_PATH`.
- yt-dlp: installed by `requirements.txt`, but the CLI must be available inside the active venv.

Run:

```powershell
python main.py
```

Open:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## First Channel

Use a raw YouTube channel ID when possible:

```powershell
curl -X POST http://127.0.0.1:8000/api/channels `
  -H "Content-Type: application/json" `
  -d "{\"url\":\"UCxxxxxxxxxxxxxxxxxxxxxx\",\"name\":\"Example\"}"
```

Channel URLs with `/channel/UC...` work directly. Handles such as `https://www.youtube.com/@name` are resolved with yt-dlp before RSS scanning.

Trigger processing:

```powershell
curl -X POST http://127.0.0.1:8000/api/process
```

## Pipeline

1. `scraper` scans YouTube RSS feeds and inserts unseen videos.
2. `downloader` downloads highest-quality media with yt-dlp.
3. `downloader.AudioExtractor` creates normalized mono WAV speech audio.
4. `transcription` runs whisper.cpp and writes normalized timestamped JSON.
5. `clip_detector` prompts Ollama for viral moments and ranks candidates.
6. `captions` generates title, description, hashtags, hook text, and animated ASS subtitles.
7. `editor` estimates focus with OpenCV, crops to 9:16, burns subtitles, adds hook text, normalizes audio, and exports MP4.
8. `uploader` requires human approval plus a structured rights/originality gate before queueing uploads.
9. `analytics` records real views, likes, comments, CTR, retention, watch time, and subscriber gain when YouTube returns them.
10. `learning` exports JSONL/CSV datasets and calibration reports from real outcomes and review labels.

## FFmpeg Commands Used

Audio extraction:

```bash
ffmpeg -y -i input.mp4 -vn -ac 1 -ar 16000 \
  -af "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11" \
  -codec:a libmp3lame -b:a 96k output.mp3
```

Shorts rendering shape:

```bash
ffmpeg -y -ss START -t DURATION -i input.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:x=(iw-1080)*FOCUS:y=(ih-1920)/2,scale=1117:1987,crop=1080:1920,eq=contrast=1.06:saturation=1.10,unsharp=5:5:0.45,fade=t=in:st=0:d=0.12,fade=t=out:st=END:d=0.18,drawtext=...,ass='clip.ass'" \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11" \
  -r 30 -c:v libx264 -preset veryfast -crf 23 \
  -c:a aac -b:a 160k -movflags +faststart -pix_fmt yuv420p output.mp4
```

## Ollama Setup

```powershell
ollama serve
ollama pull qwen2.5:7b
```

`.env` defaults:

```text
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

The viral detector prompt asks for JSON clips scored on suspense, emotional tension, curiosity gap, humor/surprise, cliffhanger potential, and cold-viewer comprehension. Caption generation uses a separate prompt for title, description, hashtags, and hook overlay text.

If Ollama is unavailable, `ALLOW_HEURISTIC_CLIP_FALLBACK=true` lets the system create lower-confidence local heuristic candidates so the rest of the pipeline can still be tested.

## whisper.cpp Setup

Place a model in `models/`, for example:

```text
models/ggml-base.en.bin
```

Update `.env` if your binary or model path differs:

```text
WHISPER_CPP_BINARY=whisper-cli
WHISPER_MODEL_PATH=models/ggml-base.en.bin
WHISPER_THREADS=4
```

The transcriber runs whisper.cpp JSON output and writes normalized files to `data/transcripts/*.normalized.json`.

## YouTube Uploads

Uploads are disabled by default:

```text
YOUTUBE_UPLOAD_ENABLED=false
```

To enable:

1. Create a Google Cloud OAuth desktop client.
2. Enable YouTube Data API v3 and YouTube Analytics API.
3. Save the OAuth client file as `client_secret.json` in the project root, or update `YOUTUBE_CLIENT_SECRET_FILE`.
4. Set `YOUTUBE_UPLOAD_ENABLED=true`.
5. Queue a clip with `POST /api/clips/{clip_id}/upload`.

The first upload opens an OAuth browser flow and stores `youtube_token.json`. Scheduled uploads are uploaded as private with `publishAt` set.

## API Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/channels` | Add channel |
| `GET` | `/api/channels` | List channels |
| `GET` | `/api/videos` | List source videos |
| `POST` | `/api/process` | Queue durable scan/process job |
| `POST` | `/api/videos/{video_id}/process` | Queue durable one-video job |
| `GET` | `/api/clips` | List generated clips |
| `POST` | `/api/clips/{clip_id}/upload` | Queue/upload clip |
| `GET` | `/api/uploads` | List upload queue |
| `POST` | `/api/clips/{clip_id}/subtitles/regenerate` | Rebuild subtitles and rerender |
| `GET` | `/api/analytics` | Fetch analytics summary |
| `POST` | `/api/analytics/refresh` | Queue durable analytics refresh |
| `GET` | `/api/jobs` | List durable jobs |
| `POST` | `/api/jobs/run-next` | Run due durable jobs manually |
| `POST` | `/api/clips/{clip_id}/rights` | Record rights/originality review |
| `POST` | `/api/clips/import-existing` | Import existing MP4 artifacts |
| `GET` | `/api/storage` | Storage lifecycle status |
| `POST` | `/api/storage/cleanup` | Queue cleanup/archive job |

## SQLite Schema

The ORM lives in `database/models.py`. A SQLite DDL snapshot is included in `database/schema.sql`.

Tables:

- `channels`: monitored YouTube channels and RSS state.
- `videos`: discovered source videos and processing paths.
- `clips`: viral clip timestamps, scores, metadata, subtitle path, MP4 path.
- `uploads`: YouTube upload queue/status records.
- `analytics`: point-in-time performance snapshots labeled `REAL` or `PREDICTED`.
- `processing_jobs` / `job_stages`: crash-resumable local work queue.
- `review_decisions`, `rights_reviews`, `quality_gate_results`: human review and upload safety gates.
- `negative_samples`: rejected, weak, failed, repetitive, and low-retention examples.
- `media_assets`: tracked files for cleanup/archive rules.
- `calibration_reports`: prediction-vs-outcome accuracy reports.

SQLite is the default:

```text
DATABASE_URL=sqlite+aiosqlite:///./database/shorts.db
```

PostgreSQL migration path:

```text
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/ai_shorts
```

The SQLAlchemy models avoid SQLite-only types, so adding Alembic later is straightforward.

## Local Development

Useful commands:

```powershell
python main.py
python -m compileall .
```

Keep `YOUTUBE_UPLOAD_ENABLED=false` while testing. Generated media is written under `data/`, and can be deleted safely between test runs if no processing job is active.

For low RAM:

- Use `qwen2.5:7b`, `llama3`, or `mistral`.
- Use `ggml-base.en.bin` or `ggml-small.en.bin` for whisper.cpp.
- Keep `MAX_CLIPS_PER_VIDEO=1` or `2`.
- Keep scheduler intervals longer while working on a laptop.

## Deployment Notes

Single-machine deployment:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Production hardening checklist:

- Move media storage to durable object storage.
- Add Alembic migrations before changing schema in production.
- Switch `DATABASE_URL` to PostgreSQL.
- Run workers separately from the API process for heavy video jobs.
- Put the API behind a reverse proxy with HTTPS and authentication.
- Use a process manager such as systemd, supervisord, Docker Compose, or a container orchestrator.
- Store OAuth tokens and client secrets in a secret manager.

## Notes on Free Execution

The default system uses local CPU/GPU resources, local models, SQLite, FFmpeg, OpenCV, yt-dlp, and whisper.cpp. YouTube API usage requires OAuth and quota, but no paid AI API is required.
