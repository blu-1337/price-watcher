"""
Playwright-based price watcher for JavaScript-heavy websites
"""

from bs4 import BeautifulSoup
import re
from typing import Optional, Dict, Any
from datetime import datetime
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
        
        # For GitHub Actions/CI: use headed mode with xvfb (less detectable than headless)
        # Check if we're in CI environment (GitHub Actions sets CI=true)
        import os
        is_ci = os.environ.get('CI', 'false').lower() == 'true'
        
        if is_ci:
            # In CI, use headed mode (xvfb will provide display) - this avoids headless detection
            self.headless = False
            # Increase wait times for CI environments (more conservative)
            self.wait_time = config.get('wait_time', 10000)  # Default 10s in CI
            self.network_idle_timeout = config.get('network_idle_timeout', 15000)  # 15s for network idle
            print(f"[{self.name}] Detected CI environment, using headed mode with xvfb")
        else:
            self.headless = config.get('headless', True)
            self.wait_time = config.get('wait_time', 5000)  # Default 5s locally
            self.network_idle_timeout = config.get('network_idle_timeout', 10000)  # 10s for network idle
        
        self.page_timeout = config.get('timeout', 30000)
        self.retries = config.get('retries', 3)  # Default 3 retries
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
        """Fetch and parse price using Playwright with retry logic"""
        import time
        
        for attempt in range(self.retries):
            try:
                if attempt > 0:
                    wait_time = attempt * 2  # Exponential backoff: 2s, 4s, 6s
                    print(f"[{self.name}] Retry attempt {attempt + 1}/{self.retries} after {wait_time}s...")
                    time.sleep(wait_time)
                
                result = self._fetch_price_once()
                if result is not None:
                    return result
                else:
                    print(f"[{self.name}] Attempt {attempt + 1}/{self.retries} returned None, will retry...")
            except Exception as e:
                print(f"[{self.name}] Attempt {attempt + 1}/{self.retries} failed: {e}")
                if attempt == self.retries - 1:
                    # Last attempt, re-raise
                    raise
        
        print(f"[{self.name}] All {self.retries} attempts failed to fetch price")
        return None
    
    def _fetch_price_once(self) -> Optional[float]:
        """Single attempt to fetch and parse price using Playwright"""
        try:
            # Detect CI environment for screenshot handling
            import os
            is_ci = os.environ.get('CI', 'false').lower() == 'true' or os.environ.get('GITHUB_ACTIONS', 'false').lower() == 'true'
            screenshot_dir = './screenshots' if is_ci else '/tmp'
            
            # Create screenshots directory if in CI
            if is_ci:
                os.makedirs(screenshot_dir, exist_ok=True)
                print(f"[{self.name}] CI environment detected, screenshots will be saved to {screenshot_dir}/")
            
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
                
                # Network request monitoring and console log monitoring (for debugging in CI)
                network_requests = []
                network_responses = []
                console_messages = []
                price_requests_found = []  # Initialize early for use in logging
                
                if is_ci:
                    # Log all network requests in CI
                    def log_request(request):
                        url = request.url
                        method = request.method
                        network_requests.append({'url': url, 'method': method, 'time': datetime.now().isoformat()})
                        print(f"[{self.name}] [NETWORK] Request: {method} {url[:100]}")
                    
                    def log_response(response):
                        url = response.url
                        status = response.status
                        network_responses.append({'url': url, 'status': status, 'time': datetime.now().isoformat()})
                        print(f"[{self.name}] [NETWORK] Response: {status} {url[:100]}")
                    
                    page.on("request", log_request)
                    page.on("response", log_response)
                    
                    # Capture console messages
                    def log_console(msg):
                        text = msg.text
                        console_messages.append({'text': text, 'type': msg.type, 'time': datetime.now().isoformat()})
                        print(f"[{self.name}] [CONSOLE] {msg.type}: {text[:200]}")
                    
                    page.on("console", log_console)
                
                try:
                    print(f"[{self.name}] Navigating to: {self.url}")
                    
                    # Progressive wait strategy: Wait for multiple load states
                    # Step 1: Wait for DOM content to be loaded
                    print(f"[{self.name}] Step 1: Waiting for DOM content to load...")
                    page.goto(self.url, wait_until='domcontentloaded', timeout=self.page_timeout)
                    print(f"[{self.name}] ✓ DOM content loaded")
                    
                    # Step 2: Wait for full page load
                    print(f"[{self.name}] Step 2: Waiting for full page load...")
                    try:
                        page.wait_for_load_state('load', timeout=10000)
                        print(f"[{self.name}] ✓ Page fully loaded")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Page load timeout: {e}, continuing...")
                    
                    # Step 3: Wait for network to be idle (no requests for 500ms)
                    print(f"[{self.name}] Step 3: Waiting for network to be idle (timeout: {self.network_idle_timeout}ms)...")
                    try:
                        page.wait_for_load_state('networkidle', timeout=self.network_idle_timeout)
                        print(f"[{self.name}] ✓ Network is idle")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Network idle timeout: {e}, continuing anyway...")
                    
                    # Step 4: Additional wait for JavaScript to execute and any delayed requests
                    print(f"[{self.name}] Step 4: Waiting additional 3000ms for JavaScript execution...")
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
                    
                    # Take a screenshot after cookie consent (always in CI, or if not headless locally)
                    try:
                        if is_ci or not self.headless:
                            safe_name = self.name.replace(' ', '_').replace('/', '_')
                            screenshot_path = os.path.join(screenshot_dir, f"{safe_name}_after_cookies.png")
                            page.screenshot(path=screenshot_path, full_page=True)
                            print(f"[{self.name}] ✓ Screenshot saved: {screenshot_path}")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Failed to save screenshot: {e}")
                    
                    # Escape selector for use in JavaScript (needed throughout function)
                    escaped_selector = self.selector.replace("'", "\\'").replace('"', '\\"')
                    
                    # Wait for the specific selector to appear (more reliable than fixed timeout)
                    print(f"[{self.name}] Waiting for price element to appear...")
                    try:
                        page.wait_for_selector(self.selector, timeout=self.wait_time, state='visible')
                        print(f"[{self.name}] ✓ Price element found on page")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Price element not found after waiting: {e}")
                        # Try fallback: use page.evaluate() to check if element exists
                        element_exists = page.evaluate(f"""
                            () => {{
                                const el = document.querySelector('{escaped_selector}');
                                return el !== null;
                            }}
                        """)
                        if not element_exists:
                            print(f"[{self.name}] ✗ Element does not exist in DOM, cannot proceed")
                            return None
                        print(f"[{self.name}] Element exists in DOM but not visible, trying anyway...")
                    
                    # Progressive wait strategy for element content
                    # Step 1: Wait for element to have any text content
                    print(f"[{self.name}] Step 1: Waiting for element to have text content...")
                    try:
                        page.wait_for_function(
                            f"document.querySelector('{escaped_selector}')?.textContent?.trim()",
                            timeout=self.wait_time
                        )
                        print(f"[{self.name}] ✓ Element has text content")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Element text content wait timeout: {e}, checking anyway...")
                        # Fallback: use page.evaluate() to check content directly
                        has_content = page.evaluate(f"""
                            () => {{
                                const el = document.querySelector('{escaped_selector}');
                                return el && el.textContent && el.textContent.trim();
                            }}
                        """)
                        if not has_content:
                            print(f"[{self.name}] ✗ Element has no text content")
                            return None
                    
                    # Step 2: Wait for element to have price-like content (digits and currency)
                    print(f"[{self.name}] Step 2: Waiting for element to have price-like content (digits + currency)...")
                    try:
                        page.wait_for_function(
                            f"""
                            () => {{
                                const el = document.querySelector('{escaped_selector}');
                                if (!el) return false;
                                const text = (el.textContent || el.innerText || '').trim();
                                // Check if text contains price pattern (digits and currency symbol)
                                return /\\d+[,\\.]?\\d*\\s*[€$£]/.test(text);
                            }}
                            """,
                            timeout=self.wait_time
                        )
                        print(f"[{self.name}] ✓ Element has price-like content")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Price pattern wait timeout: {e}, checking anyway...")
                        # Fallback: check if price pattern exists
                        has_price_pattern = page.evaluate(f"""
                            () => {{
                                const el = document.querySelector('{escaped_selector}');
                                if (!el) return false;
                                const text = (el.textContent || el.innerText || '').trim();
                                return /\\d+[,\\.]?\\d*\\s*[€$£]/.test(text);
                            }}
                        """)
                        if not has_price_pattern:
                            print(f"[{self.name}] ⚠ Element text does not match price pattern")
                    
                    # Step 3: Wait for text content to be stable (not changing)
                    print(f"[{self.name}] Step 3: Waiting for element text to stabilize...")
                    try:
                        previous_text = page.evaluate(f"""
                            () => {{
                                const el = document.querySelector('{escaped_selector}');
                                return el ? (el.textContent || el.innerText || '').trim() : '';
                            }}
                        """)
                        page.wait_for_timeout(1000)  # Wait 1 second
                        current_text = page.evaluate(f"""
                            () => {{
                                const el = document.querySelector('{escaped_selector}');
                                return el ? (el.textContent || el.innerText || '').trim() : '';
                            }}
                        """)
                        if previous_text == current_text:
                            print(f"[{self.name}] ✓ Element text is stable")
                        else:
                            print(f"[{self.name}] ⚠ Element text changed: '{previous_text[:50]}' -> '{current_text[:50]}'")
                            # Wait one more time for stability
                            page.wait_for_timeout(2000)
                            final_text = page.evaluate(f"""
                                () => {{
                                    const el = document.querySelector('{escaped_selector}');
                                    return el ? (el.textContent || el.innerText || '').trim() : '';
                                }}
                            """)
                            if current_text == final_text:
                                print(f"[{self.name}] ✓ Element text stabilized after additional wait")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Could not check text stability: {e}")
                    
                    # Try to wait for specific network requests that might load price data
                    # Look for common API endpoints that might contain price information
                    print(f"[{self.name}] Checking for price-related network requests...")
                    price_related_keywords = ['price', 'product', 'api', 'data', 'json', 'ajax']
                    # Clear and repopulate price_requests_found
                    price_requests_found.clear()
                    
                    if is_ci and network_responses:
                        for response in network_responses:
                            url_lower = response['url'].lower()
                            if any(keyword in url_lower for keyword in price_related_keywords):
                                price_requests_found.append(response['url'])
                                print(f"[{self.name}] Found potential price-related request: {response['url'][:100]}")
                    
                    # If we found price-related requests, wait a bit more for them to complete
                    if price_requests_found:
                        print(f"[{self.name}] Waiting additional 2000ms for price-related requests to complete...")
                        page.wait_for_timeout(2000)
                    else:
                        print(f"[{self.name}] No obvious price-related requests found, using standard wait...")
                        page.wait_for_timeout(2000)
                    
                    # Get page URL to check for redirects
                    current_url = page.url
                    print(f"[{self.name}] Current URL: {current_url}")
                    
                    # Enhanced element verification before getting content
                    print(f"[{self.name}] Verifying element visibility and content...")
                    element_locator = page.locator(self.selector)
                    
                    try:
                        is_visible = element_locator.is_visible(timeout=2000)
                        print(f"[{self.name}] Element visibility: {is_visible}")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Could not check visibility: {e}")
                        is_visible = False
                    
                    # Get text content directly from Playwright (more reliable than HTML parsing)
                    try:
                        playwright_text = element_locator.text_content(timeout=2000)
                        if playwright_text and playwright_text.strip():
                            print(f"[{self.name}] ✓ Element text content (from Playwright): {repr(playwright_text[:100])}")
                            # Try parsing directly from Playwright text first
                            parsed_price = self._parse_price(playwright_text.strip())
                            if parsed_price is not None:
                                print(f"[{self.name}] ✓ Successfully parsed price from Playwright text content")
                                return parsed_price
                            else:
                                print(f"[{self.name}] ⚠ Failed to parse Playwright text, falling back to HTML parsing...")
                        else:
                            print(f"[{self.name}] ⚠ Element has no text content from Playwright")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Could not get text content from Playwright: {e}")
                    
                    # Log element's computed style for debugging
                    try:
                        computed_style = page.evaluate(f"""
                            () => {{
                                const el = document.querySelector('{escaped_selector}');
                                if (!el) return null;
                                const style = window.getComputedStyle(el);
                                return {{
                                    display: style.display,
                                    visibility: style.visibility,
                                    opacity: style.opacity,
                                    height: style.height,
                                    width: style.width
                                }};
                            }}
                        """)
                        if computed_style:
                            print(f"[{self.name}] Element computed style: {computed_style}")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Could not get computed style: {e}")
                    
                    # Get page content
                    html_content = page.content()
                    print(f"[{self.name}] ✓ Page loaded successfully")
                    print(f"[{self.name}] 📊 Response size: {len(html_content)} bytes")
                    
                    # Take screenshot after page load (before parsing)
                    try:
                        if is_ci or not self.headless:
                            safe_name = self.name.replace(' ', '_').replace('/', '_')
                            screenshot_path = os.path.join(screenshot_dir, f"{safe_name}_after_load.png")
                            page.screenshot(path=screenshot_path, full_page=True)
                            print(f"[{self.name}] ✓ Screenshot saved: {screenshot_path}")
                    except Exception as e:
                        print(f"[{self.name}] ⚠ Failed to save screenshot: {e}")
                    
                    # Save debugging information in CI
                    if is_ci:
                        try:
                            safe_name = self.name.replace(' ', '_').replace('/', '_')
                            
                            # Save network request logs
                            if network_requests or network_responses:
                                network_log_path = os.path.join(screenshot_dir, f"{safe_name}_network_logs.json")
                                import json
                                network_log = {
                                    'requests': network_requests[-50:],  # Last 50 requests
                                    'responses': network_responses[-50:],  # Last 50 responses
                                    'price_related_requests': price_requests_found
                                }
                                with open(network_log_path, 'w', encoding='utf-8') as f:
                                    json.dump(network_log, f, indent=2, ensure_ascii=False)
                                print(f"[{self.name}] ✓ Network logs saved: {network_log_path}")
                            
                            # Save console logs
                            if console_messages:
                                console_log_path = os.path.join(screenshot_dir, f"{safe_name}_console_logs.json")
                                import json
                                with open(console_log_path, 'w', encoding='utf-8') as f:
                                    json.dump(console_messages, f, indent=2, ensure_ascii=False)
                                print(f"[{self.name}] ✓ Console logs saved: {console_log_path}")
                        except Exception as e:
                            print(f"[{self.name}] ⚠ Failed to save debugging logs: {e}")
                    
                    # Save HTML for debugging (first 2000 chars)
                    print(f"[{self.name}] First 2000 chars of HTML:")
                    print(html_content[:2000])
                    print(f"[{self.name}] " + "="*60)
                    
                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Debug: Show page title (prominent logging)
                    title = soup.find('title')
                    if title:
                        title_text = title.get_text(strip=True)[:100]
                        print(f"[{self.name}] 📄 Page title: {title_text}")
                    else:
                        print(f"[{self.name}] ⚠ No page title found")
                    
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
                        
                        # Fallback: Try using page.evaluate() for direct DOM access
                        print(f"[{self.name}] Attempting fallback: direct DOM access via page.evaluate()...")
                        try:
                            fallback_text = page.evaluate(f"""
                                () => {{
                                    const el = document.querySelector('{escaped_selector}');
                                    if (!el) return null;
                                    return el.textContent || el.innerText || '';
                                }}
                            """)
                            if fallback_text and fallback_text.strip():
                                print(f"[{self.name}] ✓ Found text via page.evaluate(): {repr(fallback_text[:100])}")
                                parsed_price = self._parse_price(fallback_text.strip())
                                if parsed_price is not None:
                                    return parsed_price
                        except Exception as e:
                            print(f"[{self.name}] ⚠ Fallback page.evaluate() failed: {e}")
                        
                        # Take screenshot when element not found (for debugging blocking pages)
                        try:
                            if is_ci or not self.headless:
                                safe_name = self.name.replace(' ', '_').replace('/', '_')
                                screenshot_path = os.path.join(screenshot_dir, f"{safe_name}_element_not_found.png")
                                page.screenshot(path=screenshot_path, full_page=True)
                                print(f"[{self.name}] 📸 Screenshot saved (element not found): {screenshot_path}")
                        except Exception as e:
                            print(f"[{self.name}] ⚠ Failed to save screenshot: {e}")
                        
                        # Save HTML snapshot for debugging
                        try:
                            if is_ci:
                                safe_name = self.name.replace(' ', '_').replace('/', '_')
                                html_path = os.path.join(screenshot_dir, f"{safe_name}_html_snapshot.html")
                                with open(html_path, 'w', encoding='utf-8') as f:
                                    f.write(html_content)
                                print(f"[{self.name}] 📄 HTML snapshot saved: {html_path}")
                        except Exception as e:
                            print(f"[{self.name}] ⚠ Failed to save HTML snapshot: {e}")
                        
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
                    
                    # Enhanced logging if element is empty
                    if not price_text:
                        print(f"[{self.name}] ⚠ Element found but has no text content!")
                        print(f"[{self.name}] Element HTML: {str(price_element)[:200]}")
                        print(f"[{self.name}] Element classes: {price_element.get('class', [])}")
                        print(f"[{self.name}] Element ID: {price_element.get('id', 'N/A')}")
                        
                        # Try fallback: get text via page.evaluate()
                        try:
                            fallback_text = page.evaluate(f"""
                                () => {{
                                    const el = document.querySelector('{escaped_selector}');
                                    if (!el) return null;
                                    return el.textContent || el.innerText || el.innerHTML || '';
                                }}
                            """)
                            if fallback_text and fallback_text.strip():
                                print(f"[{self.name}] ✓ Found text via page.evaluate() fallback: {repr(fallback_text[:100])}")
                                price_text = fallback_text.strip()
                        except Exception as e:
                            print(f"[{self.name}] ⚠ Fallback page.evaluate() failed: {e}")
                    
                    if not price_text:
                        print(f"[{self.name}] ✗ Cannot proceed: element has no text content")
                        # Save HTML snapshot for debugging
                        try:
                            if is_ci:
                                safe_name = self.name.replace(' ', '_').replace('/', '_')
                                html_path = os.path.join(screenshot_dir, f"{safe_name}_empty_element.html")
                                with open(html_path, 'w', encoding='utf-8') as f:
                                    f.write(html_content)
                                print(f"[{self.name}] 📄 HTML snapshot saved (empty element): {html_path}")
                        except Exception as e:
                            print(f"[{self.name}] ⚠ Failed to save HTML snapshot: {e}")
                        return None
                    
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

