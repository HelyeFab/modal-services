"""
Ollama LLM Service on Modal
- Qwen 2.5 32B for high-quality Japanese language processing
- Excellent for: grammar explanations, translations, story generation
- Model cached in Volume (no download on cold start)
- OpenAI-compatible /v1/chat/completions endpoint
- Protected with API key authentication

GPU Requirements:
- A10G (24GB VRAM) - fits quantized 32B model
- First download: ~20GB, takes 5-10 minutes
- Subsequent cold starts: 30-60 seconds
"""

import modal
import subprocess
import time
import os

app = modal.App("ollama-llm")

# Volume to cache ollama models - persists across cold starts
# Using larger volume for 32B model (~20GB)
ollama_volume = modal.Volume.from_name("ollama-models-large", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl")
    .run_commands(
        "curl -fsSL https://ollama.com/install.sh | sh",
    )
    .pip_install("fastapi[standard]", "httpx")
)

# Qwen 2.5 32B - Excellent Japanese language support
# ~20GB download, requires A10G GPU (24GB VRAM)
MODEL_NAME = "qwen2.5:32b"


def start_ollama_server():
    """Start ollama server and wait for it to be ready."""
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for server to be ready - longer timeout for large model
    for i in range(60):  # Up to 60 seconds for 32B model loading
        try:
            import httpx
            httpx.get("http://localhost:11434/api/tags", timeout=2)
            print(f"Ollama server ready after {i+1} seconds")
            return True
        except:
            time.sleep(1)
    return False


def ensure_model_pulled():
    """Pull model if not already cached in volume."""
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
    )
    if MODEL_NAME.split(":")[0] in result.stdout:
        print(f"Model {MODEL_NAME} already cached")
        return

    print(f"Pulling {MODEL_NAME} (first time only, will be cached)...")
    subprocess.run(["ollama", "pull", MODEL_NAME], check=True)
    print(f"Model {MODEL_NAME} pulled and cached!")


@app.cls(
    image=image,
    gpu="A10G",  # 24GB VRAM - required for 32B model (~$0.38/hr)
    timeout=900,  # 15 min timeout for long generations
    min_containers=0,  # Scale to zero when idle
    scaledown_window=600,  # Keep warm for 10 min (reduces cold starts)
    volumes={"/root/.ollama": ollama_volume},
    secrets=[modal.Secret.from_name("moshimoshi-api-key")],
)
class OllamaLLM:
    @modal.enter()
    def setup(self):
        """Start ollama and ensure model is available."""
        print("Starting Ollama server...")
        if not start_ollama_server():
            raise RuntimeError("Failed to start Ollama server")
        print("Ollama server ready!")

        ensure_model_pulled()

        # Commit volume so model persists
        ollama_volume.commit()

    @modal.asgi_app()
    def serve(self):
        """Serve FastAPI app with OpenAI-compatible routes."""
        from fastapi import FastAPI, Request
        from fastapi.responses import StreamingResponse, JSONResponse
        from starlette.middleware.base import BaseHTTPMiddleware
        import httpx

        api = FastAPI(title="Ollama LLM")

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

        @api.post("/v1/chat/completions")
        async def chat_completions(request_body: dict):
            """
            OpenAI-compatible chat completions endpoint with streaming support.

            Model: Qwen 2.5 32B - excellent for Japanese language tasks.

            Usage with openai library:
                from openai import OpenAI
                client = OpenAI(base_url="https://YOUR_MODAL_URL", api_key="your-key")

                # Non-streaming
                response = client.chat.completions.create(
                    model="qwen2.5:32b",
                    messages=[{"role": "user", "content": "Hello!"}]
                )

                # Streaming
                for chunk in client.chat.completions.create(
                    model="qwen2.5:32b",
                    messages=[{"role": "user", "content": "Hello!"}],
                    stream=True
                ):
                    print(chunk.choices[0].delta.content, end="")
            """
            stream = request_body.get("stream", False)

            payload = {
                "model": request_body.get("model", MODEL_NAME),
                "messages": request_body.get("messages", []),
                "temperature": request_body.get("temperature", 0.7),
                "max_tokens": request_body.get("max_tokens", 4096),  # Higher default for 32B
                "stream": stream,
            }

            if stream:
                async def stream_response():
                    async with httpx.AsyncClient() as client:
                        async with client.stream(
                            "POST",
                            "http://localhost:11434/v1/chat/completions",
                            json=payload,
                            timeout=300,  # 5 min for large generations
                        ) as response:
                            async for line in response.aiter_lines():
                                if line:
                                    yield line + "\n"

                return StreamingResponse(
                    stream_response(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:11434/v1/chat/completions",
                        json=payload,
                        timeout=300,  # 5 min for large generations
                    )
                return response.json()

        @api.post("/generate")
        async def generate(request_body: dict):
            """
            Simple generate endpoint for quick prompts with streaming support.

            Model: Qwen 2.5 32B

            POST /generate
            {"prompt": "Summarize: ...", "max_tokens": 256}

            POST /generate (streaming)
            {"prompt": "Summarize: ...", "max_tokens": 256, "stream": true}

            POST /generate (JSON mode)
            {"prompt": "Return JSON: ...", "format": "json"}
            """
            stream = request_body.get("stream", False)

            payload = {
                "model": request_body.get("model", MODEL_NAME),
                "prompt": request_body.get("prompt", ""),
                "options": {
                    "num_predict": request_body.get("max_tokens", 4096),
                    "temperature": request_body.get("temperature", 0.7),
                },
                "stream": stream,
            }

            # Support JSON format mode
            if request_body.get("format") == "json":
                payload["format"] = "json"

            if stream:
                async def stream_response():
                    async with httpx.AsyncClient() as client:
                        async with client.stream(
                            "POST",
                            "http://localhost:11434/api/generate",
                            json=payload,
                            timeout=300,  # 5 min for large generations
                        ) as response:
                            async for line in response.aiter_lines():
                                if line:
                                    yield line + "\n"

                return StreamingResponse(
                    stream_response(),
                    media_type="application/x-ndjson",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    },
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:11434/api/generate",
                        json=payload,
                        timeout=300,  # 5 min for large generations
                    )
                return response.json()

        @api.get("/health")
        async def health():
            """Health check endpoint."""
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        "http://localhost:11434/api/tags",
                        timeout=5,
                    )
                    models = response.json().get("models", [])
                    return {
                        "status": "healthy",
                        "service": "ollama-llm",
                        "model": MODEL_NAME,
                        "models_loaded": [m["name"] for m in models],
                    }
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)}

        @api.get("/models")
        async def list_models():
            """List available models."""
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:11434/api/tags",
                    timeout=5,
                )
            return response.json()

        @api.get("/")
        async def root():
            return {
                "service": "Ollama LLM",
                "model": MODEL_NAME,
                "endpoints": ["/v1/chat/completions", "/generate", "/models", "/health"],
                "auth": "Required - X-API-Key header",
            }

        return api


@app.local_entrypoint()
def test():
    """Test the Ollama LLM service."""
    import httpx

    print("Testing Ollama LLM on Modal...")

    # Get the web URL from the deployed app
    # For local testing, we'd need to call the class methods differently
    print("Deploy the app and test with:")
    print('  curl -X POST "https://YOUR_URL/generate" -H "Content-Type: application/json" -H "X-API-Key: YOUR_KEY" -d \'{"prompt": "What is 2+2?"}\'')
