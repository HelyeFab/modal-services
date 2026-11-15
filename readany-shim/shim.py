"""
ReadAny -> OpenAI shim.

ReadAny (v1.3.6) sends `max_tokens` and `temperature` on every chat request.
The gpt-5 family rejects both: it wants `max_completion_tokens`, and the
reasoning variants only accept temperature 1. This shim sits between the app
and api.openai.com and repairs the request body.

It never stores a key: the caller's Authorization header is forwarded as-is.
"""

import json
import re

import modal

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]==0.115.6", "httpx==0.28.1"
)

app = modal.App("readany-shim", image=image)

# Last few requests, so a failure can be READ instead of guessed at.
# Never holds the Authorization header or any key material.
trace = modal.Dict.from_name("readany-shim-trace", create_if_missing=True)

UPSTREAM = "https://api.openai.com"

# Params the reasoning models refuse outright.
REASONING_DROP = ("top_p", "frequency_penalty", "presence_penalty", "logprobs", "top_logprobs")


def is_gpt5_family(model: str) -> bool:
    return bool(model) and (model.startswith("gpt-5") or re.match(r"^o\d", model))


def is_reasoning(model: str) -> bool:
    """gpt-5-chat* is the non-reasoning variant; it still wants max_completion_tokens."""
    return is_gpt5_family(model) and not model.startswith("gpt-5-chat")


def repair(body: dict) -> dict:
    model = str(body.get("model") or "")
    if not is_gpt5_family(model):
        return body

    if "max_tokens" in body:
        body["max_completion_tokens"] = body.pop("max_tokens")

    if is_reasoning(model):
        if body.get("temperature") != 1:
            body.pop("temperature", None)
        for key in REASONING_DROP:
            body.pop(key, None)

    return body


def strip_param_from_error(body: dict, error_text: str) -> tuple[dict, str | None]:
    """OpenAI names the offending field in the 400. Drop it and let the caller retry."""
    try:
        param = json.loads(error_text)["error"].get("param")
    except Exception:
        param = None
    if not param:
        match = re.search(r"[Uu]nsupported parameter: '([^']+)'", error_text)
        param = match.group(1) if match else None
    if param and param in body:
        body.pop(param)
        return body, param
    return body, None


@app.function(min_containers=0, timeout=900)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def serve():
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse

    web = FastAPI()

    def record(entry: dict) -> None:
        try:
            recent = trace.get("recent", [])
            trace["recent"] = ([*recent, entry])[-20:]
        except Exception:
            pass

    @web.get("/health")
    async def health():
        return {"ok": True, "upstream": UPSTREAM}

    @web.get("/trace")
    async def read_trace():
        return {"recent": trace.get("recent", [])}

    @web.delete("/trace")
    async def clear_trace():
        trace["recent"] = []
        return {"cleared": True}

    @web.api_route("/{path:path}", methods=["GET", "POST", "DELETE"])
    async def proxy(path: str, request: Request):
        clean = path.lstrip("/")
        if clean.startswith("v1/"):
            clean = clean[3:]
        url = f"{UPSTREAM}/v1/{clean}"

        headers = {}
        for name in ("authorization", "content-type", "openai-organization", "openai-project"):
            value = request.headers.get(name)
            if value:
                headers[name] = value

        raw = await request.body()

        if request.method != "POST" or not raw:
            async with httpx.AsyncClient(timeout=120) as client:
                upstream = await client.request(
                    request.method, url, headers=headers, content=raw or None
                )
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type"),
            )

        try:
            body = json.loads(raw)
        except Exception:
            body = None

        if not isinstance(body, dict):
            async with httpx.AsyncClient(timeout=300) as client:
                upstream = await client.post(url, headers=headers, content=raw)
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type"),
            )

        body = repair(body)
        streaming = bool(body.get("stream"))

        if streaming:
            async def relay():
                attempt = dict(body)
                async with httpx.AsyncClient(timeout=None) as client:
                    for _ in range(3):
                        async with client.stream(
                            "POST", url, headers=headers, json=attempt
                        ) as upstream:
                            if upstream.status_code == 400:
                                text = (await upstream.aread()).decode()
                                attempt, dropped = strip_param_from_error(attempt, text)
                                record({
                                    "path": clean,
                                    "model": attempt.get("model"),
                                    "status": 400,
                                    "stream": True,
                                    "dropped": dropped,
                                    "error": text[:400],
                                })
                                if dropped:
                                    continue
                                yield f"data: {text}\n\n".encode()
                                return
                            async for chunk in upstream.aiter_raw():
                                yield chunk
                            return

            return StreamingResponse(relay(), media_type="text/event-stream")

        attempt = dict(body)
        async with httpx.AsyncClient(timeout=300) as client:
            for _ in range(3):
                upstream = await client.post(url, headers=headers, json=attempt)
                if upstream.status_code == 400:
                    attempt, dropped = strip_param_from_error(attempt, upstream.text)
                    record({
                        "path": clean,
                        "model": attempt.get("model"),
                        "status": 400,
                        "dropped": dropped,
                        "error": upstream.text[:400],
                    })
                    if dropped:
                        continue
                record({
                    "path": clean,
                    "model": attempt.get("model"),
                    "status": upstream.status_code,
                    "sent": sorted(attempt.keys()),
                    "error": "" if upstream.status_code < 400 else upstream.text[:400],
                })
                return Response(
                    content=upstream.content,
                    status_code=upstream.status_code,
                    media_type=upstream.headers.get("content-type"),
                )

        return JSONResponse({"error": {"message": "shim: retries exhausted"}}, status_code=400)

    return web
