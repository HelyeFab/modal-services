"""
Kokoro TTS Service on Modal - Minimal version for debugging
"""

import modal

app = modal.App("kokoro-tts")

kokoro_volume = modal.Volume.from_name("kokoro-models", create_if_missing=True)

# Simpler image - test if basic setup works
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("espeak-ng", "ffmpeg", "libsndfile1", "libespeak-ng1")
    .run_commands(
        # Verify espeak-ng is installed correctly
        "espeak-ng --version || echo 'espeak-ng not working'",
        "ls -la /usr/lib/x86_64-linux-gnu/libespeak* || echo 'no espeak libs found'",
    )
    .pip_install(
        "torch==2.4.1+cpu",
        extra_index_url="https://download.pytorch.org/whl/cpu",
    )
    .pip_install(
        "kokoro>=0.8",
        "soundfile",
        "fastapi[standard]",
        "numpy",
    )
    .env({
        "HF_HOME": "/root/.cache/huggingface",
        "PHONEMIZER_ESPEAK_PATH": "/usr/bin",
        "PHONEMIZER_ESPEAK_LIBRARY": "/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1",
    })
)


@app.function(
    image=image,
    cpu=4,
    memory=8192,
    timeout=300,
    volumes={"/root/.cache": kokoro_volume},
)
@modal.asgi_app()
def serve():
    """Serve FastAPI app - simple function-based approach."""
    from fastapi import FastAPI, HTTPException, Response
    from pydantic import BaseModel, Field
    import io

    api = FastAPI(title="Kokoro TTS API", version="1.0.0")

    # Lazy-loaded pipeline
    _pipeline = None

    def get_pipeline():
        nonlocal _pipeline
        if _pipeline is None:
            print("Loading Kokoro pipeline...")
            from kokoro import KPipeline
            _pipeline = KPipeline(lang_code="a")
            print("Pipeline loaded!")
            kokoro_volume.commit()
        return _pipeline

    class SpeechRequest(BaseModel):
        model: str = "kokoro"
        input: str
        voice: str = "af_heart"
        response_format: str = "wav"
        speed: float = Field(default=1.0, ge=0.25, le=4.0)

    @api.post("/v1/audio/speech")
    async def create_speech(request: SpeechRequest):
        """Generate speech from text."""
        try:
            import numpy as np
            import soundfile as sf

            pipeline = get_pipeline()

            audio_chunks = []
            for gs, ps, audio in pipeline(
                request.input,
                voice=request.voice,
                speed=request.speed,
            ):
                if audio is not None:
                    audio_chunks.append(audio)

            if not audio_chunks:
                raise HTTPException(status_code=500, detail="No audio generated")

            full_audio = np.concatenate(audio_chunks)
            buffer = io.BytesIO()
            sf.write(buffer, full_audio, 24000, format="WAV")
            buffer.seek(0)

            return Response(
                content=buffer.read(),
                media_type="audio/wav",
                headers={"Content-Disposition": "attachment; filename=speech.wav"},
            )
        except Exception as e:
            import traceback
            print(f"Error: {e}")
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))

    @api.get("/v1/audio/voices")
    async def list_voices():
        return {"voices": ["af_heart", "af_bella", "am_adam", "bf_emma", "bm_george"]}

    @api.get("/v1/models")
    async def list_models():
        return {"object": "list", "data": [{"id": "kokoro", "object": "model", "owned_by": "kokoro"}]}

    @api.get("/health")
    async def health():
        return {"status": "healthy", "service": "kokoro-tts"}

    @api.get("/")
    async def root():
        return {"service": "Kokoro TTS", "status": "running"}

    return api
