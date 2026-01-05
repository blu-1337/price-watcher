# Price Watcher

A modular Python application that monitors multiple websites for price drops and sends Telegram notifications when prices fall below specified thresholds.

## Features

- 🔍 **Modular Design**: Easily add multiple watchers for different websites and products
- 🌐 **HTML-based Watchers**: Monitor any website using CSS selectors
- 📱 **Telegram Notifications**: Get instant alerts when prices drop
- ⚙️ **Configurable**: Simple JSON configuration for all watchers
- 🔄 **GitHub Actions Integration**: Automatic monitoring every 10 minutes
- 💰 **Price Range Support**: Handles price ranges (e.g., "147,99€ – 189,99€") and extracts minimum/maximum prices

## Architecture

The application is designed with modularity in mind:

```
price-watcher/
├── watchers/           # Watcher implementations
│   ├── base.py        # Abstract base class for watchers
│   └── html_watcher.py # HTML/CSS selector-based watcher
├── notifiers/          # Notification modules
│   └── telegram.py     # Telegram bot notifier
├── main.py            # Main script that orchestrates all watchers
├── config.json        # Configuration file (not in git)
└── config.json.example # Example configuration
```

## Requirements

- Python 3.7+
- Internet connection
- Telegram bot token and chat ID

## Installation

1. **Clone or navigate to the repository:**
   ```bash
   cd price-watcher
   ```

2. **Create and activate virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers (if using playwright watcher type):**
   ```bash
   playwright install chromium
   ```

4. **Create configuration file:**
   ```bash
   cp config.json.example config.json
   ```

5. **Edit `config.json`** with your settings (see Configuration section)

## Configuration

The `config.json` file contains your Telegram credentials and watcher configurations:

```json
{
  "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
  "telegram_chat_id": "YOUR_CHAT_ID_HERE",
  "watchers": [
    {
      "name": "Product Name",
      "type": "html",
      "url": "https://example.com/product",
      "threshold": 115.0,
      "config": {
        "selector": "p.oopStage-priceRangeCtaRange",
        "price_index": 0,
        "user_agent": "Mozilla/5.0..."
      }
    }
  ]
}
```

### Configuration Fields

- **telegram_bot_token**: Your Telegram bot token from BotFather
- **telegram_chat_id**: Your Telegram chat ID
- **watchers**: Array of watcher configurations

### Watcher Configuration

Each watcher has the following fields:

- **name**: Unique name for this watcher (used in notifications)
- **type**: Watcher type (currently only "html" is supported)
- **url**: URL of the product/page to monitor
- **threshold**: Price threshold in euros (alert if price <= threshold)
- **config**: Watcher-specific configuration
  - **selector**: CSS selector for the price element (e.g., `"p.oopStage-priceRangeCtaRange"`)
  - **price_index**: For price ranges, which price to use (0 = minimum/first, 1 = maximum/second)
  - **user_agent**: Optional custom user agent string

### Getting Telegram Credentials

**Telegram Bot Token:**
1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow instructions to name your bot
4. Copy the bot token you receive

**Chat ID:**
1. Start a chat with your bot (search for it by name)
2. Send any message to your bot
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find the `chat.id` value in the JSON response

Or use the helper script from the `olx-apartment-search` project:
```bash
python get_chat_id.py
```

## Usage

### Local Testing

**Quick test command (with virtual environment):**

```bash
cd price-watcher
python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt && playwright install chromium && python3 main.py
```

Or step by step:

```bash
# Navigate to directory
cd price-watcher

# Activate virtual environment (if already created)
source .venv/bin/activate

# Install Playwright browsers (if using playwright watcher)
playwright install chromium

# Run the price watcher
python3 main.py
```

The script will:
1. Load all configured watchers
2. Check each website for current prices
3. Compare prices against thresholds
4. Send Telegram notifications for any price alerts

### Adding Multiple Watchers

To monitor multiple products/sites, simply add more entries to the `watchers` array in `config.json`:

```json
{
  "watchers": [
    {
      "name": "Product 1",
      "type": "html",
      "url": "https://site1.com/product1",
      "threshold": 115.0,
      "config": {
        "selector": "span.price",
        "price_index": 0
      }
    },
    {
      "name": "Product 2",
      "type": "html",
      "url": "https://site2.com/product2",
      "threshold": 50.0,
      "config": {
        "selector": "div.product-price",
        "price_index": 0
      }
    }
  ]
}
```

## GitHub Actions Setup

The repository includes a GitHub Actions workflow that runs the price watcher every 10 minutes.

### Setup Steps

1. **Push your code to GitHub** (make sure `config.json` is in `.gitignore`)

2. **Add GitHub Secrets:**
   - Go to your repository on GitHub
   - Navigate to **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**
   - Add the following secrets:
     - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
     - `TELEGRAM_CHAT_ID`: Your Telegram chat ID
     - `WATCHERS_CONFIG`: Your watchers array as a JSON string

   For `WATCHERS_CONFIG`, you need to provide the watchers array as a JSON string. For example:
   ```json
   [{"name":"Product Name","type":"html","url":"https://example.com/product","threshold":115.0,"config":{"selector":"p.oopStage-priceRangeCtaRange","price_index":0}}]
   ```

3. **The workflow will automatically run:**
   - Every 10 minutes (scheduled)
   - Manually via GitHub Actions UI (workflow_dispatch)

### GitHub Secrets Example

If your `config.json` watchers array looks like this:

```json
{
  "watchers": [
    {
      "name": "My Product",
      "type": "html",
      "url": "https://example.com/product",
      "threshold": 115.0,
      "config": {
        "selector": "p.oopStage-priceRangeCtaRange",
        "price_index": 0
      }
    }
  ]
}
```

Then your `WATCHERS_CONFIG` secret should be (as a single-line JSON string):
```
[{"name":"My Product","type":"html","url":"https://example.com/product","threshold":115.0,"config":{"selector":"p.oopStage-priceRangeCtaRange","price_index":0}}]
```

## Price Parsing

The HTML watcher handles various price formats:

- **Single prices**: `"147,99€"` → `147.99`
- **Price ranges**: `"147,99€ – 189,99€"` → `147.99` (when price_index=0) or `189.99` (when price_index=1)
- **European format**: `"1.400,50€"` → `1400.50`
- **US format**: `"1,400.50€"` → `1400.50`

## Extending the System

The modular design makes it easy to add new watcher types:

1. Create a new watcher class in `watchers/` that inherits from `BaseWatcher`
2. Implement the required methods: `fetch_price()` and `format_alert_message()`
3. Update `main.py` to handle your new watcher type in `_create_watcher()`
4. Add your watcher type to the configuration

## Troubleshooting

**No notifications received:**
- Check that `config.json` exists and contains valid credentials
- Verify bot token and chat ID are correct
- Make sure you've sent at least one message to your bot
- Check the URL is correct and accessible

**Price not detected:**
- Verify the CSS selector is correct (use browser DevTools to inspect the element)
- For JavaScript-heavy sites, use `type: "playwright"` instead of `type: "html"`
- Try different `price_index` values if dealing with price ranges
- For Playwright: Increase `wait_time` if content loads slowly

**Playwright installation issues:**
- Make sure you ran `playwright install chromium` after installing requirements
- On Linux, you may need to install system dependencies (GitHub Actions workflow handles this automatically)
- Playwright requires more disk space (~300MB for Chromium browser)

**GitHub Actions not running:**
- Check that secrets are properly configured
- Verify the workflow file is in `.github/workflows/`
- Check GitHub Actions logs for error messages
- Ensure `WATCHERS_CONFIG` is valid JSON

## Files

- `main.py` - Main script that orchestrates all watchers
- `watchers/base.py` - Abstract base class for watchers
- `watchers/html_watcher.py` - HTML/CSS selector-based watcher
- `notifiers/telegram.py` - Telegram notification handler
- `config.json` - Configuration file (not tracked in git)
- `config.json.example` - Example configuration template
- `requirements.txt` - Python dependencies
- `.github/workflows/price-watcher.yml` - GitHub Actions workflow

## Notes

- The script checks prices on each run - it doesn't track historical prices
- Each run will send a notification if the price is below threshold (no duplicate prevention)
- For production use, consider adding a database to track notified prices
- Make sure to respect websites' robots.txt and rate limits

## License

This project is provided as-is for personal use.
