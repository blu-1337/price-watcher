# GitHub Actions Setup Guide

This guide will help you set up the price watcher to run automatically on GitHub Actions every 10 minutes.

## Prerequisites

- A GitHub repository (you can create one if you don't have it)
- Your Telegram bot token and chat ID
- Your watchers configuration ready

## Step 1: Push Code to GitHub

1. Initialize git repository (if not already done):
   ```bash
   cd price-watcher
   git init
   git add .
   git commit -m "Initial commit: Price watcher setup"
   ```

2. Create a repository on GitHub and push:
   ```bash
   git remote add origin <your-github-repo-url>
   git branch -M main
   git push -u origin main
   ```

## Step 2: Configure GitHub Secrets

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**

### Add TELEGRAM_BOT_TOKEN

- **Name**: `TELEGRAM_BOT_TOKEN`
- **Value**: Your Telegram bot token (e.g., `8252139378:AAHWUJHNe8K8eEkL5zOMse7TBA93aD3J3HE`)
- Click **Add secret**

### Add TELEGRAM_CHAT_ID

- **Name**: `TELEGRAM_CHAT_ID`
- **Value**: Your Telegram chat ID (e.g., `1728975541`)
- Click **Add secret**

### Add WATCHERS_CONFIG

First, prepare your watchers configuration:

1. Make sure your local `config.json` has the correct watcher configurations (with actual URLs, not "YOUR_URL_HERE")

2. Generate the JSON string for the secret:
   ```bash
   python3 generate_watchers_secret.py
   ```
   
   This will output a JSON string like:
   ```
   [{"name":"Product Price Watcher","type":"html","url":"https://example.com/product","threshold":115.0,"config":{"selector":"p.oopStage-priceRangeCtaRange","price_index":0}}]
   ```

3. Copy the entire JSON string (the output between the "=" lines)

4. Go back to GitHub Secrets and add:
   - **Name**: `WATCHERS_CONFIG`
   - **Value**: Paste the JSON string you copied
   - Click **Add secret**

**Important**: The WATCHERS_CONFIG value must be valid JSON. Make sure there are no extra spaces or line breaks when copying.

## Step 3: Verify Workflow

1. Go to the **Actions** tab in your GitHub repository
2. You should see the "Price Watcher" workflow
3. The workflow will run:
   - Every 10 minutes automatically (scheduled)
   - Manually via "Run workflow" button (workflow_dispatch)

4. To test manually:
   - Click on "Price Watcher" workflow
   - Click "Run workflow" → "Run workflow"
   - Wait for it to complete and check the logs

## Step 4: Monitor Results

- Check the workflow runs in the **Actions** tab
- If prices drop below thresholds, you'll receive Telegram notifications
- Check workflow logs if something goes wrong

## Updating Watchers Configuration

If you need to add or modify watchers:

1. Update your local `config.json`
2. Run `python3 generate_watchers_secret.py` to get the new JSON string
3. Go to GitHub Secrets → `WATCHERS_CONFIG` → Update
4. Paste the new JSON string

## Troubleshooting

**Workflow fails with "Invalid JSON":**
- Make sure WATCHERS_CONFIG is valid JSON (use the helper script)
- Check for trailing commas or syntax errors
- Ensure URLs are properly quoted

**No notifications received:**
- Check workflow logs for errors
- Verify bot token and chat ID are correct
- Make sure you've sent a message to your bot first
- Verify the URLs in your watchers config are accessible

**Price not detected:**
- Check workflow logs for error messages
- Verify CSS selectors are correct
- Test locally first: `python3 main.py`

**Workflow not running automatically:**
- GitHub Actions free tier has some limitations on scheduled workflows
- Workflows may be delayed during high load
- Check GitHub Actions status page if schedules seem delayed

## Example WATCHERS_CONFIG Value

For a single watcher monitoring one product:

```json
[{"name":"Product Price Watcher","type":"html","url":"https://example.com/product","threshold":115.0,"config":{"selector":"p.oopStage-priceRangeCtaRange","price_index":0,"user_agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}}]
```

For multiple watchers:

```json
[{"name":"Product 1","type":"html","url":"https://site1.com/product1","threshold":115.0,"config":{"selector":"p.price","price_index":0}},{"name":"Product 2","type":"html","url":"https://site2.com/product2","threshold":50.0,"config":{"selector":"div.product-price","price_index":0}}]
```

