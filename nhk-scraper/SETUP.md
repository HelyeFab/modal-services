# NHK Easy API Deployment Guide

## Step 1: Create PlanetScale Database (Free)

1. Go to https://planetscale.com and sign up (free tier)
2. Create a new database named `nhk-easy`
3. Get your connection credentials from the dashboard
4. Note down:
   - Host (e.g., `aws.connect.psdb.cloud`)
   - Username
   - Password
   - Database name: `nhk-easy`

## Step 2: Initialize Database Schema

The database needs the nhk-easy schema. We'll do this automatically on first run.

## Step 3: Configure Modal Secrets

Run this command with your PlanetScale credentials:

```bash
modal secret create nhk-database \
  MYSQL_HOST=your-planetscale-host \
  MYSQL_USER=your-username \
  MYSQL_PASSWORD=your-password \
  MYSQL_DATABASE=nhk-easy
```

## Step 4: Deploy to Modal

```bash
cd /mnt/c/Users/esfab/WinDevProjects/modal-services/nhk-scraper
modal deploy deploy_nhk_springboot.py
```

## API Endpoints

After deployment, you'll get:
- NHK News API: `https://[your-workspace]--nhk-easy-api.modal.run/news`
- Health Check: `https://[your-workspace]--nhk-easy-api.modal.run/actuator/health`

## Usage

Fetch articles:
```bash
curl "https://[your-url]/news?startDate=2024-12-01T00:00:00.000Z&endDate=2024-12-03T23:59:59.000Z"
```
