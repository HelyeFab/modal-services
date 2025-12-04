# NHK Easy API Auth Proxy

Adds API key authentication to the NHK Easy API on Railway.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NHK_API_KEY` | API key for authentication (same as Modal services) |
| `UPSTREAM_URL` | Internal URL of nhk-easy-api (default: `http://nhk-easy-api.railway.internal:8080`) |

## Endpoints

- `GET /health` - Health check (no auth)
- `GET /news?startDate=...&endDate=...` - Get articles (requires `X-API-Key` header)

## Usage

```bash
curl -H "X-API-Key: YOUR_KEY" \
  "https://nhk-api-proxy-production.up.railway.app/news?startDate=2025-12-01T00:00:00.000Z&endDate=2025-12-03T23:59:59.000Z"
```

## Deploy

```bash
cd nhk-api-railway
railway link  # Link to existing project
railway up    # Deploy
```
