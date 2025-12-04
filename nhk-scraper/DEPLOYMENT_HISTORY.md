# NHK Easy News API - Complete Deployment History & Documentation

**Date:** December 3, 2025
**Project:** Replacing unreachable homeserver infrastructure with cloud-based hosting
**Status:** ✅ Successfully deployed to Railway

---

## Table of Contents
1. [Problem Statement](#problem-statement)
2. [Solution Architecture](#solution-architecture)
3. [Deployment Journey](#deployment-journey)
4. [Final Working Configuration](#final-working-configuration)
5. [Challenges & Solutions](#challenges--solutions)
6. [Testing & Verification](#testing--verification)
7. [Maintenance & Operations](#maintenance--operations)
8. [Future Improvements](#future-improvements)
9. [Update: Dec 4 - Cron Job Debugging](#update-december-4-2025---cron-job-debugging--logging-improvements)
10. [Moshimoshi Integration](#moshimoshi-integration-no-changes-required)
11. [Backfill Script](#backfill-script-fetching-older-articles)

---

## Problem Statement

### Initial Situation
- **Homeserver**: `sheldon-term` (100.111.118.91) became completely unreachable
- **Symptoms**:
  - Connection timeouts
  - 100% packet loss
  - SSH failures
  - All services down

### Services Requiring Migration
1. **NHK Easy News Scraper API** (previously at `nhk.selfmind.dev`)
   - Spring Boot Kotlin application
   - MySQL database backend
   - Daily scraping of Japanese news articles
   - REST API serving news with furigana annotations

2. **Kokoro TTS Service** (previously at `api.selfmind.dev/kokoro`)
   - Kokoro-82M text-to-speech model
   - OpenAI-compatible API endpoints
   - Japanese/English/Chinese voice support

### Requirements
- CLI-based deployment and management
- Production-ready hosting
- Cost-effective solution
- Integration with existing moshimoshi Next.js app (deployed on Vercel)

---

## Solution Architecture

### Final Architecture (Railway-Based)

```
┌─────────────────────────────────────────────────────────────┐
│                    Railway Project                          │
│              "terrific-communication"                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐      ┌──────────────────┐            │
│  │  nhk-easy-api    │◄─────┤     MySQL        │            │
│  │  (REST API)      │      │  (Database)      │            │
│  │  Port: 8080      │      │  Internal:3306   │            │
│  │  Public Domain   │      └──────────────────┘            │
│  └──────────────────┘              ▲                        │
│          │                         │                        │
│          │                         │                        │
│          │               ┌─────────┴────────┐               │
│          │               │  nhk-easy-task   │               │
│          │               │  (Scraper)       │               │
│          │               │  Runs on deploy  │               │
│          │               │  or cron         │               │
│          │               └──────────────────┘               │
│          │                                                   │
└──────────┼───────────────────────────────────────────────────┘
           │
           │ HTTPS
           ▼
┌──────────────────────┐
│   moshimoshi App     │
│   (Vercel)           │
│   Fetches news       │
└──────────────────────┘
```

### Component Details

#### 1. nhk-easy-api (REST API Service)
- **Source**: GitHub repo `HelyeFab/nhk-easy-api` (forked from `nhk-news-web-easy/nhk-easy-api`)
- **Technology**: Spring Boot 2.6.2, Kotlin, Hibernate ORM
- **Function**: Serves news articles via REST endpoints
- **URL**: `https://nhk-easy-api-production.up.railway.app`
- **Endpoints**:
  - `GET /actuator/health` - Health check
  - `GET /news?startDate=X&endDate=Y` - Fetch news articles

#### 2. nhk-easy-task (Scraper Service)
- **Source**: GitHub repo `HelyeFab/nhk-easy-task` (forked from `nhk-news-web-easy/nhk-easy-task`)
- **Technology**: Spring Boot 2.6.2, Kotlin, CommandLineRunner pattern
- **Function**: Scrapes NHK Easy News website and stores articles in MySQL
- **Execution Model**: Runs once on startup, then exits (`exitProcess(0)`)
- **Trigger**: Manual redeploy or cron schedule (to be configured)

#### 3. MySQL Database
- **Type**: Railway MySQL service
- **Internal Hostname**: `mysql.railway.internal`
- **Port**: 3306
- **Database Name**: `railway`
- **Tables**: Auto-created by Hibernate (DDL mode: `update`)
  - `news` - Main articles table
  - `news_images` - Article images
  - `sentences` - Article sentences with furigana
  - `words` - Vocabulary words

---

## Deployment Journey

### Phase 1: Modal Attempts (Failed)

#### Attempt 1.1: Kokoro TTS on Modal
**Goal**: Deploy Kokoro-82M TTS model to Modal
**File**: `deploy_kokoro.py`
**Result**: ❌ Failed

**Issues Encountered**:
1. Missing dependencies during image build (`loguru`, `huggingface-hub`)
2. Deprecated Modal API usage:
   - `keep_warm=1` → should use `min_containers`
   - `allow_concurrent_inputs` → deprecated
   - `@modal.web_endpoint` → should use `@modal.fastapi_endpoint`
3. Build process failed in background (process ID: ec4149)

**Code Created**:
```python
# deploy_kokoro.py
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libsndfile1")
    .pip_install(
        "fastapi[standard]==0.115.6",
        "torch==2.5.1",
        "torchaudio==2.5.1",
        "loguru",
        "huggingface-hub",
    )
    .run_commands(
        "cd /root && git clone https://github.com/remsky/Kokoro-FastAPI.git",
        "cd /root/Kokoro-FastAPI && python docker/scripts/download_model.py",
    )
)
```

**Status**: Pending - needs API updates and build investigation

#### Attempt 1.2: Simple Python NHK Scraper on Modal
**Goal**: Deploy lightweight Python scraper using `nhk-easy` library
**File**: `deploy_nhk_simple.py`
**Result**: ❌ Failed

**Issues Encountered**:
1. HTTP 401 Unauthorized from NHK API
2. NHK blocks simple HTTP requests without proper headers
3. `nhk-easy` library limitations (only fetches today's articles)

**Error**:
```
401 Client Error: Unauthorized for url: https://news.web.nhk/news/easy/news-list.json
```

**Lesson Learned**: NHK requires more sophisticated scraping approach (like the Spring Boot implementation)

#### Attempt 1.3: Spring Boot Docker on Modal
**Goal**: Deploy existing Spring Boot NHK API Docker images to Modal
**File**: `deploy_nhk_springboot.py`
**Result**: ❌ Failed

**Issues Encountered**:
1. Modal requires Python in base images
2. Spring Boot Docker images are Java-only (no Python runtime)

**Error**:
```
We were unable to determine the version of Python installed in the Image
```

**Lesson Learned**: Modal is primarily designed for Python workloads, not Java/Spring Boot

---

### Phase 2: Railway Migration (Success)

#### Decision to Pivot
After Modal failures, pivoted to Railway because:
- Native Docker support (no Python requirement)
- Supports both Spring Boot services
- Built-in MySQL database
- $5/month free credit
- CLI available for management

#### Step 2.1: Railway CLI Setup
**Challenge**: Railway npm package doesn't support ARM64 architecture

**Solution**: Used bash installer instead
```bash
bash <(curl -fsSL cli.new/install)
```

**Authentication**:
```bash
railway login  # Opens browser for OAuth
railway whoami # Verify: Emmanuel Fabiani (emmanuelfabiani23@gmail.com)
```

#### Step 2.2: MySQL Database Creation
Created MySQL service within Railway project:
- **Project Name**: terrific-communication
- **Environment**: production
- **Auto-generated variables**:
  - `MYSQLHOST` → `mysql.railway.internal`
  - `MYSQLPORT` → `3306`
  - `MYSQLUSER` → `root`
  - `MYSQLPASSWORD` → `MKCixlltjXujzRRSdwqtVQqLfLOHFOMk`
  - `MYSQLDATABASE` → `railway`

#### Step 2.3: Deploy nhk-easy-api Service

**Method**: GitHub integration via Railway Dashboard

**Steps**:
1. Forked `nhk-news-web-easy/nhk-easy-api` to `HelyeFab/nhk-easy-api`
2. Railway Dashboard → New Service → GitHub Repo
3. Selected `HelyeFab/nhk-easy-api`
4. Railway auto-detected Dockerfile and built image

**Environment Variables** (set via CLI):
```bash
railway variables --set \
  'SPRING_DATASOURCE_URL=jdbc:mysql://mysql.railway.internal:3306/railway?useSSL=false&allowPublicKeyRetrieval=true' \
  --set 'SPRING_DATASOURCE_USERNAME=root' \
  --set 'SPRING_DATASOURCE_PASSWORD=MKCixlltjXujzRRSdwqtVQqLfLOHFOMk' \
  --set 'SPRING_JPA_HIBERNATE_DDL_AUTO=update'
```

**Domain Generation**:
- Generated Railway domain: `nhk-easy-api-production.up.railway.app`
- Port configured: 8080

**Initial Issue - Database Connection Failed**:
```
com.mysql.cj.jdbc.exceptions.CommunicationsException: Communications link failure
```

**Root Cause**: Initially tried using external database URL (`shinkansen.proxy.rlwy.net`) which wasn't accessible from Railway's internal network

**Fix**: Changed to internal MySQL hostname:
- External: `shinkansen.proxy.rlwy.net:41383` ❌
- Internal: `mysql.railway.internal:3306` ✅

**Second Issue - Missing Tables**:
```
Schema-validation: missing table [news]
```

**Root Cause**: Empty database, Hibernate configured for validation not creation

**Fix**: Set DDL mode to `update`:
```bash
railway variables --set 'SPRING_JPA_HIBERNATE_DDL_AUTO=update'
```

**Result**: ✅ Tables auto-created, API running successfully

#### Step 2.4: Deploy nhk-easy-task Service

**Initial Attempt - Dashboard Deploy**:
Encountered "unspecified error" when trying to deploy via Dashboard UI

**Solution**: Used Railway CLI instead

**Steps**:
```bash
# Link to project
cd /mnt/c/Users/esfab/WinDevProjects/modal-services/nhk-scraper
railway link  # Selected: terrific-communication / production

# Fork repository
# Forked nhk-news-web-easy/nhk-easy-task to HelyeFab/nhk-easy-task

# Add service via CLI
railway add \
  --service nhk-easy-task \
  --repo HelyeFab/nhk-easy-task

# Link to new service
railway service link nhk-easy-task

# Set environment variables
railway variables --set \
  'SPRING_DATASOURCE_URL=jdbc:mysql://mysql.railway.internal:3306/railway?useSSL=false&allowPublicKeyRetrieval=true' \
  --set 'SPRING_DATASOURCE_USERNAME=root' \
  --set 'SPRING_DATASOURCE_PASSWORD=MKCixlltjXujzRRSdwqtVQqLfLOHFOMk' \
  --set 'SPRING_JPA_HIBERNATE_DDL_AUTO=update'
```

**Deployment Status**:
```bash
railway service status
# Output:
# Service: nhk-easy-task
# Deployment: 36385907-feb7-4f6a-b9c5-d024cc3289cf
# Status: SUCCESS
```

**Verification** (from logs):
```
2025-12-03 21:48:02.276  INFO  Started ApplicationKt in 9.677 seconds
2025-12-03 21:48:02.303  INFO  Start to fetch news, now=2025-12-03T21:48:02.303Z
2025-12-03 21:48:12.489  INFO  Closing JPA EntityManagerFactory
2025-12-03 21:48:12.504  INFO  HikariPool-1 - Shutdown completed
```

**Result**: ✅ Scraper executed successfully, ran for ~10 seconds, then exited gracefully

---

## Final Working Configuration

### Railway Services Configuration

#### Service 1: nhk-easy-api
```
Name: nhk-easy-api
Type: Web Service
Source: GitHub (HelyeFab/nhk-easy-api)
Build: Dockerfile
Port: 8080
Domain: nhk-easy-api-production.up.railway.app

Environment Variables:
  SPRING_DATASOURCE_URL=jdbc:mysql://mysql.railway.internal:3306/railway?useSSL=false&allowPublicKeyRetrieval=true
  SPRING_DATASOURCE_USERNAME=root
  SPRING_DATASOURCE_PASSWORD=MKCixlltjXujzRRSdwqtVQqLfLOHFOMk
  SPRING_JPA_HIBERNATE_DDL_AUTO=update

  # Auto-injected by Railway:
  RAILWAY_ENVIRONMENT=production
  RAILWAY_PROJECT_NAME=terrific-communication
  RAILWAY_SERVICE_NAME=nhk-easy-api
```

#### Service 2: nhk-easy-task
```
Name: nhk-easy-task
Type: Service (batch job)
Source: GitHub (HelyeFab/nhk-easy-task)
Build: Dockerfile
Port: 8080 (for health check, not exposed)
Domain: None (internal service)

Environment Variables:
  SPRING_DATASOURCE_URL=jdbc:mysql://mysql.railway.internal:3306/railway?useSSL=false&allowPublicKeyRetrieval=true
  SPRING_DATASOURCE_USERNAME=root
  SPRING_DATASOURCE_PASSWORD=MKCixlltjXujzRRSdwqtVQqLfLOHFOMk
  SPRING_JPA_HIBERNATE_DDL_AUTO=update

  # Auto-injected by Railway:
  RAILWAY_SERVICE_NHK_EASY_API_URL=nhk-easy-api-production.up.railway.app
```

#### Service 3: MySQL
```
Name: MySQL
Type: Database
Internal Host: mysql.railway.internal
Port: 3306
Database: railway
Root Password: MKCixlltjXujzRRSdwqtVQqLfLOHFOMk

Tables (auto-created):
  - news
  - news_images
  - sentences
  - words
```

### railway.json Configuration
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

---

## Moshimoshi Integration Guide

### Overview
Moshimoshi is a Next.js application deployed on Vercel that previously fetched NHK Easy News from the homeserver at `nhk.selfmind.dev`. Now it needs to be updated to use the new Railway API.

### API Endpoint Changes

#### Old Homeserver URL (DEPRECATED)
```
http://nhk.selfmind.dev/news
http://100.111.118.91:8080/news
```
❌ **Status**: Unreachable (homeserver down)

#### New Railway URL (ACTIVE)
```
https://nhk-easy-api-production.up.railway.app/news
```
✅ **Status**: Active and operational

### Implementation Steps

#### Step 1: Update Environment Variables

**In Vercel Dashboard**:
1. Go to your moshimoshi project settings
2. Navigate to Environment Variables
3. Add or update:
   ```
   NEXT_PUBLIC_NHK_API_BASE_URL=https://nhk-easy-api-production.up.railway.app
   ```
4. Redeploy the application for changes to take effect

**In Local Development** (`.env.local`):
```bash
# .env.local
NEXT_PUBLIC_NHK_API_BASE_URL=https://nhk-easy-api-production.up.railway.app
```

#### Step 2: Update API Client Code

**Before** (Hardcoded homeserver URL):
```typescript
// ❌ Old implementation
const response = await fetch(
  `http://nhk.selfmind.dev/news?startDate=${startDate}&endDate=${endDate}`
);
```

**After** (Using environment variable):
```typescript
// ✅ New implementation
const NHK_API_BASE_URL = process.env.NEXT_PUBLIC_NHK_API_BASE_URL ||
                         'https://nhk-easy-api-production.up.railway.app';

const response = await fetch(
  `${NHK_API_BASE_URL}/news?startDate=${startDate}&endDate=${endDate}`
);
```

#### Step 3: Create API Utility Module (Recommended)

**Create `lib/nhk-api.ts`**:
```typescript
// lib/nhk-api.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_NHK_API_BASE_URL ||
                     'https://nhk-easy-api-production.up.railway.app';

export interface NHKArticle {
  newsId: string;
  title: string;
  titleWithRuby: string;
  outline: string;
  outlineWithRuby: string;
  body: string;
  bodyWithoutHtml: string;
  url: string;
  m3u8Url: string;
  imageUrl: string;
  publishedAtUtc: string;
}

export interface FetchNewsParams {
  startDate: string;  // ISO 8601 format
  endDate: string;    // ISO 8601 format
}

/**
 * Fetch NHK Easy News articles from Railway API
 *
 * @param params - Date range for fetching articles
 * @returns Array of news articles
 * @throws Error if API request fails
 *
 * @example
 * ```typescript
 * const articles = await fetchNHKNews({
 *   startDate: '2025-12-01T00:00:00.000Z',
 *   endDate: '2025-12-03T23:59:59.000Z'
 * });
 * ```
 */
export async function fetchNHKNews(
  params: FetchNewsParams
): Promise<NHKArticle[]> {
  const { startDate, endDate } = params;

  // Validate dates
  if (!startDate || !endDate) {
    throw new Error('startDate and endDate are required');
  }

  // Build URL with query parameters
  const url = new URL(`${API_BASE_URL}/news`);
  url.searchParams.set('startDate', startDate);
  url.searchParams.set('endDate', endDate);

  try {
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      // Add timeout for production
      signal: AbortSignal.timeout(10000), // 10 second timeout
    });

    if (!response.ok) {
      throw new Error(
        `NHK API error: ${response.status} ${response.statusText}`
      );
    }

    const articles: NHKArticle[] = await response.json();
    return articles;
  } catch (error) {
    if (error instanceof Error) {
      console.error('Failed to fetch NHK news:', error.message);
      throw new Error(`Failed to fetch NHK news: ${error.message}`);
    }
    throw error;
  }
}

/**
 * Check if NHK API is healthy
 *
 * @returns true if API is responding, false otherwise
 */
export async function checkNHKApiHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/actuator/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000), // 5 second timeout
    });

    if (!response.ok) return false;

    const health = await response.json();
    return health.status === 'UP';
  } catch (error) {
    console.error('NHK API health check failed:', error);
    return false;
  }
}

/**
 * Get articles for today
 */
export async function getTodaysArticles(): Promise<NHKArticle[]> {
  const today = new Date();
  const startOfDay = new Date(today.setHours(0, 0, 0, 0));
  const endOfDay = new Date(today.setHours(23, 59, 59, 999));

  return fetchNHKNews({
    startDate: startOfDay.toISOString(),
    endDate: endOfDay.toISOString(),
  });
}

/**
 * Get articles for a specific date range (convenience function)
 */
export async function getArticlesByDateRange(
  startDate: Date,
  endDate: Date
): Promise<NHKArticle[]> {
  return fetchNHKNews({
    startDate: startDate.toISOString(),
    endDate: endDate.toISOString(),
  });
}
```

#### Step 4: Update Page/Component Usage

**Example: News Page**:
```typescript
// app/news/page.tsx or pages/news.tsx

import { fetchNHKNews, getTodaysArticles } from '@/lib/nhk-api';
import { useState, useEffect } from 'react';

export default function NewsPage() {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadArticles() {
      try {
        setLoading(true);

        // Option 1: Get today's articles
        const data = await getTodaysArticles();

        // Option 2: Get specific date range
        // const data = await fetchNHKNews({
        //   startDate: '2025-12-01T00:00:00.000Z',
        //   endDate: '2025-12-03T23:59:59.000Z'
        // });

        setArticles(data);
      } catch (err) {
        setError(err.message);
        console.error('Failed to load articles:', err);
      } finally {
        setLoading(false);
      }
    }

    loadArticles();
  }, []);

  if (loading) return <div>Loading articles...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <h1>NHK Easy News</h1>
      {articles.map((article) => (
        <article key={article.newsId}>
          <h2 dangerouslySetInnerHTML={{ __html: article.titleWithRuby }} />
          <p dangerouslySetInnerHTML={{ __html: article.outlineWithRuby }} />
          {article.imageUrl && (
            <img src={article.imageUrl} alt={article.title} />
          )}
          <a href={article.url} target="_blank" rel="noopener noreferrer">
            Read full article
          </a>
          {article.m3u8Url && (
            <audio controls>
              <source src={article.m3u8Url} type="application/x-mpegURL" />
            </audio>
          )}
        </article>
      ))}
    </div>
  );
}
```

#### Step 5: Server-Side Data Fetching (Next.js App Router)

**For Server Components**:
```typescript
// app/news/page.tsx

import { fetchNHKNews } from '@/lib/nhk-api';

export default async function NewsPage() {
  // Fetch data on the server
  const articles = await fetchNHKNews({
    startDate: '2025-12-01T00:00:00.000Z',
    endDate: '2025-12-03T23:59:59.000Z'
  });

  return (
    <div>
      <h1>NHK Easy News</h1>
      {articles.map((article) => (
        <article key={article.newsId}>
          <h2 dangerouslySetInnerHTML={{ __html: article.titleWithRuby }} />
          {/* ... rest of article display */}
        </article>
      ))}
    </div>
  );
}

// Enable ISR (Incremental Static Regeneration)
export const revalidate = 3600; // Revalidate every hour
```

#### Step 6: Error Handling & Fallbacks

**Add error boundaries and fallback UI**:
```typescript
// app/error.tsx

'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div>
      <h2>Failed to load NHK news</h2>
      <p>{error.message}</p>
      <button onClick={() => reset()}>Try again</button>
    </div>
  );
}
```

#### Step 7: Add Health Check Monitoring

**Create a health check endpoint in moshimoshi**:
```typescript
// app/api/health/nhk/route.ts

import { checkNHKApiHealth } from '@/lib/nhk-api';
import { NextResponse } from 'next/server';

export async function GET() {
  const isHealthy = await checkNHKApiHealth();

  return NextResponse.json(
    {
      service: 'nhk-api',
      status: isHealthy ? 'healthy' : 'unhealthy',
      url: process.env.NEXT_PUBLIC_NHK_API_BASE_URL
    },
    { status: isHealthy ? 200 : 503 }
  );
}
```

### Testing the Integration

#### 1. Test API Connection
```bash
# From moshimoshi project directory
curl "https://nhk-easy-api-production.up.railway.app/actuator/health"
# Expected: {"status":"UP"}
```

#### 2. Test Article Fetch
```bash
curl "https://nhk-easy-api-production.up.railway.app/news?startDate=2025-12-03T00:00:00.000Z&endDate=2025-12-04T23:59:59.000Z"
# Expected: JSON array with articles
```

#### 3. Test in Development
```bash
# In moshimoshi directory
npm run dev
# Visit http://localhost:3000/news
# Verify articles load correctly
```

#### 4. Test in Production (after deployment)
- Deploy to Vercel with updated environment variables
- Visit your production URL
- Check browser console for any API errors
- Verify articles display correctly with furigana

### Migration Checklist

- [ ] Update environment variables in Vercel
- [ ] Update environment variables in `.env.local`
- [ ] Create or update `lib/nhk-api.ts` utility
- [ ] Replace all hardcoded API URLs in codebase
- [ ] Update any API client functions
- [ ] Add error handling for API failures
- [ ] Test locally with `npm run dev`
- [ ] Deploy to Vercel
- [ ] Verify production deployment works
- [ ] Remove old homeserver references
- [ ] Update documentation/README

### Common Issues & Solutions

#### Issue 1: CORS Errors
**Symptom**: Browser console shows CORS policy errors
**Solution**: Railway API should allow CORS by default, but if issues persist, add CORS headers in Spring Boot configuration

#### Issue 2: Date Format Errors
**Symptom**: API returns empty array or error
**Solution**: Ensure dates are in ISO 8601 format: `YYYY-MM-DDTHH:mm:ss.sssZ`
```typescript
const isoDate = new Date().toISOString(); // ✅ Correct format
```

#### Issue 3: Slow Response Times
**Symptom**: Articles take long to load
**Solutions**:
- Implement caching in moshimoshi
- Use ISR (Incremental Static Regeneration) in Next.js
- Consider adding Redis cache layer on Railway

#### Issue 4: API Rate Limiting
**Symptom**: Too many requests error
**Solution**: Implement request caching and debouncing in moshimoshi frontend

### Performance Optimization Tips

1. **Cache API Responses**:
```typescript
import { cache } from 'react';

export const getCachedArticles = cache(async (startDate: string, endDate: string) => {
  return fetchNHKNews({ startDate, endDate });
});
```

2. **Use SWR for Client-Side Caching**:
```typescript
import useSWR from 'swr';

function useNHKArticles(startDate: string, endDate: string) {
  const { data, error, isLoading } = useSWR(
    `/api/nhk/news?start=${startDate}&end=${endDate}`,
    () => fetchNHKNews({ startDate, endDate }),
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      refreshInterval: 3600000, // Refresh every hour
    }
  );

  return { articles: data, error, isLoading };
}
```

3. **Prefetch Articles**:
```typescript
// Prefetch next page of articles
<Link
  href="/news/next-page"
  onMouseEnter={() => {
    // Prefetch on hover
    fetchNHKNews({ startDate, endDate });
  }}
>
  Next Page
</Link>
```

### Monitoring & Analytics

**Add logging for API calls**:
```typescript
export async function fetchNHKNews(params: FetchNewsParams): Promise<NHKArticle[]> {
  const startTime = Date.now();

  try {
    const articles = await /* ... fetch logic ... */;

    // Log successful fetch
    console.log(`NHK API: Fetched ${articles.length} articles in ${Date.now() - startTime}ms`);

    return articles;
  } catch (error) {
    // Log error with context
    console.error('NHK API Error:', {
      error: error.message,
      params,
      duration: Date.now() - startTime,
    });
    throw error;
  }
}
```

**Integrate with analytics** (optional):
```typescript
// Track API usage in your analytics
analytics.track('nhk_articles_fetched', {
  count: articles.length,
  dateRange: { startDate, endDate },
  loadTime: Date.now() - startTime,
});
```

---

## Challenges & Solutions

### Challenge 1: ARM64 Architecture Compatibility
**Problem**: Railway CLI npm package doesn't support ARM64
**Error**: `Failed fetching the binary: Not Found`
**Solution**: Used bash installer: `bash <(curl -fsSL cli.new/install)`

### Challenge 2: WSL/Windows Railway CLI Access
**Problem**: Railway CLI auth in Windows not visible in WSL root session
**Error**: `Unauthorized. Please login with railway login`
**Solution**: Execute Railway commands via PowerShell from WSL:
```bash
powershell.exe -Command "railway whoami"
powershell.exe -Command "cd C:\Users\esfab\...; railway status"
```

### Challenge 3: External Database Connection Failed
**Problem**: Spring Boot trying to connect to external database URL
**Error**: `Communications link failure` to `shinkansen.proxy.rlwy.net`
**Root Cause**: External database not accessible from Railway internal network
**Solution**: Use Railway's internal MySQL service with hostname `mysql.railway.internal`

### Challenge 4: Database Schema Missing
**Problem**: Hibernate validation failed, no tables exist
**Error**: `Schema-validation: missing table [news]`
**Root Cause**: Empty database, Hibernate DDL mode set to `validate`
**Solution**: Change DDL mode to `update` to auto-create tables:
```bash
SPRING_JPA_HIBERNATE_DDL_AUTO=update
```

### Challenge 5: Scraper Not Running
**Problem**: Scraper deployed successfully but database remained empty
**Root Cause**: Date range query mismatch (querying 2024 dates, scraper ran on 2025-12-03)
**Solution**: Query with correct date: `startDate=2025-12-03`
**Verification**: Found 4 articles successfully scraped and stored

### Challenge 6: Railway Dashboard "Unspecified Error"
**Problem**: Could not add nhk-easy-task service via Dashboard UI
**Error**: Generic "unspecified error" message
**Solution**: Used Railway CLI instead:
```bash
railway add --service nhk-easy-task --repo HelyeFab/nhk-easy-task
```

### Challenge 7: Understanding Task Execution Model
**Problem**: Confusion about whether scraper runs continuously or once
**Investigation**: Analyzed source code - `CommandLineRunner` with `exitProcess(0)`
**Finding**: Task runs once on startup, scrapes articles, then exits
**Implication**: Need cron schedule to run regularly, or manual redeploy triggers

---

## Testing & Verification

### API Health Check
```bash
curl https://nhk-easy-api-production.up.railway.app/actuator/health
# Response: {"status":"UP"}
```

### Fetch News Articles
```bash
curl "https://nhk-easy-api-production.up.railway.app/news?startDate=2025-12-03T00:00:00.000Z&endDate=2025-12-04T23:59:59.000Z"
```

**Response**: 4 articles successfully returned:
1. **たくさんの雪や強い風に気をつけて** (Watch out for snow and strong winds)
   - ID: ne2025120311491
   - Published: 2025-12-03T10:30:00Z

2. **香港の火事から1週間** (One week since Hong Kong fire)
   - ID: ne2025120311530
   - Published: 2025-12-03T10:29:00Z

3. **アメリカの「ブラックフライデー」...** (America's Black Friday sales)
   - ID: ne2025120311510
   - Published: 2025-12-03T10:28:00Z

4. **今年インターネットの検索が増えたことば** (Trending search terms)
   - ID: ne2025120311563
   - Published: 2025-12-03T10:27:00Z

### Article Data Structure
Each article includes:
- ✅ `newsId` - Unique identifier
- ✅ `title` - Article title (plain)
- ✅ `titleWithRuby` - Title with furigana annotations
- ✅ `outline` - Brief summary
- ✅ `outlineWithRuby` - Summary with furigana
- ✅ `body` - Full article HTML with color-coded word types
- ✅ `bodyWithoutHtml` - Plain text version
- ✅ `url` - Original NHK article URL
- ✅ `m3u8Url` - Audio narration stream URL
- ✅ `imageUrl` - Article thumbnail
- ✅ `publishedAtUtc` - Publication timestamp

### Railway Service Status
```bash
# Check API status
railway service link nhk-easy-api
railway service status
# Output: Status: SUCCESS

# Check Task status
railway service link nhk-easy-task
railway service status
# Output: Status: SUCCESS

# View logs
railway logs
```

---

## Maintenance & Operations

### Manual Scraper Trigger
Since the scraper runs once and exits, to manually fetch new articles:

```bash
# Option 1: Redeploy via CLI
cd /mnt/c/Users/esfab/WinDevProjects/modal-services/nhk-scraper
railway service link nhk-easy-task
railway redeploy

# Option 2: Redeploy via Dashboard
# 1. Go to https://railway.app/dashboard
# 2. Select nhk-easy-task service
# 3. Click "Redeploy"
```

### Setting Up Cron Schedule (TODO)
Railway supports cron jobs for scheduled task execution:

**Method 1: Railway Dashboard**
1. Go to nhk-easy-task service settings
2. Look for "Cron Schedule" or "Scheduling" section
3. Set cron expression: `0 * * * *` (hourly)

**Method 2: Code Modification**
Alternative: Modify the application to use Spring's `@Scheduled` annotation:
```kotlin
@Scheduled(cron = "0 * * * *")  // Hourly
fun scheduledScrape() {
    newsTask.saveTopNews()
}
```
Then remove `exitProcess(0)` to keep the app running.

### Monitoring & Logs

**View Real-time Logs**:
```bash
railway logs
```

**Check Deployment Status**:
```bash
railway service status
```

**View Variables**:
```bash
railway variables
```

### Database Access

**Via Railway Dashboard**:
1. Go to MySQL service
2. Click "Connect" tab
3. Use provided connection string

**Via CLI** (if supported):
```bash
railway connect MySQL
```

### Cost Monitoring
- Railway provides $5/month free credit
- Monitor usage in Railway Dashboard
- Current setup uses:
  - 2 web services (nhk-easy-api, nhk-easy-task)
  - 1 MySQL database
  - Estimated cost: ~$10-15/month (verify in dashboard)

---

## Future Improvements

### High Priority

#### 1. Configure Automated Scraping Schedule
**Current State**: Scraper runs only on deployment
**Goal**: Run hourly to fetch new articles automatically
**Options**:
- Railway cron jobs (recommended)
- Modify code to use `@Scheduled` annotation
- External cron service (GitHub Actions, etc.)

**Recommended Solution**:
```bash
# In Railway Dashboard:
# nhk-easy-task → Settings → Cron Schedule
# Set: 0 * * * * (every hour)
```

#### 2. Fix Kokoro TTS Deployment
**Status**: Pending (Modal deployment failed)
**Issues**:
- Deprecated Modal API usage
- Build process errors
- Background process ec4149 failed

**Next Steps**:
1. Update `deploy_kokoro.py` with current Modal API:
   ```python
   @app.function(
       image=image,
       gpu=None,
       cpu=4,
       memory=4096,
       min_containers=1,  # Instead of keep_warm
       timeout=120,
   )
   @modal.fastapi_endpoint()  # Instead of @modal.web_endpoint
   ```
2. Investigate background build logs
3. Test deployment with updated code

#### 3. Update moshimoshi to Use New API
**Current State**: moshimoshi still points to unreachable homeserver
**Goal**: Update API base URL to Railway endpoint

**Files to Modify**:
```typescript
// In moshimoshi codebase
const NHK_API_BASE_URL = "https://nhk-easy-api-production.up.railway.app"

// Update all fetch calls:
fetch(`${NHK_API_BASE_URL}/news?startDate=${start}&endDate=${end}`)
```

**Environment Variable Approach** (recommended):
```bash
# In Vercel dashboard or .env:
NEXT_PUBLIC_NHK_API_URL=https://nhk-easy-api-production.up.railway.app
```

### Medium Priority

#### 4. Add Monitoring & Alerting
- Set up health check monitoring (UptimeRobot, etc.)
- Configure alerts for scraper failures
- Track API response times
- Monitor database size growth

#### 5. Add Backup Strategy
- Railway database backups
- Export articles to S3/cloud storage periodically
- Version control for configuration

#### 6. Optimize Database Performance
- Add indexes on frequently queried fields
- Implement query caching
- Consider read replicas if needed

#### 7. Enhance Security
- Add API authentication if needed
- Rate limiting for public endpoints
- CORS configuration review
- Database access restrictions

### Low Priority

#### 8. Additional Features
- Article search functionality
- Filtering by difficulty level
- User favorites/bookmarks
- Article history tracking

#### 9. Performance Optimization
- CDN for static assets (images, audio)
- Response caching
- Database query optimization
- Connection pooling tuning

#### 10. Documentation
- API documentation (OpenAPI/Swagger)
- User guide for moshimoshi
- Deployment runbook
- Troubleshooting guide

---

## Reference Links

### Repositories
- **nhk-easy-api (original)**: https://github.com/nhk-news-web-easy/nhk-easy-api
- **nhk-easy-api (fork)**: https://github.com/HelyeFab/nhk-easy-api
- **nhk-easy-task (original)**: https://github.com/nhk-news-web-easy/nhk-easy-task
- **nhk-easy-task (fork)**: https://github.com/HelyeFab/nhk-easy-task

### Services
- **Railway Dashboard**: https://railway.app/dashboard
- **Railway CLI Docs**: https://docs.railway.app/develop/cli
- **Modal Docs**: https://modal.com/docs
- **NHK Easy News**: https://www3.nhk.or.jp/news/easy/

### API Endpoints
- **Production API**: https://nhk-easy-api-production.up.railway.app
- **Health Check**: https://nhk-easy-api-production.up.railway.app/actuator/health
- **News Endpoint**: https://nhk-easy-api-production.up.railway.app/news

### Tools & Technologies
- **Spring Boot**: https://spring.io/projects/spring-boot
- **Kotlin**: https://kotlinlang.org/
- **Hibernate**: https://hibernate.org/
- **Railway**: https://railway.app/
- **Modal**: https://modal.com/

---

## Quick Command Reference

### Railway CLI Essentials
```bash
# Authentication
railway login
railway whoami

# Project/Service Management
railway status
railway service link <service-name>
railway service status

# Deployment
railway up
railway redeploy

# Variables
railway variables
railway variables --set 'KEY=value'

# Logs
railway logs
railway logs --follow

# Domain Management
railway domain
```

### Testing Commands
```bash
# Health check
curl https://nhk-easy-api-production.up.railway.app/actuator/health

# Fetch news (with date range)
curl "https://nhk-easy-api-production.up.railway.app/news?startDate=2025-12-03T00:00:00.000Z&endDate=2025-12-04T23:59:59.000Z"

# Pretty print JSON
curl "..." | jq '.'
```

### PowerShell from WSL
```bash
# Execute Railway commands via PowerShell
powershell.exe -Command "railway whoami"
powershell.exe -Command "cd C:\Users\esfab\WinDevProjects\modal-services\nhk-scraper; railway status"
powershell.exe -Command "cd C:\Users\esfab\WinDevProjects\modal-services\nhk-scraper; railway logs"
```

---

## Conclusion

Successfully migrated NHK Easy News infrastructure from unreachable homeserver to Railway cloud platform. The system is now:

✅ **Fully operational** - API serving articles, scraper populating database
✅ **Cloud-hosted** - Railway infrastructure with MySQL database
✅ **CLI-manageable** - Railway CLI for deployment and monitoring
✅ **Production-ready** - Proper error handling, health checks, logging

**Total Deployment Time**: ~3-4 hours (including troubleshooting)
**Services Migrated**: 1 of 2 (NHK ✅, Kokoro pending ⏳)
**Deployment Cost**: ~$10-15/month (Railway)

The foundation is solid. Next steps focus on automation (cron scheduling), completing Kokoro TTS migration, and updating moshimoshi integration.

---

---

## Update: December 4, 2025 - Cron Job Debugging & Logging Improvements

### Issue Reported
After setting up the cron schedule for `nhk-easy-task`, the job appeared to run but:
- Logs only showed `"Start to fetch news"` then immediate shutdown
- No error messages visible
- No new articles appearing in database

### Investigation Findings

#### 1. Root Cause Identified: Silent Deduplication
The `NewsService.kt` had a silent return when all fetched articles already existed in the database:

```kotlin
// BEFORE (no logging)
if (latestNews.isEmpty()) {
    return  // ← Silent exit, no visibility
}
```

This meant when NHK's "top news" feed returned articles already in the database, the scraper completed successfully but logged nothing about what happened.

#### 2. System Was Actually Working Correctly
- NHK was returning 20 articles
- All 20 were already in the database (scraped on initial deployment)
- NHK simply hadn't published new articles yet
- The scraper was doing its job - just no visibility into the deduplication

### Fix Applied: Enhanced Logging

Updated the fork (`HelyeFab/nhk-easy-task`) with comprehensive logging:

**NewsTask.kt changes:**
```kotlin
logger.info("Fetching top news from NHK...")
topNews = newsFetcher.getTopNews()
logger.info("Successfully fetched {} articles from NHK", topNews.size)

logger.info("Parsing {} articles...", topNews.size)
// ... parsing ...
logger.info("Successfully parsed {} articles", parsedNews.size)

logger.info("Saving articles to database...")
newsService.saveAll(parsedNews)
logger.info("Save operation completed")
logger.info("News scraping task completed successfully")
```

**NewsService.kt changes:**
```kotlin
logger.info("Checking {} articles for duplicates", newsList.size)

if (latestNews.isEmpty()) {
    logger.info("No new articles to save - all {} articles already exist in database", newsList.size)
    return
}

logger.info("Saving {} new articles (out of {} fetched)", latestNews.size, newsList.size)
newsRepository.saveAll(latestNews)
logger.info("Successfully saved {} articles to database", latestNews.size)
```

### New Log Output Example

After the fix, logs now show complete visibility:

```
INFO: Start to fetch news, now=2025-12-04T10:17:04.105Z
INFO: Fetching top news from NHK...
INFO: Successfully fetched 20 articles from NHK
INFO: Parsing 20 articles...
INFO: Successfully parsed 20 articles
INFO: Saving articles to database...
INFO: Checking 20 articles for duplicates
INFO: No new articles to save - all 20 articles already exist in database
INFO: Save operation completed
INFO: News scraping task completed successfully
```

When new articles ARE available:
```
INFO: Checking 25 articles for duplicates
INFO: Saving 5 new articles (out of 25 fetched)
INFO: Successfully saved 5 articles to database
```

### Cron Schedule Status
- **Configured**: Yes, via Railway Dashboard
- **Working**: Yes, runs successfully
- **Current behavior**: Fetches from NHK, deduplicates, saves only new articles

### Database Status (as of Dec 4, 2025)
- **Total articles**: 20
- **Date range**: Nov 25 - Dec 3, 2025
- **Source**: NHK Easy News "top news" feed

---

## Moshimoshi Integration: No Changes Required

### API Contract Unchanged

**The Railway API is 100% compatible with the previous homeserver API.**

| Aspect | Old (Homeserver) | New (Railway) | Change Required? |
|--------|------------------|---------------|------------------|
| Base URL | `http://nhk.selfmind.dev` | `https://nhk-easy-api-production.up.railway.app` | **URL only** |
| Endpoint | `/news` | `/news` | No |
| Parameters | `startDate`, `endDate` | `startDate`, `endDate` | No |
| Response Format | JSON array | JSON array | No |
| Article Schema | Same fields | Same fields | No |
| HTTPS | No | Yes | Better |

### What Moshimoshi Needs to Update

**ONLY the API base URL needs to change:**

#### Option 1: Environment Variable (Recommended)
```bash
# In Vercel Dashboard or .env.local
NEXT_PUBLIC_NHK_API_BASE_URL=https://nhk-easy-api-production.up.railway.app
```

#### Option 2: Update in Code
If the URL is hardcoded in `functions/src/scrapers/nhkEasyScraper.ts`:

```typescript
// BEFORE
const apiUrl = `https://nhk.selfmind.dev/news?startDate=${start}&endDate=${end}`;

// AFTER
const apiUrl = `https://nhk-easy-api-production.up.railway.app/news?startDate=${start}&endDate=${end}`;
```

### What Does NOT Need to Change
- Article parsing logic
- Furigana handling
- Audio URL processing
- Image URL handling
- Date formatting
- Error handling patterns
- Pre-caching pipeline stages

### Testing the Integration
```bash
# Test that the new API works identically
curl "https://nhk-easy-api-production.up.railway.app/news?startDate=2025-12-01T00:00:00.000Z&endDate=2025-12-04T23:59:59.000Z"

# Verify health
curl "https://nhk-easy-api-production.up.railway.app/actuator/health"
# Expected: {"status":"UP"}
```

---

## Backfill Script: Fetching Older Articles

### Problem
The regular scraper (`nhk-easy-task`) only fetches from NHK's `top-list.json` endpoint, which returns ~20 current articles. To populate the database with historical articles, a separate backfill approach was needed.

### Solution: Python Backfill Script

Created `backfill_articles.py` - a standalone Python script that:
1. Authenticates with NHK using the same OAuth flow as the Kotlin scraper
2. Fetches from `news-list.json` (articles organized by date, ~243 dates available)
3. Parses each article's full HTML content
4. Inserts into the Railway MySQL database
5. Skips articles that already exist (deduplication by `news_id`)

### NHK API Endpoints

| Endpoint | Purpose | Used By |
|----------|---------|---------|
| `top-list.json` | Current ~20 top articles | Regular scraper (nhk-easy-task) |
| `news-list.json` | Articles by date (243+ dates) | Backfill script |

The `news-list.json` structure:
```json
{
  "2025-12-04": [article1, article2, ...],
  "2025-12-03": [article3, article4, ...],
  "2025-10-01": [...]
}
```

### Script Location
```
C:\Users\esfab\WinDevProjects\modal-services\nhk-scraper\backfill_articles.py
```

### Usage

```bash
# Backfill specific date range
python backfill_articles.py --start-date 2025-10-01 --end-date 2025-11-26

# Backfill last N days
python backfill_articles.py --days 30

# Dry run (see what would be done without inserting)
python backfill_articles.py --start-date 2025-10-01 --end-date 2025-11-26 --dry-run
```

### Requirements
```bash
pip install pymysql requests beautifulsoup4
```

### Backfill Executed: December 4, 2025

**Date Range**: October 1, 2025 → November 26, 2025

**Results**:
| Metric | Value |
|--------|-------|
| Dates processed | 38 |
| Articles processed | 111 |
| New articles inserted | 111 |
| Skipped (already exist) | 0 |
| Failed to parse | 0 |

**Database Status After Backfill**:
| Metric | Before | After |
|--------|--------|-------|
| Total articles | 20 | **131** |
| Oldest article | Nov 27, 2025 | **Oct 1, 2025** |
| Newest article | Dec 3, 2025 | Dec 3, 2025 |

### Script Features

- **OAuth Authentication**: Uses same cookie-based flow as Kotlin scraper
- **Date Range Filtering**: Only processes dates within specified range
- **Deduplication**: Checks `news_id` before inserting
- **Full Article Parsing**: Fetches HTML, extracts body, removes ruby annotations for plain text
- **Audio URL Generation**: Constructs m3u8 URLs for article narration
- **Progress Logging**: Shows each article being processed
- **Windows Console Support**: Handles Japanese character encoding

### Example Output

```
============================================================
NHK Easy News Backfill
============================================================
Date range: 2025-10-01 to 2025-11-26
Dry run: False
============================================================

[AUTH] Authenticating with NHK...
[AUTH] Authentication successful
[INFO] Found 243 dates in news-list.json
[INFO] 38 dates match the requested range

[DATE] 2025-10-01: 4 articles
  [FETCH] ne2025100112102: 運転免許証　旅行で来た外国人はとることができない...
  [OK] Inserted: 運転免許証　旅行で来た外国人はとることができない
  ...

============================================================
Summary
============================================================
Total articles processed: 111
New articles inserted: 111
Skipped (already exist): 0
Failed to parse: 0
============================================================
```

### When to Use

- **Initial database population**: After fresh Railway deployment
- **Filling gaps**: If scraper missed days due to downtime
- **Historical data**: Loading articles from before Railway migration
- **Testing**: Use `--dry-run` to preview without inserting

### Notes

- NHK's `news-list.json` contains ~243 dates of historical articles
- Articles older than ~8 months may not be available
- Script connects to Railway MySQL via public proxy (`shortline.proxy.rlwy.net:46705`)
- Each article fetch includes a delay to avoid rate limiting

---

**Document Version**: 1.2
**Last Updated**: 2025-12-04
**Maintained By**: Claude + Emmanuel Fabiani
**Contact**: emmanuelfabiani23@gmail.com
