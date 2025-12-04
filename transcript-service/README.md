# YouTube Transcript Service

A Flask API that fetches Japanese transcripts from YouTube videos using existing YouTube captions.

**Production URL:** `https://modal-services-production.up.railway.app`

## Features

- Fetches Japanese transcripts from YouTube videos
- Prioritizes manual subtitles over auto-generated
- Returns structured segments with timestamps
- CORS enabled for cross-origin requests

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/get-japanese-transcript` | GET | Fetch Japanese transcript |
| `/health` | GET | Health check |
| `/` | GET | Service info |

## Usage

### Get Japanese Transcript

```bash
curl "https://modal-services-production.up.railway.app/get-japanese-transcript?videoId=cAFz4nWkJoA"
```

**Response:**
```json
{
  "available": true,
  "videoId": "cAFz4nWkJoA",
  "language": "Japanese",
  "languageCode": "ja",
  "isJapanese": true,
  "isGenerated": false,
  "totalSegments": 23,
  "totalDuration": 79.048,
  "segments": [
    {
      "start": 13.989,
      "duration": 1.263,
      "end": 15.252,
      "text": "あ！"
    }
  ]
}
```

---

## Deploy to Railway (Web Dashboard - No CLI)

### Step 1: Push to GitHub

First, create a GitHub repository and push this code:

```bash
cd transcript-service
git init
git add .
git commit -m "Initial commit: YouTube transcript service"
git remote add origin https://github.com/YOUR_USERNAME/transcript-service.git
git branch -M main
git push -u origin main
```

Or if using the modal-services monorepo, just push to that repo.

### Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Authorize Railway to access your GitHub (if not already)
5. Select your repository (`transcript-service` or `modal-services`)

### Step 3: Configure the Service

If using a monorepo (like modal-services):
1. Click on the service after it's created
2. Go to **Settings** → **Build**
3. Set **Root Directory** to: `transcript-service`

### Step 4: Set Environment Variables (Optional)

1. Go to **Variables** tab
2. Railway auto-detects `PORT` - no need to set it

### Step 5: Generate Domain

1. Go to **Settings** → **Networking**
2. Click **"Generate Domain"**
3. You'll get a URL like: `https://transcript-service-production-xxxx.up.railway.app`

Or add a custom domain:
1. Click **"Add Custom Domain"**
2. Enter: `transcript.appsparkle.org` (or your preferred subdomain)
3. Add the CNAME record to your DNS

### Step 6: Verify Deployment

```bash
# Health check
curl https://modal-services-production.up.railway.app/health

# Test transcript
curl "https://modal-services-production.up.railway.app/get-japanese-transcript?videoId=cAFz4nWkJoA"
```

---

## Moshimoshi Integration

Update the environment variable in moshimoshi:

```env
# .env.local
TRANSCRIPT_SERVER_URL=https://modal-services-production.up.railway.app
```

---

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run locally
python server.py
# Server runs on http://localhost:5000

# Test
curl "http://localhost:5000/get-japanese-transcript?videoId=cAFz4nWkJoA"
```

---

## Files

```
transcript-service/
├── server.py          # Flask application
├── requirements.txt   # Python dependencies
├── Procfile          # Railway/Heroku process file
├── railway.toml      # Railway configuration
├── .gitignore        # Git ignore rules
└── README.md         # This file
```

---

## Costs

Railway Hobby Plan (~$5/month):
- Always-on (no cold starts)
- 512MB RAM, shared CPU
- Auto-deploys from GitHub on push
- 99.9% SLA uptime
