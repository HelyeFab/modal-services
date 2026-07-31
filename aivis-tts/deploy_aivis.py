"""
AivisSpeech TTS on Modal — single-voice replacement for the Sheldon shim.

Serves the SAME contract as `tts.appsparkle.org`:
    POST /v1/audio/speech   {model, input, voice, speed}   header: X-API-Key
    -> audio/mpeg (MP3)

Why single-voice: only one Japanese voice is in use (阿井田茂 / Aida Shigeru).
Baking exactly one model into the image means NO modal.Volume, no persistent
state, and no repeat of the uid-1000 empty-volume permission crash that bit the
Sheldon deployment.

Deploy:  modal deploy deploy_aivis.py
"""

import modal

app = modal.App("aivis-tts")

# 阿井田茂 (Aida Shigeru) — AivisHub, owner `khirio`, middle-aged male, 7 styles.
# Speaker id 1310138976 = the ノーマル style (the one actually in use since 2026-07-30).
AIVM_UUID = "47e53151-a378-46f3-abee-ce13aa07feb1"
DEFAULT_SPEAKER = 1310138976

ENGINE_PORT = 10101
ENGINE_DIR = "/opt/aivisspeech-engine"

# The image's Cmd is `gosu user … poetry run python ./run.py`, i.e. a POETRY run,
# not a PyInstaller build — so the engine uses the "-Dev" data directory.
# (This is why the Sheldon volume was mounted at .../AivisSpeech-Engine-Dev.)
MODELS_DIR = "/home/user/.local/share/AivisSpeech-Engine-Dev/Models"

image = (
    modal.Image.from_registry(
        "ghcr.io/aivis-project/aivisspeech-engine:cpu-latest",
        add_python="3.11",
    )
    .apt_install("ffmpeg", "curl", "gosu")
    .pip_install("httpx", "fastapi[standard]", "uvicorn")
    .run_commands(
        # Bake the single voice model in at build time.
        # api.aivis-project.com 307-redirects to a *signed* R2 URL that expires in
        # 1h, so always fetch through the api host (-L) and never hardcode the R2 link.
        f"mkdir -p {MODELS_DIR}",
        f'curl -fsSL "https://api.aivis-project.com/v1/aivm-models/{AIVM_UUID}'
        f'/download?model_type=AIVMX" -o {MODELS_DIR}/aida-shigeru.aivmx',
        # Fail the BUILD (not the first request) if the download silently produced
        # something that isn't a model.
        f'test -s {MODELS_DIR}/aida-shigeru.aivmx',
        # The engine runs as uid 1000 via gosu. Fixing ownership here — at build
        # time, deterministically — is what avoids the runtime PermissionError.
        "chown -R 1000:1000 /home/user/.local",
    )
)


@app.function(
    image=image,
    cpu=4,
    memory=8192,
    timeout=600,
    min_containers=0,      # scale to zero; revisit after the cold-start benchmark
    scaledown_window=600,  # stay warm 10min so a study session doesn't re-pay cold start
    # Holds the SAME key the Sheldon shim used, so consumers need only a URL
    # change — every stored key (ReadAloud data.json, Chiba .env.local, both Anki
    # bake scripts) stays valid.
    secrets=[modal.Secret.from_name("aivis-tts-key")],
)
@modal.asgi_app()
def serve():
    import os
    import re
    import time
    import threading
    import subprocess

    import httpx
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from pydantic import BaseModel

    api = FastAPI(title="AivisSpeech TTS", version="1.0.0")
    API_KEY = os.environ.get("AIVIS_API_KEY")

    # ---------------------------------------------------------------- auth
    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.url.path in ("/health", "/"):
                return await call_next(request)
            if request.headers.get("X-API-Key") != API_KEY:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized",
                             "detail": "Invalid or missing X-API-Key"},
                )
            return await call_next(request)

    api.add_middleware(AuthMiddleware)

    # CORS is added AFTER auth so it ends up OUTERMOST (Starlette runs middleware in
    # reverse-add order). Browsers omit auth headers on OPTIONS preflight, so if auth
    # ran first every preflight would 401. Anki card templates depend on this.
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    # ------------------------------------------------------- text cleaning
    # Ported from the Sheldon shim (aivis-shim.py), which exists ONLY on that box.
    # Behaviour is reconstructed from the 2026-07-30 record — the version that WON
    # the A/B against the Kokoro multi-voice build.
    JP = r"぀-ゟ゠-ヿ一-鿿々〆ー"

    # Keep: Japanese, Latin letters, digits, apostrophe, period, hyphen, whitespace,
    # and basic sentence punctuation. Drop: emoji, pictographs, stray symbols.
    # The critical part is that Latin is KEPT — the old regex stripped it, so English
    # words were silently DELETED instead of being transliterated by the engine.
    _DROP = re.compile(rf"[^{JP}A-Za-z0-9'’.\-,!?。、！？「」 \t\n]")

    # Collapse whitespace ONLY where it sits between two Japanese characters — that
    # is a furigana-layout artifact. Spaces around/between Latin words are preserved
    # so "Hello World" doesn't get glued into "HelloWorld".
    _JP_SPACE = re.compile(rf"(?<=[{JP}])[ \t]+(?=[{JP}])")

    def clean_for_speech(text: str) -> str:
        text = _DROP.sub("", text)
        text = _JP_SPACE.sub("", text)
        return re.sub(r"[ \t]{2,}", " ", text).strip()

    # ------------------------------------------------------------- engine
    engine_ready = False

    def start_engine():
        nonlocal engine_ready
        print("starting AivisSpeech engine…")
        subprocess.Popen(
            ["gosu", "user", "/opt/python/bin/poetry", "run", "python", "./run.py",
             "--host", "127.0.0.1", "--port", str(ENGINE_PORT)],
            cwd=ENGINE_DIR,
        )
        for _ in range(300):
            try:
                r = httpx.get(f"http://127.0.0.1:{ENGINE_PORT}/version", timeout=2)
                if r.status_code == 200:
                    print(f"engine ready: {r.text}")
                    engine_ready = True
                    return
            except Exception:
                pass
            time.sleep(1)
        print("engine FAILED to become ready within 300s")

    threading.Thread(target=start_engine, daemon=True).start()

    def await_engine(limit: int = 300) -> None:
        for _ in range(limit * 2):
            if engine_ready:
                return
            time.sleep(0.5)
        raise HTTPException(status_code=503, detail="engine not ready")

    # ------------------------------------------------------------- routes
    class SpeechRequest(BaseModel):
        model: str = "tts-1"
        input: str
        voice: str = ""
        # SPEED IS CLIENT-SIDE. 1.0 approved by ear 2026-07-31 for this voice,
        # replacing the 0.80 that had been chosen for M2 on 2026-07-19 — a
        # different voice, so the old value did not carry over. Consumers each
        # carry their own value and must be updated when repointed here.
        speed: float = 1.0

    @api.post("/v1/audio/speech")
    async def create_speech(req: SpeechRequest):
        await_engine()

        text = clean_for_speech(req.input)
        if not text:
            raise HTTPException(status_code=400, detail="nothing speakable in input")

        # SINGLE-VOICE BUILD: only one model is installed, so any incoming id —
        # Aida's own, the legacy M2 1368642336 still in the Anki scripts, にせ,
        # the ancient "23", or empty — resolves to the one voice. This is what
        # makes the stale-voice drift across consumers self-healing.
        speaker = DEFAULT_SPEAKER

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{ENGINE_PORT}") as c:
            q = await c.post("/audio_query",
                             params={"text": text, "speaker": speaker}, timeout=60)
            if q.status_code != 200:
                raise HTTPException(status_code=502,
                                    detail=f"audio_query failed: {q.text[:300]}")
            query = q.json()
            query["speedScale"] = req.speed

            s = await c.post("/synthesis", params={"speaker": speaker},
                             json=query, timeout=180)
            if s.status_code != 200:
                raise HTTPException(status_code=502,
                                    detail=f"synthesis failed: {s.text[:300]}")

        # Transcode WAV -> MP3 so the response is byte-compatible with what the
        # Sheldon shim returned (audio/mpeg). ReadAloud, Chiba's cache and the Anki
        # bake scripts all expect MP3; vvox_persist sniffs magic bytes.
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-vn", "-b:a", "96k", "-f", "mp3", "pipe:1"],
            input=s.content, capture_output=True,
        )
        if proc.returncode != 0 or not proc.stdout:
            raise HTTPException(
                status_code=500,
                detail=f"mp3 transcode failed: {proc.stderr.decode()[:300]}")

        return Response(content=proc.stdout, media_type="audio/mpeg")

    @api.get("/v1/audio/voices")
    async def list_voices():
        if not engine_ready:
            return {"voices": [], "status": "starting"}
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{ENGINE_PORT}") as c:
            r = await c.get("/speakers", timeout=30)
        if r.status_code != 200:
            return {"voices": [], "error": r.text[:300]}
        return {"voices": [
            {"id": str(st["id"]), "name": f"{sp['name']} ({st['name']})"}
            for sp in r.json() for st in sp.get("styles", [])
        ], "default": str(DEFAULT_SPEAKER)}

    @api.get("/health")
    async def health():
        return {"status": "healthy" if engine_ready else "starting",
                "service": "aivis-tts", "speaker": DEFAULT_SPEAKER}

    @api.get("/")
    async def root():
        return {
            "service": "AivisSpeech TTS (single voice: 阿井田茂 / Aida Shigeru)",
            "status": "ready" if engine_ready else "starting",
            "usage": "POST /v1/audio/speech {input, speed} + X-API-Key -> audio/mpeg",
            "note": "voice field is ignored — one model is installed",
        }

    return api
