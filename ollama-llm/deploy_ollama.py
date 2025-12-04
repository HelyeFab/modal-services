"""
Ollama LLM Service on Modal
- Llama 3.2 3B for light text processing
- Model cached in Volume (no download on cold start)
- OpenAI-compatible /v1/chat/completions endpoint
"""

import modal
import subprocess
import time

app = modal.App("ollama-llm")

# Volume to cache ollama models - persists across cold starts
ollama_volume = modal.Volume.from_name("ollama-models", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("curl")
    .run_commands(
        "curl -fsSL https://ollama.com/install.sh | sh",
    )
    .pip_install("fastapi[standard]", "httpx")
)

MODEL_NAME = "llama3.2:3b"


def start_ollama_server():
    """Start ollama server and wait for it to be ready."""
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for server to be ready
    for _ in range(30):
        try:
            import httpx
            httpx.get("http://localhost:11434/api/tags", timeout=1)
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
    gpu="T4",
    timeout=600,
    min_containers=0,
    scaledown_window=300,
    volumes={"/root/.ollama": ollama_volume},
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
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse
        import httpx

        api = FastAPI(title="Ollama LLM")

        @api.post("/v1/chat/completions")
        async def chat_completions(request_body: dict):
            """
            OpenAI-compatible chat completions endpoint with streaming support.

            Usage with openai library:
                from openai import OpenAI
                client = OpenAI(base_url="https://YOUR_MODAL_URL", api_key="unused")

                # Non-streaming
                response = client.chat.completions.create(
                    model="llama3.2:3b",
                    messages=[{"role": "user", "content": "Hello!"}]
                )

                # Streaming
                for chunk in client.chat.completions.create(
                    model="llama3.2:3b",
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
                "max_tokens": request_body.get("max_tokens", 512),
                "stream": stream,
            }

            if stream:
                async def stream_response():
                    async with httpx.AsyncClient() as client:
                        async with client.stream(
                            "POST",
                            "http://localhost:11434/v1/chat/completions",
                            json=payload,
                            timeout=120,
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
                        timeout=120,
                    )
                return response.json()

        @api.post("/generate")
        async def generate(request_body: dict):
            """
            Simple generate endpoint for quick prompts with streaming support.

            POST /generate
            {"prompt": "Summarize: ...", "max_tokens": 256}

            POST /generate (streaming)
            {"prompt": "Summarize: ...", "max_tokens": 256, "stream": true}
            """
            stream = request_body.get("stream", False)

            payload = {
                "model": request_body.get("model", MODEL_NAME),
                "prompt": request_body.get("prompt", ""),
                "options": {
                    "num_predict": request_body.get("max_tokens", 512),
                    "temperature": request_body.get("temperature", 0.7),
                },
                "stream": stream,
            }

            if stream:
                async def stream_response():
                    async with httpx.AsyncClient() as client:
                        async with client.stream(
                            "POST",
                            "http://localhost:11434/api/generate",
                            json=payload,
                            timeout=120,
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
                        timeout=120,
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

        return api


@app.local_entrypoint()
def test():
    """Test the Ollama LLM service."""
    import httpx

    print("Testing Ollama LLM on Modal...")

    # Get the web URL from the deployed app
    # For local testing, we'd need to call the class methods differently
    print("Deploy the app and test with:")
    print('  curl -X POST "https://YOUR_URL/generate" -H "Content-Type: application/json" -d \'{"prompt": "What is 2+2?"}\'')
