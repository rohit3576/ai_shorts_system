# Real Creator Intelligence Platform Guide

This project is now designed to be operated as a local-first creator workflow, not a blind reposting machine. The system can generate Shorts, but the useful learning comes only after you upload reviewed clips and collect real YouTube outcomes.

## A. Local Environment Setup

Use Windows PowerShell unless a command says otherwise.

### 1. Install Python

1. Download Python 3.11 or 3.12 from https://www.python.org/downloads/windows/.
2. During install, check **Add python.exe to PATH**.
3. Verify:

```powershell
python --version
pip --version
```

If `python` is not found, reopen PowerShell. If it still fails, reinstall Python and check the PATH option.

### 2. Install Git

Download Git for Windows from https://git-scm.com/download/win.

```powershell
git --version
```

### 3. Install FFmpeg

Recommended beginner path:

```powershell
winget install Gyan.FFmpeg
```

Close and reopen PowerShell, then verify:

```powershell
ffmpeg -version
ffprobe -version
```

If that fails, add the FFmpeg `bin` folder to Windows PATH manually.

### 4. Install Ollama

Download Ollama from https://ollama.com/download/windows.

```powershell
ollama --version
ollama pull qwen2.5:7b
ollama serve
```

If `ollama serve` says the port is already in use, Ollama is probably already running.

### 5. Set Up whisper.cpp

The easiest path for this project is the Python package:

```powershell
python -m pip install whisper.cpp-cli
```

Download a small model:

```powershell
mkdir models
curl.exe -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin?download=true" -o models\ggml-tiny.en.bin
```

Verify:

```powershell
whisper-cpp --help
```

Some installs expose `whisper-cli` instead. If so, set `WHISPER_CPP_BINARY=whisper-cli` in `.env`.

### 6. Install Node.js

Download the LTS version from https://nodejs.org/.

```powershell
node --version
npm --version
```

### 7. Create the Python Virtual Environment

From the project root:

```powershell
cd "C:\Users\ashok\Documents\FreeLancing Projects\Sample App\YouTube Agent\ai_shorts_system"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### 8. Install Python Requirements

```powershell
pip install -r requirements.txt
```

### 9. Install Dashboard Dependencies

```powershell
cd app\dashboard\frontend
npm install
npm run build
cd ..\..\..
```

### 10. Configure `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Important beginner defaults:

```text
YOUTUBE_UPLOAD_ENABLED=false
SCHEDULER_ENABLED=true
STORAGE_CLEANUP_MODE=mark_only
OLLAMA_MODEL=qwen2.5:7b
WHISPER_CPP_BINARY=whisper-cpp
WHISPER_MODEL_PATH=models/ggml-tiny.en.bin
```

Run the app:

```powershell
python main.py
```

Open:

```text
http://127.0.0.1:8000
```

Useful folders:

```text
data/videos/       downloaded source videos
data/audio/        WAV files for transcription
data/transcripts/  normalized transcript JSON
data/clips/        rendered Shorts
data/training/     JSONL/CSV learning exports
database/shorts.db SQLite database
temp/              temporary files
models/            whisper.cpp models
```

## B. YouTube Setup

### 1. Create YouTube Channels Carefully

Do not start by risking your personal main account. Create a new Brand Account or test channel first.

Begin with at most two channels:

- Gaming clips from gameplay you recorded or have permission to use.
- Nature/survival storytelling using owned, licensed, public-domain, or commentary-added footage.

### 2. Create a Brand Account

1. Go to YouTube.
2. Open your account menu.
3. Choose **Switch account**.
4. Choose **View all channels**.
5. Create a channel.
6. Use a clear niche name, not a misleading impersonation.

### 3. Enable APIs

Go to https://console.cloud.google.com/.

1. Create a Google Cloud project.
2. Open **APIs & Services > Library**.
3. Enable **YouTube Data API v3**.
4. Enable **YouTube Analytics API**.

### 4. Create OAuth Credentials

1. Open **APIs & Services > OAuth consent screen**.
2. Choose External for a personal project.
3. Add yourself as a test user.
4. Open **Credentials**.
5. Create **OAuth client ID**.
6. Application type: **Desktop app**.
7. Download the JSON file.
8. Rename it:

```text
client_secret.json
```

9. Place it in the project root:

```text
ai_shorts_system/client_secret.json
```

### 5. Authenticate Uploads

Keep uploads disabled until you are ready:

```text
YOUTUBE_UPLOAD_ENABLED=false
```

When ready:

```text
YOUTUBE_UPLOAD_ENABLED=true
YOUTUBE_PRIVACY_STATUS=private
```

The first upload opens a browser OAuth flow and writes:

```text
youtube_token.json
```

Do not commit `client_secret.json` or `youtube_token.json`.

### 6. Quota and Policy Warnings

YouTube API quota is limited. Uploads are expensive compared with reads. Avoid test-spamming uploads.

Policy reality:

- Reused-content channels may fail monetization review.
- Reposting streamers, creators, or shows without permission can trigger copyright claims or strikes.
- Shorts automation does not remove your responsibility for rights, originality, and community guidelines.

## C. Content Acquisition Guide

Safer sources:

- Your own gameplay.
- Your own camera footage.
- Creator clips with written permission.
- Podcasts where you have clipping permission.
- Public-domain footage with source records.
- Licensed footage with license files saved.
- Transformative commentary or narration-added edits.

Risky sources:

- Blindly downloading popular channels.
- Reposting Outdoor Boys, streamers, podcasts, documentaries, sports, TV, or movie clips without permission.
- Uploading mass clips with no commentary, no transformation, and no review.

Why blindly reposting Outdoor Boys or streamers is risky:

- The footage is not yours.
- You may not have commercial rights.
- YouTube can classify the channel as reused content.
- Claims can arrive after views accumulate.
- Monetization review is stricter than initial upload checks.

The platform now requires a structured rights/originality review before upload:

- owned content
- licensed content
- commentary added
- narration added
- transformative edit
- approved for upload

If the clip cannot honestly pass that review, do not upload it.

## D. First Real Usage Flow

### 1. Add a Source Channel

Use the dashboard Channels page or API:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/channels `
  -H "Content-Type: application/json" `
  -d "{\"url\":\"https://www.youtube.com/@YourSource\",\"name\":\"Test Source\",\"niche_type\":\"gaming\"}"
```

### 2. Download and Process Long-Form Video

Queue durable processing:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/process
```

Run due jobs manually if needed:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/jobs/run-next
```

### 3. Generate Candidate Shorts

The durable job system downloads, extracts audio, transcribes, detects clips, scores retention, renders, and stores canonical records.

Every successful Short creates:

- Video row
- Clip row
- ClipIntelligence row
- LearningEvent row
- AnalyticsSnapshot row marked `PREDICTED`

Real analytics only appears after YouTube upload snapshots.

### 4. Review Clips Manually

Use labels honestly:

- boring
- weak hook
- no payoff
- repetitive
- confusing
- low energy
- policy risk
- strong pacing
- high tension
- policy risk
- viral potential

Reject weak clips. Rejections are useful negative samples.

### 5. Approve or Reject

Approve only clips you would be comfortable publishing under your channel name.

Reject clips that feel slow, repetitive, confusing, or legally risky.

### 6. Regenerate Hooks

Use hook regeneration when the moment is good but the opening line is weak. The system stores the action as a learning signal.

### 7. Render Final Short

Rendered MP4s live in:

```text
data/clips/
```

Existing `final_short.mp4` and preview files are imported automatically into database records on app startup.

### 8. Upload Manually First

Start with private uploads. Before upload, submit the rights review:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/clips/1/rights `
  -H "Content-Type: application/json" `
  -d "{\"owned_content\":true,\"licensed_content\":false,\"commentary_added\":true,\"narration_added\":false,\"transformative_edit\":true,\"approved_for_upload\":true,\"policy_notes\":\"Own gameplay with commentary.\"}"
```

Queue upload:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/clips/1/upload `
  -H "Content-Type: application/json" `
  -d "{\"rights_review\":{\"owned_content\":true,\"commentary_added\":true,\"transformative_edit\":true,\"approved_for_upload\":true}}"
```

### 9. Track Analytics

Snapshots are collected at:

- 1 hour
- 6 hours
- 24 hours
- 72 hours
- 7 days

The dashboard shows `No real analytics collected yet.` until real YouTube data exists.

### 10. Compare Predictions vs Outcomes

Training exports are written to:

```text
data/training/clip_outcomes.jsonl
data/training/successful_clips.jsonl
data/training/failed_clips.jsonl
data/training/hook_performance.jsonl
data/training/dead_zone_patterns.jsonl
data/training/clip_outcomes.csv
data/training/calibration_report.json
data/training/calibration_report.csv
```

Calibration compares predicted retention, virality, and hook strength against real analytics.

## E. Channel Strategy Guide

Start with two channels max.

Recommended first niches:

- Gaming: your own gameplay, highlights, fails, clutch moments, challenge runs.
- Nature/survival: owned footage, licensed footage, public domain, or commentary/narration-added storytelling.

Do not spam uploads. A realistic early cadence:

- 1 to 2 Shorts per day per channel.
- Review every clip manually.
- Keep weak clips private or reject them.
- Track retention at 24 hours and 7 days.
- Make one change per batch: hook style, duration, subtitles, pacing, or upload time.

Quality beats volume because:

- Low-retention uploads can train you into bad habits.
- Reused or low-effort content can damage monetization chances.
- A solo creator can review 2 good clips per day better than 20 mediocre ones.

## F. Monetization Reality Check

Shorts RPM is often low. Many channels earn cents per thousand Shorts views, not dollars. RPM varies by country, niche, ad market, viewer behavior, and monetization status.

Practical expectations:

- First month: learn workflow, avoid policy mistakes, collect data.
- Months 2-3: identify hooks and pacing that retain viewers.
- Months 3-6: maybe meaningful growth if retention and originality are strong.
- Revenue usually follows audience trust, not automation volume.

Why retention matters:

- Swipe-away kills distribution.
- Strong first 1-3 seconds matter.
- Payoff must arrive quickly.
- Rewatchable clips can outperform longer but flatter clips.

Why originality matters:

- Monetization review looks for reused content.
- Commentary, narration, editing, structure, and packaging need to add real value.
- Permission and licensing reduce platform and legal risk.

Common beginner mistakes:

- Uploading too many unreviewed clips.
- Copying big creators without permission.
- Treating predicted scores as facts.
- Ignoring bad analytics.
- Keeping every downloaded source file forever.
- Changing ten variables at once.

Sustainable approach:

- Build a small library of rights-safe sources.
- Keep a review log.
- Compare predictions to outcomes weekly.
- Delete or archive old heavy files.
- Improve one workflow step at a time.

## G. Troubleshooting Guide

### FFmpeg Not Found

```powershell
ffmpeg -version
```

If not found:

```powershell
winget install Gyan.FFmpeg
```

Reopen PowerShell. Check Windows PATH.

### Ollama Not Running

```powershell
ollama serve
ollama list
```

If the model is missing:

```powershell
ollama pull qwen2.5:7b
```

### whisper.cpp Errors

Check binary:

```powershell
whisper-cpp --help
whisper-cli --help
```

If your command is `whisper-cli`, update `.env`:

```text
WHISPER_CPP_BINARY=whisper-cli
```

Check model path:

```powershell
Test-Path models\ggml-tiny.en.bin
```

### yt-dlp Issues

Update:

```powershell
pip install --upgrade yt-dlp
```

Some videos block downloads, require login, or are not safe to repurpose. Do not fight rights restrictions for content you do not own.

### Windows PATH Issues

After installing Python, Git, FFmpeg, Node, or Ollama:

1. Close PowerShell.
2. Open a new PowerShell window.
3. Run the version command again.
4. If still broken, edit **Environment Variables > Path**.

### Upload Failures

Check:

- `YOUTUBE_UPLOAD_ENABLED=true`
- `client_secret.json` exists
- OAuth test user is added
- YouTube Data API is enabled
- Clip has passed rights review
- Clip status is approved
- Rendered MP4 exists

Uploads are blocked if the quality gate fails.

### OAuth Issues

Delete the token and retry:

```powershell
Remove-Item youtube_token.json
python main.py
```

Make sure the OAuth client type is **Desktop app**.

### Rendering Failures

Check:

```powershell
ffmpeg -version
Test-Path data\videos
Test-Path data\transcripts
```

Failed renders are stored as negative samples so they can be inspected instead of disappearing.

### Storage Growing Too Large

Default cleanup mode is safe:

```text
STORAGE_CLEANUP_MODE=mark_only
```

To archive instead of only marking expired files:

```text
STORAGE_CLEANUP_MODE=archive
```

Use `delete` only when you are confident:

```text
STORAGE_CLEANUP_MODE=delete
```

## H. Final Goal

The goal is not to create a spam machine. The goal is to turn a local laptop into a careful creator intelligence system:

- ingest safely
- generate candidates
- review honestly
- upload responsibly
- collect real outcomes
- preserve failures
- calibrate predictions
- improve future clips
- stay policy safer
- keep storage under control

When the dashboard says there is no real analytics yet, believe it. The system learns from reality only after reviewed uploads receive real viewer data.
