"""
Telegram Bot Notifier
Sends notifications to Telegram about price alerts
"""

import requests
from typing import Optional
import time


class TelegramNotifier:
    """Handles sending notifications via Telegram Bot API"""
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize Telegram notifier
        
        Args:
            bot_token: Telegram bot token from BotFather
            chat_id: Telegram chat ID to send messages to
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, text: str, parse_mode: str = "HTML", retries: int = 3) -> bool:
        """
        Send a text message to Telegram with retry logic
        
        Args:
            text: Message text to send
            parse_mode: Parse mode (HTML or Markdown)
            retries: Number of retry attempts
            
        Returns:
            True if successful, False otherwise
        """
        url = f"{self.api_url}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        
        for attempt in range(retries):
            try:
                response = requests.post(url, json=payload, timeout=10)
                
                # Check for rate limiting (429 Too Many Requests)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"Rate limited. Waiting {retry_after} seconds before retry...")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                return True
            except requests.RequestException as e:
                if attempt < retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                    print(f"Error sending Telegram message (attempt {attempt + 1}/{retries}): {e}")
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    print(f"Error sending Telegram message after {retries} attempts: {e}")
                    return False
        
        return False

