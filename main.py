"""
Price Watcher - Modular price monitoring system
Monitors multiple websites for price drops and sends Telegram notifications
"""

import json
import os
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime

from watchers.html_watcher import HTMLWatcher
from watchers.base import BaseWatcher
from notifiers.telegram import TelegramNotifier

# Try to import PlaywrightWatcher (optional)
try:
    from watchers.playwright_watcher import PlaywrightWatcher
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class PriceWatcherManager:
    """Manages multiple price watchers and coordinates notifications"""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize the price watcher manager
        
        Args:
            config_path: Path to configuration JSON file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.notifier = self._init_notifier()
        self.watchers = self._init_watchers()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        if not os.path.exists(self.config_path):
            print(f"Error: Configuration file '{self.config_path}' not found!")
            print(f"Please create it based on 'config.json.example'")
            sys.exit(1)
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Validate required fields
            if 'telegram_bot_token' not in config or 'telegram_chat_id' not in config:
                print("Error: Configuration must include 'telegram_bot_token' and 'telegram_chat_id'")
                sys.exit(1)
            
            if 'watchers' not in config or not config['watchers']:
                print("Warning: No watchers configured!")
            
            return config
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in configuration file: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading configuration: {e}")
            sys.exit(1)
    
    def _init_notifier(self) -> TelegramNotifier:
        """Initialize Telegram notifier"""
        return TelegramNotifier(
            bot_token=self.config['telegram_bot_token'],
            chat_id=self.config['telegram_chat_id']
        )
    
    def _init_watchers(self) -> List[BaseWatcher]:
        """Initialize all configured watchers"""
        watchers = []
        
        for watcher_config in self.config.get('watchers', []):
            try:
                watcher = self._create_watcher(watcher_config)
                if watcher:
                    watchers.append(watcher)
                    print(f"Initialized watcher: {watcher_config['name']}")
            except Exception as e:
                print(f"Error initializing watcher '{watcher_config.get('name', 'unknown')}': {e}")
        
        return watchers
    
    def _create_watcher(self, config: Dict[str, Any]) -> Optional[BaseWatcher]:
        """
        Create a watcher instance based on configuration
        
        Args:
            config: Watcher configuration dictionary
            
        Returns:
            Watcher instance or None if type is unknown
        """
        watcher_type = config.get('type', '').lower()
        name = config.get('name', 'Unnamed Watcher')
        url = config.get('url', '')
        threshold = float(config.get('threshold', 0))
        watcher_config = config.get('config', {})
        
        if not url or url == 'YOUR_URL_HERE':
            print(f"Warning: Watcher '{name}' has invalid URL. Skipping.")
            return None
        
        if watcher_type == 'html':
            return HTMLWatcher(name, url, threshold, watcher_config)
        elif watcher_type == 'playwright':
            if not PLAYWRIGHT_AVAILABLE:
                print(f"Error: Playwright is not available for '{name}'. Install with: pip install playwright && playwright install chromium")
                return None
            return PlaywrightWatcher(name, url, threshold, watcher_config)
        else:
            print(f"Warning: Unknown watcher type '{watcher_type}' for '{name}'. Skipping.")
            return None
    
    def run(self):
        """Run all watchers and send notifications for price alerts"""
        # Send test message in CI environment to verify Telegram connectivity
        is_ci = os.environ.get('CI', 'false').lower() == 'true' or os.environ.get('GITHUB_ACTIONS', 'false').lower() == 'true'
        if is_ci:
            print(f"\n{'='*60}")
            print("CI Environment Detected - Sending Telegram Test Message")
            print(f"{'='*60}\n")
            test_message = f"""🧪 <b>Price Watcher Test Message</b>

✅ Telegram connectivity test from GitHub Actions
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔧 Environment: CI/GitHub Actions

This is a test message to verify that Telegram notifications are working correctly."""
            success = self.notifier.send_message(test_message)
            if success:
                print("✓ Test message sent successfully to Telegram")
            else:
                print("✗ Failed to send test message to Telegram")
            print()
        
        if not self.watchers:
            print("No watchers configured. Exiting.")
            return
        
        print(f"\n{'='*60}")
        print(f"Price Watcher - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        alerts = []
        
        for watcher in self.watchers:
            print(f"\nChecking: {watcher.name}")
            print(f"URL: {watcher.url}")
            
            try:
                alert = watcher.check_price()
                if alert:
                    alerts.append({
                        'watcher_name': watcher.name,
                        **alert
                    })
                    print(f"✓ Price alert triggered: {alert['price']}€ (threshold: {watcher.threshold}€)")
                else:
                    # The check_price method already prints the price, so we just confirm it's above threshold
                    pass
            except Exception as e:
                print(f"✗ Error checking price: {e}")
                import traceback
                traceback.print_exc()
        
        # Send notifications
        if alerts:
            print(f"\n{'='*60}")
            print(f"Found {len(alerts)} price alert(s)! Sending notifications...")
            print(f"{'='*60}\n")
            
            for alert in alerts:
                success = self.notifier.send_message(alert['message'])
                if success:
                    print(f"✓ Sent alert for {alert['watcher_name']}")
                else:
                    print(f"✗ Failed to send alert for {alert['watcher_name']}")
        else:
            print(f"\n{'='*60}")
            print("No price alerts. All prices are above thresholds.")
            print(f"{'='*60}\n")


def main():
    """Main entry point"""
    config_path = os.environ.get('CONFIG_PATH', 'config.json')
    manager = PriceWatcherManager(config_path)
    manager.run()


if __name__ == "__main__":
    main()

