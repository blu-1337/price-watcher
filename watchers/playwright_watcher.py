"""
Playwright-based price watcher for JavaScript-heavy websites
"""

from bs4 import BeautifulSoup
import re
from typing import Optional, Dict, Any
from .base import BaseWatcher


class PlaywrightWatcher(BaseWatcher):
    """Watcher for JavaScript-heavy websites using Playwright"""
    
    def __init__(self, name: str, url: str, threshold: float, config: Dict[str, Any]):
        """
        Initialize Playwright watcher
        
        Args:
            name: Unique name for this watcher
            url: URL to monitor
            threshold: Price threshold (alert if price <= threshold)
            config: Configuration dict with keys:
                - selector: CSS selector for the price element
                - price_index: Index of price to extract from range (0=min, 1=max, default=0)
                - wait_time: Time to wait for page to load in ms (default=5000)
                - timeout: Page timeout in ms (default=30000)
                - headless: Run in headless mode (default=True)
                - cookie_selector: Optional custom selector for cookie consent button
        """
        super().__init__(name, url, threshold, config)
        self.selector = config.get('selector')
        self.price_index = config.get('price_index', 0)
        self.wait_time = config.get('wait_time', 5000)
        self.page_timeout = config.get('timeout', 30000)
        
        # For GitHub Actions/CI: use headed mode with xvfb (less detectable than headless)
        # Check if we're in CI environment (GitHub Actions sets CI=true)
        import os
        is_ci = os.environ.get('CI', 'false').lower() == 'true'
        
        if is_ci:
            # In CI, use headed mode (xvfb will provide display) - this avoids headless detection
            self.headless = False
            print(f"[{self.name}] Detected CI environment, using headed mode with xvfb")
        else:
            self.headless = config.get('headless', True)
        
        self.cookie_selector = config.get('cookie_selector')  # Optional custom cookie selector
        
        if not self.selector:
            raise ValueError("CSS selector is required for PlaywrightWatcher")
        
        # Import playwright (will fail if not installed)
        try:
            from playwright.sync_api import sync_playwright
            self.sync_playwright = sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Install it with: "
                "pip install playwright && playwright install chromium"
            )
    
    def fetch_price(self) -> Optional[float]:
        """Fetch and parse price using Playwright"""
        try:
            print(f"[{self.name}] Starting Playwright browser (headless={self.headless})...")
            
            with self.sync_playwright() as p:
                # Launch browser with more realistic settings to avoid detection
                browser_args = [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
                
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=browser_args
                )
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='de-DE',
                    timezone_id='Europe/Berlin',
                    extra_http_headers={
                        'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0',
                    },
                    java_script_enabled=True,
                )
                page = context.new_page()
                
                # Remove webdriver traces (anti-detection)
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    window.navigator.chrome = {
                        runtime: {},
                    };
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5],
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['de-DE', 'de', 'en'],
                    });
                """)
                
                try:
                    print(f"[{self.name}] Navigating to: {self.url}")
                    # Use domcontentloaded for faster initial load, then wait for content
                    page.goto(self.url, wait_until='domcontentloaded', timeout=self.page_timeout)
                    
                    # Wait for JavaScript to execute and content to load
                    page.wait_for_timeout(3000)
                    
                    # Handle cookie consent popup (common on German/EU sites)
                    print(f"[{self.name}] Checking for cookie consent popup...")
                    
                    # Use custom selector if provided, otherwise try common patterns
                    if self.cookie_selector:
                        cookie_selectors = [self.cookie_selector]
                    else:
                        cookie_selectors = [
                            'button:has-text("Annehmen")',
                            'button:has-text("Accept")',
                            'button:has-text("Akzeptieren")',
                            'button:has-text("Alle akzeptieren")',
                            'button:has-text("Accept all")',
                            '[data-testid*="accept"]',
                            '[id*="accept"]',
                            '[class*="accept"]',
                            'button[class*="cookie"]',
                            'button[class*="consent"]',
                            'button[aria-label*="accept" i]',
                            'button[aria-label*="annehmen" i]',
                            '//button[contains(text(), "Annehmen")]',  # XPath fallback
                            '//button[contains(text(), "Accept")]'
                        ]
                    
                    cookie_clicked = False
                    for selector in cookie_selectors:
                        try:
                            if selector.startswith('//'):
                                # XPath selector
                                cookie_button = page.locator(selector).first
                            else:
                                cookie_button = page.locator(selector).first
                            
                            if cookie_button.is_visible(timeout=3000):
                                print(f"[{self.name}] Found cookie consent button with selector: {selector}")
                                cookie_button.click()
                                page.wait_for_timeout(2000)  # Wait for popup to close and page to reload
                                cookie_clicked = True
                                print(f"[{self.name}] ✓ Cookie consent accepted")
                                break
                        except Exception as e:
                            continue
                    
                    if not cookie_clicked:
                        print(f"[{self.name}] No cookie consent popup found (or already accepted)")
                    
                    # Take a screenshot for debugging (save to file if not headless, or just log in headless)
                    try:
                        if not self.headless:
                            screenshot_path = f"/tmp/{self.name.replace(' ', '_')}_screenshot.png"
                            page.screenshot(path=screenshot_path, full_page=True)
                            print(f"[{self.name}] Screenshot saved to: {screenshot_path}")
                    except Exception as e:
                        pass
                    
                    # Wait for the specific selector to appear (more reliable than fixed timeout)
                    print(f"[{self.name}] Waiting for price element to appear...")
                    try:
                        page.wait_for_selector(self.selector, timeout=self.wait_time)
                        print(f"[{self.name}] ✓ Price element found on page")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Price element not found after waiting, trying anyway...")
                    
                    # Additional wait for any dynamic content
                    print(f"[{self.name}] Waiting additional {self.wait_time}ms for content to stabilize...")
                    page.wait_for_timeout(self.wait_time)
                    
                    # Get page URL to check for redirects
                    current_url = page.url
                    print(f"[{self.name}] Current URL: {current_url}")
                    
                    # Get page content
                    html_content = page.content()
                    print(f"[{self.name}] ✓ Page loaded successfully")
                    print(f"[{self.name}] Response size: {len(html_content)} bytes")
                    
                    # Save HTML for debugging (first 2000 chars)
                    print(f"[{self.name}] First 2000 chars of HTML:")
                    print(html_content[:2000])
                    print(f"[{self.name}] " + "="*60)
                    
                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Debug: Show page title
                    title = soup.find('title')
                    if title:
                        print(f"[{self.name}] Page title: {title.get_text(strip=True)[:100]}")
                    
                    # Debug: Check for common blocking indicators
                    body_text = soup.find('body')
                    if body_text:
                        body_text_lower = body_text.get_text().lower()
                        if 'captcha' in body_text_lower or 'blocked' in body_text_lower or 'access denied' in body_text_lower:
                            print(f"[{self.name}] ⚠ Possible blocking detected in page content")
                    
                    # Debug: Show all div.mt-auto elements
                    all_mt_auto = soup.select('div.mt-auto')
                    print(f"[{self.name}] Found {len(all_mt_auto)} div.mt-auto elements")
                    for idx, div in enumerate(all_mt_auto[:5]):  # Show first 5
                        text = div.get_text(strip=True)[:150]
                        classes = ' '.join(div.get('class', []))
                        print(f"[{self.name}]   Element {idx + 1} classes: {classes}")
                        print(f"[{self.name}]   Element {idx + 1} text: {text}")
                    
                    # Debug: Show all elements with text-orange-500 class
                    orange_divs = soup.select('div.text-orange-500, .text-orange-500')
                    print(f"[{self.name}] Found {len(orange_divs)} elements with text-orange-500 class")
                    for idx, div in enumerate(orange_divs[:5]):
                        text = div.get_text(strip=True)[:150]
                        print(f"[{self.name}]   Orange element {idx + 1}: {text}")
                    
                    # Debug: Look for any price-like patterns
                    all_text = soup.get_text()
                    import re
                    price_patterns = re.findall(r'\d+[,.]\d+\s*€', all_text)
                    if price_patterns:
                        print(f"[{self.name}] Found price-like patterns in page: {price_patterns[:10]}")
                    
                    # Find price element
                    price_element = soup.select_one(self.selector)
                    
                    if not price_element:
                        print(f"[{self.name}] ✗ Price element not found with selector: {self.selector}")
                        print(f"[{self.name}] Trying to find alternative elements...")
                        # Try to find any elements with similar classes for debugging
                        all_divs = soup.select('div.mt-auto')
                        if all_divs:
                            print(f"[{self.name}] Found {len(all_divs)} div.mt-auto elements")
                            for idx, div in enumerate(all_divs[:3]):
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
                    
                    # Get raw text
                    raw_text = price_element.get_text()
                    print(f"[{self.name}] Raw HTML element text: {repr(raw_text)}")
                    
                    price_text = price_element.get_text(strip=True)
                    print(f"[{self.name}] Text after strip(): {repr(price_text)}")
                    
                    parsed_price = self._parse_price(price_text)
                    return parsed_price
                    
                finally:
                    browser.close()
                    
        except Exception as e:
            print(f"[{self.name}] ✗ Error with Playwright: {e}")
            import traceback
            traceback.print_exc()
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

