"""
NHK Easy News Scraper on Modal
Scrapes NHK Easy news and provides REST API
Replaces the Spring Boot homeserver scraper
"""

import modal

app = modal.App("nhk-easy-scraper")

# Build image with scraping dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi[standard]==0.115.6",
        "beautifulsoup4==4.12.3",
        "requests==2.32.3",
        "python-dateutil==2.9.0",
        "lxml==5.3.0",
    )
)

# NHK Easy scraping logic
def scrape_nhk_easy_articles(start_date, end_date):
    """
    Scrape NHK Easy articles between start_date and end_date
    Returns list of articles with full content
    """
    import requests
    from bs4 import BeautifulSoup
    from datetime import datetime, timedelta
    from dateutil import parser as date_parser

    articles = []
    base_url = "https://www3.nhk.or.jp/news/easy"

    try:
        # Get article list page
        response = requests.get(f"{base_url}/news-list.json", timeout=10)
        response.raise_for_status()
        news_list = response.json()

        # Filter articles by date range
        start = date_parser.parse(start_date) if isinstance(start_date, str) else start_date
        end = date_parser.parse(end_date) if isinstance(end_date, str) else end_date

        for news_data in news_list:
            if not isinstance(news_data, list) or len(news_data) < 2:
                continue

            article_list = news_data[1]
            for article_id, article_meta in article_list.items():
                try:
                    # Parse article date
                    article_date_str = article_meta.get("news_prearranged_time", "")
                    if not article_date_str:
                        continue

                    article_date = datetime.strptime(article_date_str, "%Y-%m-%d %H:%M:%S")

                    # Check if within date range
                    if not (start <= article_date <= end):
                        continue

                    # Fetch full article content
                    article_url = f"{base_url}/{article_id}/{article_id}.html"
                    article_response = requests.get(article_url, timeout=10)
                    article_response.raise_for_status()

                    soup = BeautifulSoup(article_response.text, 'lxml')

                    # Extract article details
                    title_elem = soup.select_one('h1.article-main__title')
                    title = title_elem.get_text(strip=True) if title_elem else article_meta.get("title", "")

                    # Extract content with furigana (ruby tags)
                    content_elem = soup.select_one('div#js-article-body')
                    content_with_ruby = str(content_elem) if content_elem else ""
                    content_text = content_elem.get_text(separator=" ", strip=True) if content_elem else ""

                    # Extract summary
                    summary_elem = soup.select_one('p.summary')
                    summary = summary_elem.get_text(strip=True) if summary_elem else ""
                    summary_with_ruby = str(summary_elem) if summary_elem else ""

                    # Extract image
                    image_elem = soup.select_one('div.article-main__img img')
                    image_url = image_elem.get('src') if image_elem else article_meta.get("news_easy_image_uri", "")

                    if image_url and not image_url.startswith('http'):
                        image_url = f"https://www3.nhk.or.jp{image_url}"

                    article = {
                        "newsId": article_id,
                        "title": title,
                        "titleWithRuby": str(title_elem) if title_elem else title,
                        "body": content_text,
                        "bodyWithRuby": content_with_ruby,
                        "bodyWithoutHtml": content_text,
                        "outline": summary,
                        "outlineWithRuby": summary_with_ruby,
                        "url": article_url,
                        "imageUrl": image_url,
                        "publishedAtUtc": article_date.isoformat() + "Z",
                        "m3u8Url": article_meta.get("news_web_url", ""),
                    }

                    articles.append(article)

                except Exception as e:
                    print(f"Error scraping article {article_id}: {e}")
                    continue

        # Sort by publish date (newest first)
        articles.sort(key=lambda x: x["publishedAtUtc"], reverse=True)

        return articles

    except Exception as e:
        print(f"Error scraping NHK Easy: {e}")
        raise


@app.function(
    image=image,
    cpu=2,
    memory=2048,
    timeout=60,
)
@modal.web_endpoint(method="GET")
def news(startDate: str, endDate: str):
    """
    Get NHK Easy news articles

    GET /news?startDate=2024-12-01T00:00:00.000Z&endDate=2024-12-03T23:59:59.000Z

    Returns: List of news articles with full content
    """
    from fastapi import Response
    import json

    try:
        articles = scrape_nhk_easy_articles(startDate, endDate)

        return Response(
            content=json.dumps(articles, ensure_ascii=False),
            media_type="application/json; charset=utf-8"
        )
    except Exception as e:
        print(f"Error in /news endpoint: {e}")
        import traceback
        traceback.print_exc()

        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json"
        )


@app.function(image=image, cpu=0.25, memory=256)
@modal.web_endpoint(method="GET")
def health():
    """
    Health check endpoint
    GET /health
    """
    return {
        "status": "UP",
        "service": "nhk-easy-scraper",
        "version": "1.0",
        "components": {
            "scraper": {"status": "UP"},
        }
    }


# Local testing
@app.local_entrypoint()
def test():
    """
    Test NHK scraper locally
    Run: modal run deploy_nhk.py
    """
    from datetime import datetime, timedelta

    print("🧪 Testing NHK Easy Scraper on Modal...")

    # Test last 3 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=3)

    print(f"\n📅 Fetching articles from {start_date.isoformat()}Z to {end_date.isoformat()}Z")

    result = news.remote(
        startDate=start_date.isoformat() + "Z",
        endDate=end_date.isoformat() + "Z"
    )

    print(f"\n✅ Response received")
    print(f"Response type: {type(result)}")
    if hasattr(result, 'body'):
        print(f"Response size: {len(result.body)} bytes")
        # Parse and show first article
        import json
        articles = json.loads(result.body)
        print(f"\n📰 Found {len(articles)} articles")
        if articles:
            first = articles[0]
            print(f"\nFirst article:")
            print(f"  Title: {first.get('title', '')[:50]}...")
            print(f"  Published: {first.get('publishedAtUtc', '')}")
            print(f"  URL: {first.get('url', '')}")
