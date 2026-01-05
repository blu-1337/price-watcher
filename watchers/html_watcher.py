"""
HTML-based price watcher using BeautifulSoup
"""

import requests
from bs4 import BeautifulSoup
import re
from typing import Optional, Dict, Any
from .base import BaseWatcher


class HTMLWatcher(BaseWatcher):
    """Watcher for HTML-based websites using CSS selectors"""
    
    def __init__(self, name: str, url: str, threshold: float, config: Dict[str, Any]):
        """
        Initialize HTML watcher
        
        Args:
            name: Unique name for this watcher
            url: URL to monitor
            threshold: Price threshold (alert if price <= threshold)
            config: Configuration dict with keys:
                - selector: CSS selector for the price element
                - price_index: Index of price to extract from range (0=min, 1=max, default=0)
                - timeout: Request timeout in seconds (None for no timeout, default=None)
                - retries: Number of retry attempts on failure (default=1)
                - user_agent: Optional custom user agent
        """
        super().__init__(name, url, threshold, config)
        self.selector = config.get('selector')
        self.price_index = config.get('price_index', 0)  # 0 = min price, 1 = max price
        
        if not self.selector:
            raise ValueError("CSS selector is required for HTMLWatcher")
        
        # Set up session with realistic browser headers
        self.session = requests.Session()
        user_agent = config.get('user_agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Set comprehensive headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        })
        
        # Timeout configuration - None means no timeout, or specify seconds
        timeout_val = config.get('timeout')
        self.timeout = None if timeout_val is None else timeout_val
        self.retries = config.get('retries', 1)  # Default 1 retry (since no timeout, retries less needed)
    
    def fetch_price(self) -> Optional[float]:
        """Fetch and parse price from HTML with retry logic"""
        import time
        
        for attempt in range(self.retries):
            try:
                if attempt > 0:
                    wait_time = attempt * 2  # Exponential backoff: 2s, 4s, 6s
                    print(f"[{self.name}] Retry attempt {attempt + 1}/{self.retries} after {wait_time}s...")
                    time.sleep(wait_time)
                
                timeout_msg = f"timeout: {self.timeout}s" if self.timeout else "no timeout"
                print(f"[{self.name}] Fetching page: {self.url} ({timeout_msg})")
                response = self.session.get(self.url, timeout=self.timeout)
                response.raise_for_status()
                print(f"[{self.name}] ✓ Page fetched successfully (status: {response.status_code})")
                print(f"[{self.name}] Response size: {len(response.content)} bytes")
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Debug: Show page title to verify we got content
                title = soup.find('title')
                if title:
                    print(f"[{self.name}] Page title: {title.get_text(strip=True)[:100]}")
                
                price_element = soup.select_one(self.selector)
                
                if not price_element:
                    print(f"[{self.name}] ✗ Price element not found with selector: {self.selector}")
                    print(f"[{self.name}] Trying to find alternative elements...")
                    # Try to find any elements with similar classes for debugging
                    all_divs = soup.select('div.mt-auto')
                    if all_divs:
                        print(f"[{self.name}] Found {len(all_divs)} div.mt-auto elements")
                        for idx, div in enumerate(all_divs[:3]):  # Show first 3
                            print(f"[{self.name}]   Element {idx + 1}: {div.get_text(strip=True)[:100]}")
                    return None
                
                # Debug: Show which element was found
                element_tag = price_element.name
                element_classes = ' '.join(price_element.get('class', []))
                element_id = price_element.get('id', '')
                print(f"[{self.name}] ✓ Found price element:")
                print(f"[{self.name}]   Selector used: {self.selector}")
                print(f"[{self.name}]   Element: <{element_tag}>" + 
                      (f' class="{element_classes}"' if element_classes else '') + 
                      (f' id="{element_id}"' if element_id else '') + ">")
                
                # Get raw text including any non-breaking spaces
                raw_text = price_element.get_text()
                print(f"[{self.name}] Raw HTML element text: {repr(raw_text)}")
                
                price_text = price_element.get_text(strip=True)
                print(f"[{self.name}] Text after strip(): {repr(price_text)}")
                
                parsed_price = self._parse_price(price_text)
                return parsed_price
                
            except requests.Timeout as e:
                timeout_str = f"{self.timeout}s" if self.timeout else "timeout"
                error_msg = f"Timeout after {timeout_str}"
                if attempt < self.retries - 1:
                    print(f"[{self.name}] ✗ {error_msg} (attempt {attempt + 1}/{self.retries})")
                else:
                    print(f"[{self.name}] ✗ {error_msg} after {self.retries} attempts")
                    return None
            except requests.RequestException as e:
                if attempt < self.retries - 1:
                    print(f"[{self.name}] ✗ Error fetching page (attempt {attempt + 1}/{self.retries}): {e}")
                else:
                    print(f"[{self.name}] ✗ Error fetching page after {self.retries} attempts: {e}")
                    return None
            except Exception as e:
                print(f"[{self.name}] ✗ Error parsing price: {e}")
                import traceback
                traceback.print_exc()
                return None
        
        return None
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """
        Parse price from text, handling ranges like "147,99€ – 189,99€"
        
        Args:
            price_text: Raw price text from HTML
            
        Returns:
            Parsed price as float, or None if parsing fails
        """
        original_text = price_text
        print(f"[{self.name}] Starting price parsing...")
        print(f"[{self.name}] Input text: {repr(price_text)}")
        
        # Remove non-breaking spaces and normalize
        price_text = price_text.replace('\xa0', ' ').strip()
        if price_text != original_text:
            print(f"[{self.name}] After removing non-breaking spaces: {repr(price_text)}")
        
        # Handle price ranges (e.g., "147,99€ – 189,99€")
        if '–' in price_text or '-' in price_text:
            # Split on range separator
            separator = '–' if '–' in price_text else '-'
            prices = price_text.split(separator)
            print(f"[{self.name}] Detected price range (separator: {repr(separator)})")
            print(f"[{self.name}] Split into {len(prices)} parts: {prices}")
            
            if len(prices) > self.price_index:
                price_text = prices[self.price_index].strip()
                print(f"[{self.name}] Using price index {self.price_index}: {repr(price_text)}")
            else:
                price_text = prices[0].strip()
                print(f"[{self.name}] Price index {self.price_index} not available, using first: {repr(price_text)}")
        else:
            print(f"[{self.name}] No price range detected, using full text")
        
        # Extract numeric value (handles European format: 147,99€)
        # Remove currency symbols and extract numbers
        before_clean = price_text
        price_text = re.sub(r'[^\d\s.,]', '', price_text)
        price_text = price_text.replace(' ', '')
        if price_text != before_clean:
            print(f"[{self.name}] After removing currency symbols: {repr(price_text)}")
        
        # Handle European number format (1.400,50) vs US format (1,400.50)
        if re.search(r',\d{2}$', price_text):
            # European format: 147,99 -> 147.99
            before_format = price_text
            price_text = price_text.replace('.', '').replace(',', '.')
            print(f"[{self.name}] Detected European format (comma as decimal), converted: {repr(before_format)} -> {repr(price_text)}")
        else:
            # Remove dots and commas (they're thousands separators)
            before_format = price_text
            price_text = price_text.replace('.', '').replace(',', '')
            if price_text != before_format:
                print(f"[{self.name}] Removing thousands separators: {repr(before_format)} -> {repr(price_text)}")
        
        # Extract the number
        price_match = re.search(r'(\d+(?:\.\d+)?)', price_text)
        
        if price_match:
            matched_value = price_match.group(1)
            print(f"[{self.name}] Matched number: {repr(matched_value)}")
            try:
                final_price = float(matched_value)
                print(f"[{self.name}] ✓ Successfully parsed price: {final_price}€")
                return final_price
            except ValueError as e:
                print(f"[{self.name}] ✗ Failed to convert to float: {e}")
                return None
        else:
            print(f"[{self.name}] ✗ No number pattern found in: {repr(price_text)}")
            return None
    
    def format_alert_message(self, price: float) -> str:
        """Format alert message for Telegram"""
        return f"""🔔 <b>Price Alert: {self.name}</b>

💰 <b>Price:</b> {price:.2f}€
🎯 <b>Threshold:</b> {self.threshold}€

🔗 <a href="{self.url}">Check Product</a>
"""

