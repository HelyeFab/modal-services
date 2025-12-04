"""
NHK Easy Full Stack Deployment on Modal
Deploys both nhk-easy-api (REST API) and nhk-easy-task (scraper)
Uses external MySQL database (PlanetScale recommended)
"""

import modal

app = modal.App("nhk-easy-fullstack")

# Docker images from the official repos
nhk_api_image = modal.Image.from_registry(
    "xiaodanmao/nhk-easy-api:latest",
    add_python="3.11",
)

nhk_task_image = modal.Image.from_registry(
    "xiaodanmao/nhk-easy-task:latest",
    add_python="3.11",
)

# Database configuration
# You need to create a Modal secret with these values:
# modal secret create nhk-database \
#   MYSQL_HOST=your-db-host \
#   MYSQL_USER=your-db-user \
#   MYSQL_PASSWORD=your-db-password \
#   MYSQL_DATABASE=nhk

@app.function(
    image=nhk_api_image,
    secrets=[modal.Secret.from_name("nhk-database")],
    cpu=2,
    memory=2048,
    keep_warm=1,  # Keep 1 instance warm for faster response
)
@modal.web_endpoint(method="GET", label="nhk-api")
async def api():
    """
    NHK Easy API endpoint - forwards requests to the Spring Boot app

    GET /news?startDate=2024-12-01T00:00:00.000Z&endDate=2024-12-03T23:59:59.000Z
    GET /actuator/health
    """
    import subprocess
    import os
    from fastapi import Request, Response
    from fastapi.responses import JSONResponse

    # Get request context
    request = Request

    # Start Spring Boot application if not running
    # The Docker image should start automatically, but we ensure it's running
    try:
        # The Spring Boot app runs on port 8080 inside the container
        # Forward the request to it
        import requests as req

        # Build the URL
        query_string = request.query_params if hasattr(request, 'query_params') else ""
        url = f"http://localhost:8080{request.url.path}?{query_string}"

        # Forward the request
        response = req.get(url, timeout=30)

        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get('content-type', 'application/json')
        )
    except Exception as e:
        return JSONResponse(
            content={"error": f"Failed to reach Spring Boot app: {str(e)}"},
            status_code=500
        )


# Scheduled scraper task
@app.function(
    image=nhk_task_image,
    secrets=[modal.Secret.from_name("nhk-database")],
    schedule=modal.Cron("0 * * * *"),  # Run hourly
    cpu=2,
    memory=2048,
    timeout=600,  # 10 minutes timeout
)
def scraper_task():
    """
    Scheduled task to scrape NHK Easy news articles
    Runs every hour
    """
    import subprocess
    import os

    print("🚀 Starting NHK Easy scraper task...")
    print(f"⏰ Current time: {datetime.utcnow().isoformat()}")

    # The Docker image should run the scraper automatically
    # Just need to ensure database connection is available
    try:
        # Run the scraper (the Docker entrypoint should handle this)
        result = subprocess.run(
            ["java", "-jar", "/app.jar"],
            capture_output=True,
            text=True,
            timeout=540  # 9 minutes
        )

        print(f"✅ Scraper completed")
        print(f"stdout: {result.stdout}")
        if result.stderr:
            print(f"stderr: {result.stderr}")

        return {
            "success": True,
            "returncode": result.returncode,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"❌ Scraper failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# Manual scraper trigger for testing
@app.function(
    image=nhk_task_image,
    secrets=[modal.Secret.from_name("nhk-database")],
    cpu=2,
    memory=2048,
    timeout=600,
)
def manual_scrape():
    """
    Manually trigger the scraper (for testing)
    Usage: modal run deploy_nhk_fullstack.py::manual_scrape
    """
    return scraper_task.local()


@app.local_entrypoint()
def main():
    """
    Test the deployment
    """
    print("🧪 Testing NHK Easy Full Stack deployment...")
    print("\nTo deploy, run:")
    print("  modal deploy deploy_nhk_fullstack.py")
    print("\nMake sure you've created the database secret first:")
    print("  modal secret create nhk-database \\")
    print("    MYSQL_HOST=your-host \\")
    print("    MYSQL_USER=your-user \\")
    print("    MYSQL_PASSWORD=your-password \\")
    print("    MYSQL_DATABASE=nhk")
