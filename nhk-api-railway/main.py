"""
NHK Easy API Auth Proxy for Railway
Adds API key authentication to the NHK Easy API
"""

import os
import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

app = FastAPI(
    title="NHK Easy API",
    description="Protected NHK Easy News API",
    version="1.0.0"
)

# Configuration
API_KEY = os.environ.get("NHK_API_KEY")
UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "http://nhk-easy-api.railway.internal:8080")

# API Key security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Depends(api_key_header)):
    """Verify the API key for protected endpoints."""
    if not API_KEY:
        # No API key configured - allow requests (for testing)
        return True
    if not api_key or api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )
    return True


@app.get("/health")
async def health():
    """Health check - no auth required."""
    return {
        "status": "UP",
        "service": "nhk-easy-api-proxy",
        "auth": "enabled" if API_KEY else "disabled"
    }


@app.get("/news")
async def get_news(
    request: Request,
    startDate: str = None,
    endDate: str = None,
    _: bool = Depends(verify_api_key)
):
    """
    Get NHK Easy news articles.
    Requires X-API-Key header.

    Query params:
    - startDate: ISO datetime (e.g., 2025-12-01T00:00:00.000Z)
    - endDate: ISO datetime (e.g., 2025-12-03T23:59:59.000Z)
    """
    # Build upstream URL with query params
    params = {}
    if startDate:
        params["startDate"] = startDate
    if endDate:
        params["endDate"] = endDate

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{UPSTREAM_URL}/news", params=params)

            return JSONResponse(
                content=response.json(),
                status_code=response.status_code
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {str(e)}")


@app.get("/")
async def root():
    """API info."""
    return {
        "service": "NHK Easy API",
        "version": "1.0.0",
        "endpoints": {
            "news": "GET /news?startDate=...&endDate=...",
            "health": "GET /health"
        },
        "auth": "Required - X-API-Key header"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
