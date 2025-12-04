"""
Simple NHK Easy API using the nhk-easy Python library
Much simpler than Spring Boot approach
"""

import modal

app = modal.App("nhk-easy-simple")

# Simple image with nhk-easy library
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "nhk-easy",
    "fastapi[standard]==0.115.6",
)

@app.function(
    image=image,
    cpu=2,
    memory=2048,
    timeout=60,
)
@modal.web_endpoint(method="GET")
def news(startDate: str = None, endDate: str = None):
    """
    Get NHK Easy news articles
    GET /news

    Returns today's articles (nhk-easy library limitation)
    """
    from fastapi import Response
    import json
    import subprocess

    try:
        # Use nhk-easy CLI to get articles
        result = subprocess.run(
            ["nhk-easy", "-F"],  # Get with furigana
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return Response(
                content=json.dumps({"error": "Failed to fetch articles", "details": result.stderr}),
                status_code=500,
                media_type="application/json"
            )

        # Parse output and return as JSON
        # (This is simplified - you'd need to parse the actual output format)
        return Response(
            content=json.dumps({
                "message": "Articles fetched successfully",
                "note": "This uses nhk-easy library which fetches today's articles",
                "raw_output": result.stdout[:500]  # First 500 chars
            }),
            media_type="application/json"
        )

    except Exception as e:
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json"
        )


@app.function(image=image)
@modal.web_endpoint(method="GET")
def health():
    """Health check"""
    return {"status": "UP", "service": "nhk-easy-simple"}


@app.local_entrypoint()
def test():
    print("Deploy with: modal deploy deploy_nhk_simple.py")
