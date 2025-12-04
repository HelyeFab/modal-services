# Ollama LLM Service on Modal

A serverless LLM API running Llama 3.2 (3B) via Ollama on Modal. Features OpenAI-compatible endpoints and persistent model caching.

## Features

- **Llama 3.2 3B Instruct** - Lightweight model ideal for text processing tasks
- **OpenAI-compatible API** - Drop-in replacement using `/v1/chat/completions`
- **Streaming support** - Real-time token streaming via SSE for both endpoints
- **Persistent model caching** - Model stored in Modal Volume, fast cold starts after first run
- **Auto-scaling** - Scales to zero when idle, scales up on demand
- **GPU-accelerated** - Runs on NVIDIA T4 GPU

## Deployment

### Prerequisites

1. Modal account and CLI installed:
   ```bash
   pip install modal
   modal setup
   ```

### Deploy

```bash
# From the modal-services directory
py -3.12 "C:/Users/esfab/WinDevProjects/modal-services/ollama-llm/run_deploy.py"
```

Or directly (may have encoding issues on Windows):
```bash
py -3.12 -m modal deploy ollama-llm/deploy_ollama.py
```

### Endpoint URL

After deployment, your endpoint will be:
```
https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI-compatible chat API (supports streaming) |
| `/generate` | POST | Simple prompt-to-response (supports streaming) |
| `/health` | GET | Health check & model status |
| `/models` | GET | List loaded models |

---

## Usage Examples

### Health Check

**PowerShell:**
```powershell
Invoke-RestMethod -Uri "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/health"
```

**curl:**
```bash
curl https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "ollama-llm",
  "model": "llama3.2:3b",
  "models_loaded": ["llama3.2:3b"]
}
```

---

### Simple Generation (`/generate`)

Best for quick, single-turn prompts.

**PowerShell:**
```powershell
$body = @{
    prompt = "Summarize the benefits of exercise in 2 sentences."
    max_tokens = 100
    temperature = 0.7
} | ConvertTo-Json

Invoke-RestMethod -Uri "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/generate" -Method POST -ContentType "application/json" -Body $body
```

**PowerShell (one-liner):**
```powershell
Invoke-RestMethod -Uri "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/generate" -Method POST -ContentType "application/json" -Body '{"prompt": "What is 2+2?"}'
```

**curl:**
```bash
curl -X POST "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain quantum computing simply.", "max_tokens": 200}'
```

**Request body:**
```json
{
  "prompt": "Your prompt here",
  "max_tokens": 512,
  "temperature": 0.7,
  "model": "llama3.2:3b"
}
```

**Response:**
```json
{
  "model": "llama3.2:3b",
  "response": "The model's response text...",
  "done": true,
  "total_duration": 1234567890
}
```

#### Streaming Mode

Add `"stream": true` to receive tokens as they're generated (NDJSON format).

**curl:**
```bash
curl -X POST "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/generate" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Count from 1 to 5.", "stream": true}'
```

**Streamed response (NDJSON):**
```json
{"model":"llama3.2:3b","response":"1","done":false}
{"model":"llama3.2:3b","response":"\n","done":false}
{"model":"llama3.2:3b","response":"2","done":false}
...
{"model":"llama3.2:3b","response":"","done":true,"done_reason":"stop"}
```

---

### Chat Completions (`/v1/chat/completions`)

OpenAI-compatible endpoint for multi-turn conversations.

**PowerShell:**
```powershell
$body = @{
    messages = @(
        @{ role = "system"; content = "You are a helpful assistant." }
        @{ role = "user"; content = "What's the capital of France?" }
    )
    max_tokens = 100
} | ConvertTo-Json -Depth 3

$response = Invoke-RestMethod -Uri "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/v1/chat/completions" -Method POST -ContentType "application/json" -Body $body

# Get the response content
$response.choices[0].message.content
```

**PowerShell (one-liner):**
```powershell
(Invoke-RestMethod -Uri "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/v1/chat/completions" -Method POST -ContentType "application/json" -Body '{"messages": [{"role": "user", "content": "Hello!"}]}').choices[0].message.content
```

**curl:**
```bash
curl -X POST "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain recursion."}
    ],
    "max_tokens": 200
  }'
```

**Request body:**
```json
{
  "model": "llama3.2:3b",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 512
}
```

**Response:**
```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "model": "llama3.2:3b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 27,
    "completion_tokens": 10,
    "total_tokens": 37
  }
}
```

#### Streaming Mode

Add `"stream": true` to receive tokens via Server-Sent Events (SSE).

**curl:**
```bash
curl -X POST "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Count to 3."}], "stream": true}'
```

**Streamed response (SSE):**
```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","model":"llama3.2:3b","choices":[{"index":0,"delta":{"role":"assistant","content":"1"},"finish_reason":null}]}
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","model":"llama3.2:3b","choices":[{"index":0,"delta":{"content":", "},"finish_reason":null}]}
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","model":"llama3.2:3b","choices":[{"index":0,"delta":{"content":"2"},"finish_reason":null}]}
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","model":"llama3.2:3b","choices":[{"index":0,"delta":{"content":", "},"finish_reason":null}]}
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","model":"llama3.2:3b","choices":[{"index":0,"delta":{"content":"3"},"finish_reason":null}]}
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","model":"llama3.2:3b","choices":[{"index":0,"delta":{"content":""},"finish_reason":"stop"}]}
data: [DONE]
```

---

## Python Usage

### Using the OpenAI Library

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run",
    api_key="unused"  # Ollama doesn't require an API key
)

# Chat completion (non-streaming)
response = client.chat.completions.create(
    model="llama3.2:3b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a haiku about programming."}
    ],
    max_tokens=100,
    temperature=0.7
)

print(response.choices[0].message.content)
```

### Streaming with OpenAI Library

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run",
    api_key="unused"
)

# Streaming chat completion
stream = client.chat.completions.create(
    model="llama3.2:3b",
    messages=[{"role": "user", "content": "Explain Python in 3 sentences."}],
    stream=True
)

for chunk in stream:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
print()  # Newline at end
```

### Using httpx/requests

```python
import httpx

BASE_URL = "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run"

# Simple generation
response = httpx.post(
    f"{BASE_URL}/generate",
    json={
        "prompt": "Translate 'Hello, how are you?' to Japanese.",
        "max_tokens": 100
    },
    timeout=60
)
print(response.json()["response"])

# Chat completion
response = httpx.post(
    f"{BASE_URL}/v1/chat/completions",
    json={
        "messages": [
            {"role": "user", "content": "What is machine learning?"}
        ],
        "max_tokens": 200
    },
    timeout=60
)
print(response.json()["choices"][0]["message"]["content"])
```

### Async Python

```python
import asyncio
import httpx

async def chat(prompt: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/v1/chat/completions",
            json={"messages": [{"role": "user", "content": prompt}]},
            timeout=60
        )
        return response.json()["choices"][0]["message"]["content"]

# Usage
result = asyncio.run(chat("Explain photosynthesis briefly."))
print(result)
```

### Async Streaming with httpx

```python
import asyncio
import httpx

async def stream_chat(prompt: str):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": prompt}],
                "stream": True
            },
            timeout=60
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    import json
                    chunk = json.loads(line[6:])
                    content = chunk["choices"][0]["delta"].get("content", "")
                    print(content, end="", flush=True)
    print()

# Usage
asyncio.run(stream_chat("Write a short poem about coding."))
```

---

## Configuration

### Changing the Model

Edit `deploy_ollama.py` and change the `MODEL_NAME` variable:

```python
MODEL_NAME = "llama3.2:3b"  # Default

# Other options:
# MODEL_NAME = "llama3.2:1b"    # Smaller, faster
# MODEL_NAME = "mistral:7b"     # Larger, more capable
# MODEL_NAME = "phi3:mini"      # Microsoft's small model
# MODEL_NAME = "gemma2:2b"      # Google's small model
```

After changing, redeploy:
```bash
py -3.12 "C:/Users/esfab/WinDevProjects/modal-services/ollama-llm/run_deploy.py"
```

### GPU Options

In `deploy_ollama.py`, modify the `@app.cls` decorator:

```python
@app.cls(
    gpu="T4",           # Default: $0.000164/sec - good for 1B-7B models
    # gpu="L4",         # $0.000286/sec - faster, good for 7B-13B models
    # gpu="A10G",       # $0.000384/sec - good for 13B+ models
    # gpu="A100",       # $0.001036/sec - largest models
    timeout=600,
    min_containers=0,   # Scale to zero when idle
    scaledown_window=300,  # Keep warm for 5 min after last request
)
```

### Keep Warm (Avoid Cold Starts)

To keep a container always running (costs money but instant responses):

```python
min_containers=1,  # Always keep 1 container running
```

---

## How Model Caching Works

1. **First deployment/cold start:**
   - Container starts
   - Ollama server starts
   - Model is pulled from Ollama registry (~2GB for 3B model)
   - Model saved to Modal Volume
   - Takes 1-2 minutes

2. **Subsequent cold starts:**
   - Container starts
   - Ollama server starts
   - Model loaded from Volume (already cached)
   - Takes 10-20 seconds

3. **Warm requests:**
   - Container already running
   - Instant response (< 1 second for first token)

The Volume `ollama-models` persists at `/root/.ollama` across container restarts.

---

## Costs

Modal pricing (as of Dec 2024):

| Resource | Cost |
|----------|------|
| T4 GPU | $0.000164/sec (~$0.59/hr) |
| CPU | $0.000018/sec per core |
| Memory | $0.000002/sec per GB |

With `min_containers=0` and `scaledown_window=300`:
- **Idle:** $0 (no running containers)
- **Active:** ~$0.60/hr while processing requests
- **Cold start:** ~$0.02 per cold start (1-2 min GPU time)

---

## Troubleshooting

### Windows Encoding Errors

If you see `'charmap' codec can't encode characters` when deploying:
```bash
# Use the helper script
py -3.12 "C:/Users/esfab/WinDevProjects/modal-services/ollama-llm/run_deploy.py"
```

### Timeout on First Request

The first request after a cold start may take 1-2 minutes while the model loads. This is normal. Subsequent requests will be fast.

### Check Container Logs

```bash
py -3.12 -m modal app logs ollama-llm
```

### Check if Model is Loaded

```powershell
Invoke-RestMethod -Uri "https://emmanuelfabiani23--ollama-llm-ollamallm-serve.modal.run/models"
```

---

## Files

```
ollama-llm/
├── deploy_ollama.py   # Main Modal deployment file
├── run_deploy.py      # Windows-friendly deploy helper
└── README.md          # This file
```

---

## Use Cases

- **Text summarization** - Condense articles, documents, emails
- **Translation** - Quick translations between languages
- **Code explanation** - Explain code snippets
- **Content generation** - Draft emails, messages, simple content
- **Data extraction** - Parse and extract info from text
- **Q&A** - Answer questions about provided context

---

## Limitations

- **Model size:** 3B parameters - good for simple tasks, may struggle with complex reasoning
- **Context window:** 8K tokens max
- **Cold starts:** First request takes 1-2 min if container is cold
