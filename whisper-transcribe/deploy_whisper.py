"""
Whisper Transcription Service on Modal
- AI-powered transcription for videos without YouTube captions
- Uses faster-whisper with large-v3-turbo for Japanese
- Downloads audio from YouTube via Cobalt API
- Returns segments in same format as transcript-service
"""

import modal
import tempfile
import os
from typing import Optional

app = modal.App("whisper-transcribe")

# Volume to cache whisper models - persists across cold starts
whisper_volume = modal.Volume.from_name("whisper-models", create_if_missing=True)

# Cache directory for whisper models (not /root/.cache which has existing files)
CACHE_DIR = "/whisper-cache"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "faster-whisper>=1.0.0",
        "fastapi[standard]",
        "httpx",
        "pydantic>=2.0",
    )
)

# Model to use - large-v3-turbo is fast and accurate for Japanese
MODEL_NAME = "large-v3-turbo"


@app.cls(
    image=image,
    gpu="T4",  # T4 is cost-effective for Whisper
    timeout=600,
    min_containers=0,
    scaledown_window=300,
    volumes={CACHE_DIR: whisper_volume},
)
class WhisperTranscribe:
    model = None

    @modal.enter()
    def setup(self):
        """Load Whisper model on container start."""
        from faster_whisper import WhisperModel

        print(f"Loading Whisper model: {MODEL_NAME}...")

        # Use GPU with float16 for speed
        self.model = WhisperModel(
            MODEL_NAME,
            device="cuda",
            compute_type="float16",
            download_root=CACHE_DIR,
        )

        print("Whisper model loaded!")

        # Commit volume so model persists
        whisper_volume.commit()

    def download_youtube_audio(self, video_id: str) -> str:
        """Download audio from YouTube video using public extraction services."""
        import httpx

        # Create temp file for audio
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "audio.mp3")

        print(f"Downloading audio for video: {video_id}")

        # Try multiple extraction services
        extractors = [
            self._try_y2mate,
            self._try_ssyoutube,
        ]

        for extractor in extractors:
            try:
                audio_url = extractor(video_id)
                if audio_url:
                    print(f"Got audio URL, downloading...")
                    response = httpx.get(
                        audio_url,
                        timeout=120,
                        follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0"}
                    )
                    if response.status_code == 200:
                        with open(output_path, "wb") as f:
                            f.write(response.content)
                        print(f"Audio saved: {output_path}")
                        return output_path
            except Exception as e:
                print(f"Extractor failed: {e}")
                continue

        raise Exception("All audio extractors failed. Please upload audio directly via /transcribe/audio")

    def _try_y2mate(self, video_id: str) -> str | None:
        """Try Y2mate extraction."""
        import httpx
        # Y2mate requires a multi-step process, skip for now
        return None

    def _try_ssyoutube(self, video_id: str) -> str | None:
        """Try ssyoutube extraction."""
        import httpx
        # SSYoutube also blocks cloud IPs
        return None

    def transcribe_audio(self, audio_path: str, language: str = "ja") -> dict:
        """Transcribe audio file using Whisper."""
        print(f"Transcribing audio: {audio_path}")

        # Transcribe with word timestamps
        segments_generator, info = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,  # Filter out silence
        )

        # Convert generator to list and format segments
        segments = []
        for segment in segments_generator:
            segments.append({
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "duration": round(segment.end - segment.start, 3),
                "text": segment.text.strip(),
            })

        total_duration = segments[-1]["end"] if segments else 0

        return {
            "available": True,
            "language": info.language,
            "languageCode": info.language,
            "isJapanese": info.language == "ja",
            "isGenerated": True,  # AI-generated, not YouTube captions
            "segments": segments,
            "totalSegments": len(segments),
            "totalDuration": round(total_duration, 3),
            "source": "whisper-modal",
            "model": MODEL_NAME,
            "language_probability": round(info.language_probability, 3),
        }

    @modal.asgi_app()
    def serve(self):
        """Serve FastAPI app with transcription endpoints."""
        from fastapi import FastAPI, HTTPException, UploadFile
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel
        import traceback

        api = FastAPI(
            title="Whisper Transcription API",
            description="AI-powered transcription using Whisper on Modal",
            version="1.0.0",
        )

        # Enable CORS
        api.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        class TranscribeRequest(BaseModel):
            url: str | None = None
            videoId: str | None = None
            language: str = "ja"

        @api.get("/transcribe")
        async def transcribe_get(
            videoId: str | None = None,
            url: str | None = None,
            language: str = "ja"
        ):
            """
            Transcribe a YouTube video using Whisper.

            GET /transcribe?videoId=VIDEO_ID
            GET /transcribe?url=https://youtube.com/watch?v=VIDEO_ID
            """
            return await do_transcribe(videoId, url, language)

        @api.post("/transcribe")
        async def transcribe_post(request: TranscribeRequest):
            """
            Transcribe a YouTube video using Whisper.

            POST /transcribe
            {"videoId": "VIDEO_ID"} or {"url": "https://youtube.com/..."}
            """
            return await do_transcribe(request.videoId, request.url, request.language)

        async def do_transcribe(
            video_id: str | None,
            url: str | None,
            language: str
        ):
            """Core transcription logic."""
            # Extract video ID from URL if provided
            if url and not video_id:
                video_id = extract_video_id(url)

            if not video_id:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide videoId or url parameter"
                )

            try:
                # Download audio
                audio_path = self.download_youtube_audio(video_id)

                # Transcribe
                result = self.transcribe_audio(audio_path, language)
                result["videoId"] = video_id

                # Cleanup
                try:
                    os.remove(audio_path)
                    os.rmdir(os.path.dirname(audio_path))
                except:
                    pass

                return result

            except Exception as e:
                print(f"Error transcribing: {traceback.format_exc()}")
                raise HTTPException(
                    status_code=500,
                    detail={
                        "available": False,
                        "videoId": video_id,
                        "message": f"Transcription failed: {str(e)}",
                        "source": "whisper-modal",
                    }
                )

        @api.get("/health")
        async def health():
            """Health check endpoint."""
            return {
                "status": "healthy",
                "service": "whisper-transcribe",
                "model": MODEL_NAME,
                "gpu": "T4",
            }

        @api.post("/transcribe/audio")
        async def transcribe_audio_upload(
            file: UploadFile,
            language: str = "ja",
        ):
            """
            Transcribe uploaded audio file directly.
            This is the recommended endpoint - upload audio from client.

            curl -X POST "https://URL/transcribe/audio" \
              -F "file=@audio.mp3" \
              -F "language=ja"
            """
            if not file:
                raise HTTPException(status_code=400, detail="No audio file provided")

            temp_dir = tempfile.mkdtemp()
            # Preserve original extension
            ext = os.path.splitext(file.filename)[1] if file.filename else ".mp3"
            audio_path = os.path.join(temp_dir, f"upload{ext}")

            # Read and save uploaded file
            content = await file.read()
            with open(audio_path, "wb") as f:
                f.write(content)

            print(f"Received audio file: {file.filename}, size: {len(content)} bytes")

            try:
                result = self.transcribe_audio(audio_path, language)
                result["filename"] = file.filename
                return result
            finally:
                try:
                    os.remove(audio_path)
                    os.rmdir(temp_dir)
                except:
                    pass

        @api.get("/")
        async def root():
            """Root endpoint with service info."""
            return {
                "service": "Whisper Transcription API",
                "version": "1.0.0",
                "model": MODEL_NAME,
                "endpoints": {
                    "transcribe_get": "GET /transcribe?videoId={id}&language=ja",
                    "transcribe_post": "POST /transcribe",
                    "transcribe_audio": "POST /transcribe/audio (upload audio file)",
                    "health": "GET /health",
                },
                "description": "AI-powered transcription for videos without YouTube captions",
            }

        return api


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    import re

    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',  # Just the ID
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


@app.local_entrypoint()
def main():
    """Local test entrypoint."""
    print("Whisper Transcription Service on Modal")
    print()
    print("Deploy with:")
    print("  modal deploy deploy_whisper.py")
    print()
    print("Test with:")
    print('  curl "https://YOUR_URL/transcribe?videoId=VIDEO_ID"')
