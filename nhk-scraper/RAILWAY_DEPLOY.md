# Deploy NHK Easy API to Railway

## Step 1: Login to Railway

```bash
railway login
```

This will open your browser to authenticate.

## Step 2: Create a New Project

```bash
cd /mnt/c/Users/esfab/WinDevProjects/modal-services/nhk-scraper
railway init
```

Select "Empty Project" and give it a name like "nhk-easy-api"

## Step 3: Add Environment Variables

You already have these from your Railway MySQL database:

```bash
railway variables set MYSQL_HOST=shinkansen.proxy.rlwy.net
railway variables set MYSQL_USER=root
railway variables set MYSQL_PASSWORD=bcbwdqkeRgYgCQNFRWOSuZuRBYskSnES
railway variables set MYSQL_DATABASE=railway
railway variables set MYSQL_PORT=41383
```

## Step 4: Deploy the NHK API Service

Railway doesn't directly support docker-compose, so we'll deploy each service separately:

### Deploy API:
```bash
railway up --service nhk-api --image xiaodanmao/nhk-easy-api:latest
```

### Deploy Scraper Task:
```bash
railway up --service nhk-task --image xiaodanmao/nhk-easy-task:latest
```

## Step 5: Get Your API URL

```bash
railway domain
```

This will give you a URL like: `nhk-api.up.railway.app`

## Testing

Once deployed, test with:
```bash
curl "https://your-app.up.railway.app/news?startDate=2024-12-01T00:00:00.000Z&endDate=2024-12-03T23:59:59.000Z"
```

## Alternative: Use Railway Dashboard

If CLI is complex, you can also:
1. Go to https://railway.app/dashboard
2. Click "New Project"
3. Select "Deploy from Docker Image"
4. Enter: `xiaodanmao/nhk-easy-api:latest`
5. Add your environment variables in the UI
6. Deploy!

Then repeat for the scraper task.
