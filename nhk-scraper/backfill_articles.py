#!/usr/bin/env python3
"""
NHK Easy News Backfill Script

Fetches older articles from NHK Easy's news-list.json endpoint and inserts
them into the Railway MySQL database.

Usage:
    python backfill_articles.py --start-date 2025-11-01 --end-date 2025-11-26
    python backfill_articles.py --days 30  # Last 30 days
"""

import argparse
import io
import re
import sys
from datetime import datetime, timedelta

# Fix Windows console encoding for Japanese characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pymysql
import requests
from bs4 import BeautifulSoup

# Railway MySQL connection
DB_CONFIG = {
    'host': 'shortline.proxy.rlwy.net',
    'port': 46705,
    'user': 'root',
    'password': 'MKCixlltjXujzRRSdwqtVQqLfLOHFOMk',
    'database': 'railway',
    'charset': 'utf8mb4'
}

# NHK URLs
NHK_AUTH_URL = "https://news.web.nhk/tix/build_authorize"
NHK_NEWS_LIST_URL = "https://news.web.nhk/news/easy/news-list.json"
NHK_ARTICLE_URL_TEMPLATE = "https://news.web.nhk/news/easy/{news_id}/{news_id}.html"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:143.0) Gecko/20100101 Firefox/143.0"


class NHKAuthenticatedSession:
    """Handles NHK OAuth authentication via cookie-based flow."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        self._authenticated = False

    def authenticate(self):
        """Perform OAuth flow to get session cookies."""
        if self._authenticated:
            return

        auth_params = {
            'idp': 'a-alaz',
            'profileType': 'abroad',
            'redirect_uri': 'https://news.web.nhk/news/easy/',
            'entity': 'none',
            'area': '130',
            'pref': '13',
            'jisx0402': '13101',
            'postal': '1000001'
        }

        print("[AUTH] Authenticating with NHK...")
        self.session.headers['Referer'] = 'https://news.web.nhk/news/easy/'
        response = self.session.get(NHK_AUTH_URL, params=auth_params, allow_redirects=True)

        if response.status_code == 200:
            self._authenticated = True
            print("[AUTH] Authentication successful")
        else:
            raise Exception(f"Authentication failed with status {response.status_code}")

    def get(self, url, **kwargs):
        """Make authenticated GET request."""
        self.authenticate()
        return self.session.get(url, **kwargs)


def fetch_news_list(session: NHKAuthenticatedSession) -> dict:
    """Fetch the news-list.json which contains articles organized by date."""
    print("[FETCH] Fetching news-list.json...")
    response = session.get(NHK_NEWS_LIST_URL)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch news list: {response.status_code}")

    data = response.json()

    # news-list.json returns an array with one element containing date-keyed articles
    if isinstance(data, list) and len(data) > 0:
        return data[0]

    return data


def parse_article_html(session: NHKAuthenticatedSession, news_id: str, article_data: dict) -> dict:
    """Fetch and parse a single article's HTML content."""
    url = NHK_ARTICLE_URL_TEMPLATE.format(news_id=news_id)

    response = session.get(url)
    if response.status_code != 200:
        print(f"  [WARN] Failed to fetch article {news_id}: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    body_element = soup.find(id='js-article-body')

    if not body_element:
        print(f"  [WARN] No body found for article {news_id}")
        return None

    # Remove href from links
    for link in body_element.find_all('a'):
        if 'href' in link.attrs:
            del link['href']

    body_html = str(body_element)

    # Extract text without ruby annotations
    body_text = extract_text_without_ruby(body_element)

    # Parse outline without ruby
    outline_with_ruby = article_data.get('outline_with_ruby', '')
    outline = extract_text_from_html(outline_with_ruby)

    # Parse published time
    news_time = article_data.get('news_prearranged_time', '')
    published_at = parse_nhk_datetime(news_time)

    # Get image URL
    image_url = article_data.get('news_easy_image_uri', '') or article_data.get('news_web_image_uri', '')

    # Build m3u8 URL
    voice_uri = article_data.get('news_easy_voice_uri', '')
    m3u8_url = ''
    if voice_uri:
        base_name = voice_uri.split('.')[0] if '.' in voice_uri else voice_uri
        m3u8_url = f"https://vod-stream.nhk.jp/news/easy_audio/{base_name}/index.m3u8"

    return {
        'news_id': news_id,
        'title': article_data.get('title', ''),
        'title_with_ruby': article_data.get('title_with_ruby', ''),
        'outline': outline,
        'outline_with_ruby': outline_with_ruby,
        'url': url,
        'body': body_html,
        'body_without_html': body_text,
        'image_url': image_url,
        'm3u8_url': m3u8_url,
        'published_at_utc': published_at
    }


def extract_text_without_ruby(element) -> str:
    """Extract text from BeautifulSoup element, removing ruby annotations."""
    # Clone to avoid modifying original
    clone = BeautifulSoup(str(element), 'html.parser')

    # Remove all rt (ruby text) elements
    for rt in clone.find_all('rt'):
        rt.decompose()

    # Get text from paragraphs
    paragraphs = clone.find_all('p')
    if paragraphs:
        lines = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
        return '\n'.join(lines)

    return clone.get_text(strip=True)


def extract_text_from_html(html: str) -> str:
    """Extract plain text from HTML, removing ruby annotations."""
    if not html:
        return ''

    soup = BeautifulSoup(html, 'html.parser')
    for rt in soup.find_all('rt'):
        rt.decompose()

    return soup.get_text(strip=True)


def parse_nhk_datetime(date_str: str) -> datetime:
    """Parse NHK datetime string (JST) to UTC datetime."""
    if not date_str:
        return None

    # Format: "2025-12-03 19:30:00" (JST)
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        # Convert JST to UTC (subtract 9 hours)
        return dt - timedelta(hours=9)
    except ValueError:
        print(f"  [WARN] Could not parse datetime: {date_str}")
        return None


def article_exists(cursor, news_id: str) -> bool:
    """Check if article already exists in database."""
    cursor.execute("SELECT 1 FROM news WHERE news_id = %s LIMIT 1", (news_id,))
    return cursor.fetchone() is not None


def insert_article(cursor, article: dict):
    """Insert article into database."""
    sql = """
        INSERT INTO news (
            news_id, title, title_with_ruby, outline, outline_with_ruby,
            url, body, body_without_html, image_url, m3u8url, published_at_utc
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """
    cursor.execute(sql, (
        article['news_id'],
        article['title'][:50] if article['title'] else '',  # varchar(50)
        article['title_with_ruby'][:500] if article['title_with_ruby'] else '',  # varchar(500)
        article['outline'][:1000] if article['outline'] else '',  # varchar(1000)
        article['outline_with_ruby'],
        article['url'][:200] if article['url'] else '',
        article['body'],
        article['body_without_html'],
        article['image_url'][:200] if article['image_url'] else '',
        article['m3u8_url'][:200] if article['m3u8_url'] else '',
        article['published_at_utc']
    ))


def main():
    parser = argparse.ArgumentParser(description='Backfill NHK Easy News articles')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, help='Number of days back to fetch')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without inserting')
    args = parser.parse_args()

    # Determine date range
    if args.days:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        print("Error: Specify either --days or both --start-date and --end-date")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"NHK Easy News Backfill")
    print(f"{'='*60}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Dry run: {args.dry_run}")
    print(f"{'='*60}\n")

    # Create authenticated session
    session = NHKAuthenticatedSession()

    # Fetch news list
    news_list = fetch_news_list(session)

    # Get dates in range
    available_dates = sorted(news_list.keys())
    target_dates = [d for d in available_dates if start_date <= d <= end_date]

    print(f"[INFO] Found {len(available_dates)} dates in news-list.json")
    print(f"[INFO] {len(target_dates)} dates match the requested range")

    if not target_dates:
        print("[WARN] No dates found in the specified range")
        print(f"[INFO] Available dates: {available_dates[:5]}...{available_dates[-5:]}")
        return

    # Connect to database
    if not args.dry_run:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()

    total_articles = 0
    new_articles = 0
    skipped_articles = 0
    failed_articles = 0

    try:
        for date_key in target_dates:
            articles = news_list[date_key]
            print(f"\n[DATE] {date_key}: {len(articles)} articles")

            for article_data in articles:
                news_id = article_data.get('news_id', '')
                title = article_data.get('title', '')[:40]
                total_articles += 1

                # Check if exists
                if not args.dry_run:
                    if article_exists(cursor, news_id):
                        print(f"  [SKIP] {news_id}: {title}...")
                        skipped_articles += 1
                        continue

                # Parse article
                print(f"  [FETCH] {news_id}: {title}...")
                parsed = parse_article_html(session, news_id, article_data)

                if not parsed:
                    failed_articles += 1
                    continue

                if args.dry_run:
                    print(f"  [DRY] Would insert: {parsed['title']}")
                    new_articles += 1
                else:
                    insert_article(cursor, parsed)
                    new_articles += 1
                    print(f"  [OK] Inserted: {parsed['title'][:40]}")

        if not args.dry_run:
            conn.commit()

    finally:
        if not args.dry_run:
            cursor.close()
            conn.close()

    print(f"\n{'='*60}")
    print(f"Summary")
    print(f"{'='*60}")
    print(f"Total articles processed: {total_articles}")
    print(f"New articles inserted: {new_articles}")
    print(f"Skipped (already exist): {skipped_articles}")
    print(f"Failed to parse: {failed_articles}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
