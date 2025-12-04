"""
VOICEVOX TTS Service on Modal
High-quality Japanese text-to-speech using the official VOICEVOX Docker image
"""

import modal

app = modal.App("voicevox-tts")

# Use the official VOICEVOX CPU Docker image
image = modal.Image.from_registry(
    "voicevox/voicevox_engine:cpu-latest",
    add_python="3.11",
).pip_install("httpx", "fastapi[standard]", "uvicorn")


@app.function(
    image=image,
    cpu=4,
    memory=8192,
    timeout=600,
    min_containers=0,
    scaledown_window=300,
    secrets=[modal.Secret.from_name("moshimoshi-api-key")],
)
@modal.asgi_app()
def serve():
    """Proxy to VOICEVOX engine with OpenAI-compatible wrapper."""
    from fastapi import FastAPI, HTTPException, Response, Request
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    from pydantic import BaseModel
    import httpx
    import subprocess
    import time
    import threading
    import os

    api = FastAPI(title="VOICEVOX TTS API", version="1.0.0")

    # API Key from Modal secret
    API_KEY = os.environ.get("MOSHIMOSHI_API_KEY")

    # Auth middleware
    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Allow health check without auth
            if request.url.path == "/health":
                return await call_next(request)

            # Check API key
            api_key = request.headers.get("X-API-Key")
            if not api_key or api_key != API_KEY:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized", "detail": "Invalid or missing API key"}
                )
            return await call_next(request)

    api.add_middleware(AuthMiddleware)

    engine_ready = False
    engine_process = None

    def start_engine():
        nonlocal engine_ready, engine_process
        print("Starting VOICEVOX engine...")

        # The VOICEVOX Docker image runs the engine via /opt/voicevox_engine/run
        engine_process = subprocess.Popen(
            ["/opt/voicevox_engine/run", "--host", "0.0.0.0", "--port", "50021"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "VV_HOST": "0.0.0.0"},
        )

        # Wait for engine to be ready
        for i in range(180):  # 3 minutes timeout
            try:
                resp = httpx.get("http://localhost:50021/version", timeout=2)
                if resp.status_code == 200:
                    print(f"VOICEVOX engine ready: {resp.text}")
                    engine_ready = True
                    return
            except:
                pass
            time.sleep(1)
        print("VOICEVOX engine failed to start after 180s")

    threading.Thread(target=start_engine, daemon=True).start()

    class SpeechRequest(BaseModel):
        model: str = "voicevox"
        input: str
        voice: str = "1"  # Speaker ID
        speed: float = 1.0

    @api.post("/v1/audio/speech")
    async def create_speech(request: SpeechRequest):
        """OpenAI-compatible TTS endpoint."""
        # Wait for engine
        for _ in range(180):
            if engine_ready:
                break
            time.sleep(0.5)
        if not engine_ready:
            raise HTTPException(status_code=503, detail="Engine not ready")

        try:
            speaker_id = int(request.voice) if request.voice.isdigit() else 1

            async with httpx.AsyncClient() as client:
                # Step 1: Generate audio query
                query_resp = await client.post(
                    "http://localhost:50021/audio_query",
                    params={"text": request.input, "speaker": speaker_id},
                    timeout=60,
                )
                if query_resp.status_code != 200:
                    raise HTTPException(status_code=500, detail=f"Audio query failed: {query_resp.text}")

                query = query_resp.json()
                query["speedScale"] = request.speed

                # Step 2: Synthesize audio
                synth_resp = await client.post(
                    "http://localhost:50021/synthesis",
                    params={"speaker": speaker_id},
                    json=query,
                    timeout=120,
                )
                if synth_resp.status_code != 200:
                    raise HTTPException(status_code=500, detail=f"Synthesis failed: {synth_resp.text}")

                return Response(
                    content=synth_resp.content,
                    media_type="audio/wav",
                    headers={"Content-Disposition": "attachment; filename=speech.wav"},
                )

        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Request timeout")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @api.get("/v1/audio/voices")
    async def list_voices():
        """List available VOICEVOX speakers."""
        if not engine_ready:
            return {"voices": [], "status": "engine starting..."}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://localhost:50021/speakers", timeout=30)
                if resp.status_code == 200:
                    speakers = resp.json()
                    voices = []
                    for speaker in speakers:
                        for style in speaker.get("styles", []):
                            voices.append({
                                "id": str(style["id"]),
                                "name": f"{speaker['name']} ({style['name']})",
                            })
                    return {"voices": voices}
        except Exception as e:
            return {"voices": [], "error": str(e)}
        return {"voices": []}

    @api.get("/health")
    async def health():
        return {"status": "healthy" if engine_ready else "starting", "service": "voicevox-tts"}

    @api.get("/")
    async def root():
        return {
            "service": "VOICEVOX TTS",
            "status": "ready" if engine_ready else "starting",
            "usage": "POST /v1/audio/speech with {input: 'こんにちは', voice: '1'}",
            "voices_endpoint": "/v1/audio/voices",
            "auth": "Required - X-API-Key header",
        }

    return api
