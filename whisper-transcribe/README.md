# Whisper Transcription Service on Modal

AI-powered transcription for YouTube videos using OpenAI's Whisper model. This service complements the YouTube Transcript Service by providing transcription for videos that don't have captions.

## Features

- **Whisper large-v3-turbo** - Fast and accurate, optimized for Japanese
- **YouTube audio download** - Automatic via yt-dlp
- **GPU-accelerated** - Runs on NVIDIA T4
- **Same response format** - Compatible with transcript-service
- **Auto-scaling** - Scales to zero when idle

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/transcribe` | GET/POST | Transcribe YouTube video |
| `/health` | GET | Health check |
| `/` | GET | Service info |

## Usage

### Transcribe a Video

**GET request:**
```bash
curl "https://YOUR_MODAL_URL/transcribe?videoId=VIDEO_ID&language=ja"
```

**POST request:**
```bash
curl -X POST "https://YOUR_MODAL_URL/transcribe" \
  -H "Content-Type: application/json" \
  -d '{"videoId": "VIDEO_ID", "language": "ja"}'
```

**With YouTube URL:**
```bash
curl "https://YOUR_MODAL_URL/transcribe?url=https://youtube.com/watch?v=VIDEO_ID"
```

### Response Format

```json
{
  "available": true,
  "videoId": "VIDEO_ID",
  "language": "ja",
  "languageCode": "ja",
  "isJapanese": true,
  "isGenerated": true,
  "totalSegments": 45,
  "totalDuration": 180.5,
  "source": "whisper-modal",
  "model": "large-v3-turbo",
  "segments": [
    {
      "start": 0.0,
      "end": 3.5,
      "duration": 3.5,
      "text": "こんにちは"
    }
  ]
}
```

---

## Deployment

### Prerequisites

```bash
pip install modal
modal setup
```

### Deploy

```bash
# From the modal-services directory
py -3.12 whisper-transcribe/run_deploy.py

# Or directly (may have encoding issues on Windows)
py -3.12 -m modal deploy whisper-transcribe/deploy_whisper.py
```

### Endpoint URL

After deployment:
```
https://emmanuelfabiani23--whisper-transcribe-whispertranscribe-serve.modal.run
```

---

## Integration with Moshimoshi

Add the Whisper endpoint as a fallback in moshimoshi's transcript fetching chain:

```env
# .env.local
WHISPER_TRANSCRIBE_URL=https://YOUR_MODAL_URL
```

**Fallback chain:**
1. Firebase Cache
2. Railway (YouTube Transcript API)
3. YouTubei.js
4. **Modal Whisper** (new - for videos without captions)
5. Supa API

---

## Costs

| Resource | Cost | Notes |
|----------|------|-------|
| T4 GPU | ~$0.59/hr | Only charged when processing |
| Cold start | ~$0.02 | First request after idle |
| Per video | ~$0.01-0.05 | Depends on video length |

**Example costs:**
- 5-minute video: ~$0.01 (30 sec processing)
- 1-hour video: ~$0.10 (6 min processing)
- Idle: $0 (scales to zero)

---

## Performance

| Metric | Value |
|--------|-------|
| Model | large-v3-turbo |
| Speed | ~10x realtime on T4 |
| Cold start | 20-30 seconds |
| Warm request | Video duration / 10 |

**Example processing times:**
- 3-minute video: ~20 seconds
- 10-minute video: ~1 minute
- 1-hour video: ~6 minutes

---

## Configuration

### Change Model

Edit `deploy_whisper.py`:

```python
MODEL_NAME = "large-v3-turbo"  # Default - fast, good accuracy

# Alternatives:
# MODEL_NAME = "large-v3"       # Slower but slightly better
# MODEL_NAME = "medium"         # Faster, less accurate
# MODEL_NAME = "small"          # Even faster
```

### Change GPU

```python
@app.cls(
    gpu="T4",    # Default: ~$0.59/hr
    # gpu="L4",  # ~$0.84/hr - faster
    # gpu="A10G", # ~$1.10/hr - fastest
)
```

---

## Files

```
whisper-transcribe/
├── deploy_whisper.py  # Main Modal deployment
├── run_deploy.py      # Windows deploy helper
└── README.md          # This file
```

---

## Comparison: YouTube Captions vs Whisper

| Aspect | YouTube Captions (Railway) | Whisper (Modal) |
|--------|---------------------------|-----------------|
| Speed | Instant | 10-60 seconds |
| Cost | Free | ~$0.01-0.10/video |
| Availability | Only if video has captions | Always works |
| Accuracy | Varies (manual vs auto) | Consistent high quality |
| Use case | First choice | Fallback for no-caption videos |
