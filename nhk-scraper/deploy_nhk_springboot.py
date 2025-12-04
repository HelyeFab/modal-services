"""
NHK Easy API - Spring Boot Deployment on Modal
Deploys the official nhk-easy-api Docker image with MySQL support
"""

import modal
from datetime import datetime

app = modal.App("nhk-easy-api")

# Use the official Docker image
image = (
    modal.Image.from_registry(
        "xiaodanmao/nhk-easy-api:latest",
    )
    .apt_install("curl")  # For health checks
    .pip_install("requests")  # For HTTP forwarding
)

# Scraper image
scraper_image = modal.Image.from_registry(
    "xiaodanmao/nhk-easy-task:latest"
)


# NHK Easy API Web Endpoint
@app.function(
    image=image,
    secrets=[modal.Secret.from_name("nhk-database")],
    cpu=2,
    memory=4096,
    keep_warm=1,
    timeout=120,
    container_idle_timeout=300,
)
@modal.asgi_app()
def api():
    """
    NHK Easy REST API
    Endpoints:
    - GET /news?startDate=...&endDate=...
    - GET /actuator/health
    """
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse
    import subprocess
    import requests
    import os
    import time
    import threading

    app = FastAPI()

    # Start Spring Boot in background
    spring_boot_process = None
    spring_boot_ready = False

    def start_spring_boot():
        nonlocal spring_boot_process, spring_boot_ready
        try:
            print("🚀 Starting Spring Boot application...")
            # Spring Boot expects these env vars
            env = os.environ.copy()

            # Start Spring Boot (it should be in /app or similar)
            # The Docker image has ENTRYPOINT configured
            spring_boot_process = subprocess.Popen(
                ["java", "-jar", "/app/nhk-easy-api.jar"],  # Adjust path if needed
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait for Spring Boot to be ready
            max_wait = 60  # seconds
            start_time = time.time()
            while time.time() - start_time < max_wait:
                try:
                    response = requests.get("http://localhost:8080/actuator/health", timeout=1)
                    if response.status_code == 200:
                        spring_boot_ready = True
                        print("✅ Spring Boot is ready!")
                        return
                except:
                    pass
                time.sleep(1)

            print("⚠️ Spring Boot did not become ready in time")
        except Exception as e:
            print(f"❌ Failed to start Spring Boot: {e}")

    # Start Spring Boot in background thread
    boot_thread = threading.Thread(target=start_spring_boot, daemon=True)
    boot_thread.start()

    @app.get("/news")
    async def get_news(request: Request):
        """Get NHK Easy news articles"""
        if not spring_boot_ready:
            return JSONResponse(
                content={"error": "Spring Boot is still starting up, please wait..."},
                status_code=503
            )

        try:
            # Forward request to Spring Boot
            query_params = dict(request.query_params)
            response = requests.get(
                "http://localhost:8080/news",
                params=query_params,
                timeout=30
            )

            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type="application/json"
            )
        except Exception as e:
            return JSONResponse(
                content={"error": f"Failed to fetch news: {str(e)}"},
                status_code=500
            )

    @app.get("/actuator/health")
    async def health():
        """Health check endpoint"""
        if not spring_boot_ready:
            return JSONResponse(
                content={"status": "STARTING"},
                status_code=503
            )

        try:
            response = requests.get("http://localhost:8080/actuator/health", timeout=5)
            return Response(
                content=response.content,
                status_code=response.status_code,
                media_type="application/json"
            )
        except Exception as e:
            return JSONResponse(
                content={"status": "DOWN", "error": str(e)},
                status_code=500
            )

    @app.get("/")
    async def root():
        """API information"""
        return {
            "service": "NHK Easy API",
            "version": "1.0",
            "endpoints": {
                "news": "/news?startDate=YYYY-MM-DDTHH:mm:ss.sssZ&endDate=YYYY-MM-DDTHH:mm:ss.sssZ",
                "health": "/actuator/health"
            }
        }

    return app


# Scheduled scraper task
@app.function(
    image=scraper_image,
    secrets=[modal.Secret.from_name("nhk-database")],
    schedule=modal.Cron("0 */2 * * *"),  # Every 2 hours
    cpu=2,
    memory=2048,
    timeout=600,
)
def scraper():
    """
    Scheduled task to scrape NHK Easy articles
    Runs every 2 hours
    """
    import subprocess
    import os

    print(f"🚀 Starting NHK Easy scraper at {datetime.utcnow().isoformat()}")

    try:
        # Run the scraper task
        # The Docker image should have the scraper as entrypoint
        result = subprocess.run(
            ["java", "-jar", "/app/nhk-easy-task.jar"],  # Adjust path if needed
            capture_output=True,
            text=True,
            timeout=540,
            env=os.environ
        )

        print(f"✅ Scraper completed with exit code {result.returncode}")
        if result.stdout:
            print(f"Output: {result.stdout[:500]}")  # First 500 chars
        if result.stderr:
            print(f"Errors: {result.stderr[:500]}")

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "timestamp": datetime.utcnow().isoformat()
        }

    except subprocess.TimeoutExpired:
        print("⚠️ Scraper timed out after 9 minutes")
        return {
            "success": False,
            "error": "Timeout",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"❌ Scraper failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# Manual scraper trigger
@app.function(
    image=scraper_image,
    secrets=[modal.Secret.from_name("nhk-database")],
    cpu=2,
    memory=2048,
    timeout=600,
)
def manual_scrape():
    """
    Manually trigger the scraper
    Usage: modal run deploy_nhk_springboot.py::manual_scrape
    """
    return scraper.local()


@app.local_entrypoint()
def test():
    """Test deployment"""
    print("📋 NHK Easy API Deployment")
    print("\n1. First, create database secret:")
    print("   modal secret create nhk-database \\")
    print("     MYSQL_HOST=your-host \\")
    print("     MYSQL_USER=your-user \\")
    print("     MYSQL_PASSWORD=your-password \\")
    print("     MYSQL_DATABASE=nhk")
    print("\n2. Then deploy:")
    print("   modal deploy deploy_nhk_springboot.py")
    print("\n3. Manual scrape test:")
    print("   modal run deploy_nhk_springboot.py::manual_scrape")
