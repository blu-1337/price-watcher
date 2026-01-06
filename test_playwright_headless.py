#!/usr/bin/env python3
"""
Test script to diagnose Playwright headless vs headed mode differences
Tests the same URL/selector in both modes and compares results
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from playwright.sync_api import sync_playwright, Page, Browser


class TestRunner:
    """Runs Playwright tests in different modes and captures diagnostics"""
    
    def __init__(self, url: str, selector: str, output_dir: str = "test_artifacts"):
        self.url = url
        self.selector = selector
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize data structures
        self.network_requests = []
        self.network_responses = []
        self.console_messages = []
        self.test_results = {}
    
    def log_request(self, request):
        """Log network request"""
        self.network_requests.append({
            'url': request.url,
            'method': request.method,
            'time': datetime.now().isoformat()
        })
        print(f"  [NETWORK] Request: {request.method} {request.url[:80]}")
    
    def log_response(self, response):
        """Log network response"""
        self.network_responses.append({
            'url': response.url,
            'status': response.status,
            'time': datetime.now().isoformat()
        })
        print(f"  [NETWORK] Response: {response.status} {response.url[:80]}")
    
    def log_console(self, msg):
        """Log console message"""
        self.console_messages.append({
            'text': msg.text,
            'type': msg.type,
            'time': datetime.now().isoformat()
        })
        if msg.type in ['error', 'warning']:
            print(f"  [CONSOLE] {msg.type.upper()}: {msg.text[:200]}")
    
    def run_test(self, mode: str, headless: bool) -> Dict[str, Any]:
        """Run a single test in specified mode"""
        print(f"\n{'='*80}")
        print(f"Testing in {mode.upper()} mode (headless={headless})")
        print(f"{'='*80}\n")
        
        # Reset data structures
        self.network_requests = []
        self.network_responses = []
        self.console_messages = []
        
        mode_dir = self.output_dir / mode
        mode_dir.mkdir(exist_ok=True)
        
        result = {
            'mode': mode,
            'headless': headless,
            'url': self.url,
            'selector': self.selector,
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'price': None,
            'errors': [],
            'warnings': [],
            'element_state': {},
            'wait_results': {},
            'artifacts': {}
        }
        
        try:
            with sync_playwright() as p:
                # Launch browser
                print(f"[{mode}] Launching browser (headless={headless})...")
                browser = p.chromium.launch(
                    headless=headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                    ]
                )
                
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='de-DE',
                    timezone_id='Europe/Berlin',
                )
                
                page = context.new_page()
                
                # Set up monitoring
                page.on("request", self.log_request)
                page.on("response", self.log_response)
                page.on("console", self.log_console)
                
                # Anti-detection script
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
                
                # Test navigation
                print(f"[{mode}] Navigating to: {self.url}")
                try:
                    page.goto(self.url, wait_until='domcontentloaded', timeout=60000)
                    result['wait_results']['domcontentloaded'] = True
                    print(f"[{mode}] ✓ DOM content loaded")
                    
                    # Save screenshot after initial load
                    screenshot_path = mode_dir / "01_after_dom_load.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    result['artifacts']['screenshot_01_dom'] = str(screenshot_path)
                    
                    # Save HTML after DOM load
                    html_path = mode_dir / "01_after_dom_load.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(page.content())
                    result['artifacts']['html_01_dom'] = str(html_path)
                    
                except Exception as e:
                    result['wait_results']['domcontentloaded'] = False
                    result['errors'].append(f"DOM load failed: {str(e)}")
                    print(f"[{mode}] ✗ DOM load failed: {e}")
                
                # Wait for load state
                print(f"[{mode}] Waiting for page load...")
                try:
                    page.wait_for_load_state('load', timeout=10000)
                    result['wait_results']['load'] = True
                    print(f"[{mode}] ✓ Page loaded")
                except Exception as e:
                    result['wait_results']['load'] = False
                    result['warnings'].append(f"Load timeout: {str(e)}")
                    print(f"[{mode}] ⚠ Load timeout: {e}")
                
                # Wait for network idle
                print(f"[{mode}] Waiting for network idle...")
                try:
                    page.wait_for_load_state('networkidle', timeout=15000)
                    result['wait_results']['networkidle'] = True
                    print(f"[{mode}] ✓ Network idle")
                except Exception as e:
                    result['wait_results']['networkidle'] = False
                    result['warnings'].append(f"Network idle timeout: {str(e)}")
                    print(f"[{mode}] ⚠ Network idle timeout: {e}")
                
                # Additional wait
                print(f"[{mode}] Waiting additional 3000ms for JavaScript...")
                page.wait_for_timeout(3000)
                
                # Save screenshot after full load
                screenshot_path = mode_dir / "02_after_full_load.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                result['artifacts']['screenshot_02_full'] = str(screenshot_path)
                
                # Save HTML after full load
                html_path = mode_dir / "02_after_full_load.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(page.content())
                result['artifacts']['html_02_full'] = str(html_path)
                
                # Check element existence
                print(f"[{mode}] Checking element: {self.selector}")
                escaped_selector = self.selector.replace("'", "\\'").replace('"', '\\"')
                
                element_exists = page.evaluate(f"""
                    () => {{
                        const el = document.querySelector('{escaped_selector}');
                        return el !== null;
                    }}
                """)
                result['element_state']['exists'] = element_exists
                print(f"[{mode}] Element exists: {element_exists}")
                
                if not element_exists:
                    result['errors'].append("Element does not exist in DOM")
                    print(f"[{mode}] ✗ Element not found!")
                else:
                    # Check visibility
                    try:
                        element_locator = page.locator(self.selector)
                        is_visible = element_locator.is_visible(timeout=2000)
                        result['element_state']['visible'] = is_visible
                        print(f"[{mode}] Element visible: {is_visible}")
                    except Exception as e:
                        result['element_state']['visible'] = False
                        result['warnings'].append(f"Visibility check failed: {str(e)}")
                        print(f"[{mode}] ⚠ Visibility check failed: {e}")
                    
                    # Get text content
                    try:
                        text_content = element_locator.text_content(timeout=2000)
                        result['element_state']['has_text'] = bool(text_content and text_content.strip())
                        result['element_state']['text_content'] = text_content[:200] if text_content else None
                        print(f"[{mode}] Element text: {repr(text_content[:100]) if text_content else 'None'}")
                    except Exception as e:
                        result['element_state']['has_text'] = False
                        result['warnings'].append(f"Text content check failed: {str(e)}")
                        print(f"[{mode}] ⚠ Text content check failed: {e}")
                    
                    # Wait for selector
                    print(f"[{mode}] Waiting for selector to be visible...")
                    try:
                        page.wait_for_selector(self.selector, timeout=10000, state='visible')
                        result['wait_results']['selector_visible'] = True
                        print(f"[{mode}] ✓ Selector is visible")
                    except Exception as e:
                        result['wait_results']['selector_visible'] = False
                        result['warnings'].append(f"Selector wait failed: {str(e)}")
                        print(f"[{mode}] ⚠ Selector wait failed: {e}")
                    
                    # Wait for text content
                    print(f"[{mode}] Waiting for element to have text...")
                    try:
                        page.wait_for_function(
                            f"document.querySelector('{escaped_selector}')?.textContent?.trim()",
                            timeout=10000
                        )
                        result['wait_results']['has_text'] = True
                        print(f"[{mode}] ✓ Element has text")
                    except Exception as e:
                        result['wait_results']['has_text'] = False
                        result['warnings'].append(f"Text wait failed: {str(e)}")
                        print(f"[{mode}] ⚠ Text wait failed: {e}")
                    
                    # Wait for price pattern
                    print(f"[{mode}] Waiting for price pattern...")
                    try:
                        page.wait_for_function(
                            f"""
                            () => {{
                                const el = document.querySelector('{escaped_selector}');
                                if (!el) return false;
                                const text = (el.textContent || el.innerText || '').trim();
                                return /\\d+[,\\.]?\\d*\\s*[€$£]/.test(text);
                            }}
                            """,
                            timeout=10000
                        )
                        result['wait_results']['price_pattern'] = True
                        print(f"[{mode}] ✓ Price pattern found")
                    except Exception as e:
                        result['wait_results']['price_pattern'] = False
                        result['warnings'].append(f"Price pattern wait failed: {str(e)}")
                        print(f"[{mode}] ⚠ Price pattern wait failed: {e}")
                    
                    # Final screenshot
                    screenshot_path = mode_dir / "03_final.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    result['artifacts']['screenshot_03_final'] = str(screenshot_path)
                    
                    # Final HTML
                    html_path = mode_dir / "03_final.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(page.content())
                    result['artifacts']['html_03_final'] = str(html_path)
                    
                    # Try to parse price
                    if text_content:
                        # Simple price parsing (same as watcher)
                        import re
                        price_text = text_content.strip()
                        price_text = re.sub(r'[^\d\s.,]', '', price_text)
                        price_text = price_text.replace(' ', '')
                        if re.search(r',\d{2}$', price_text):
                            price_text = price_text.replace('.', '').replace(',', '.')
                        else:
                            price_text = price_text.replace('.', '').replace(',', '')
                        price_match = re.search(r'(\d+(?:\.\d+)?)', price_text)
                        if price_match:
                            try:
                                result['price'] = float(price_match.group(1))
                                result['success'] = True
                                print(f"[{mode}] ✓ Price parsed: {result['price']}€")
                            except ValueError:
                                result['errors'].append("Failed to convert price to float")
                        else:
                            result['errors'].append("No price pattern found in text")
                    else:
                        result['errors'].append("No text content to parse")
                
                # Save network logs
                network_log_path = mode_dir / "network_logs.json"
                with open(network_log_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'requests': self.network_requests[-50:],
                        'responses': self.network_responses[-50:],
                    }, f, indent=2, ensure_ascii=False)
                result['artifacts']['network_logs'] = str(network_log_path)
                
                # Save console logs
                console_log_path = mode_dir / "console_logs.json"
                with open(console_log_path, 'w', encoding='utf-8') as f:
                    json.dump(self.console_messages, f, indent=2, ensure_ascii=False)
                result['artifacts']['console_logs'] = str(console_log_path)
                
                browser.close()
        
        except Exception as e:
            result['errors'].append(f"Test failed: {str(e)}")
            import traceback
            result['errors'].append(traceback.format_exc())
            print(f"[{mode}] ✗ Test failed: {e}")
        
        return result
    
    def compare_results(self, headed_result: Dict, headless_result: Dict) -> Dict[str, Any]:
        """Compare results from headed and headless modes"""
        comparison = {
            'timestamp': datetime.now().isoformat(),
            'differences': [],
            'summary': {}
        }
        
        # Compare success
        comparison['summary']['headed_success'] = headed_result.get('success', False)
        comparison['summary']['headless_success'] = headless_result.get('success', False)
        
        # Compare prices
        headed_price = headed_result.get('price')
        headless_price = headless_result.get('price')
        comparison['summary']['headed_price'] = headed_price
        comparison['summary']['headless_price'] = headless_price
        
        if headed_price != headless_price:
            comparison['differences'].append({
                'type': 'price_mismatch',
                'headed': headed_price,
                'headless': headless_price
            })
        
        # Compare element state
        headed_state = headed_result.get('element_state', {})
        headless_state = headless_result.get('element_state', {})
        
        for key in ['exists', 'visible', 'has_text']:
            if headed_state.get(key) != headless_state.get(key):
                comparison['differences'].append({
                    'type': f'element_{key}',
                    'headed': headed_state.get(key),
                    'headless': headless_state.get(key)
                })
        
        # Compare text content
        headed_text = headed_state.get('text_content', '')
        headless_text = headless_state.get('text_content', '')
        if headed_text != headless_text:
            comparison['differences'].append({
                'type': 'text_content_mismatch',
                'headed': headed_text[:200],
                'headless': headless_text[:200]
            })
        
        # Compare wait results
        headed_waits = headed_result.get('wait_results', {})
        headless_waits = headless_result.get('wait_results', {})
        
        for key in ['domcontentloaded', 'load', 'networkidle', 'selector_visible', 'has_text', 'price_pattern']:
            if headed_waits.get(key) != headless_waits.get(key):
                comparison['differences'].append({
                    'type': f'wait_{key}',
                    'headed': headed_waits.get(key),
                    'headless': headless_waits.get(key)
                })
        
        # Compare errors
        if headed_result.get('errors') != headless_result.get('errors'):
            comparison['differences'].append({
                'type': 'errors_different',
                'headed_errors': headed_result.get('errors', []),
                'headless_errors': headless_result.get('errors', [])
            })
        
        # Compare network requests count
        headed_requests = len(headed_result.get('artifacts', {}).get('network_logs', []))
        headless_requests = len(headless_result.get('artifacts', {}).get('network_logs', []))
        # Actually, we need to load the network logs to compare
        # For now, just note if counts are very different
        
        return comparison
    
    def generate_report(self, headed_result: Dict, headless_result: Dict, comparison: Dict):
        """Generate a human-readable comparison report"""
        report_path = self.output_dir / "comparison_report.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("PLAYWRIGHT HEADLESS vs HEADED MODE COMPARISON REPORT\n")
            f.write("="*80 + "\n\n")
            
            f.write("SUMMARY\n")
            f.write("-"*80 + "\n")
            f.write(f"Headed Mode Success: {headed_result.get('success', False)}\n")
            f.write(f"Headless Mode Success: {headless_result.get('success', False)}\n")
            f.write(f"Headed Price: {headed_result.get('price', 'N/A')}\n")
            f.write(f"Headless Price: {headless_result.get('price', 'N/A')}\n\n")
            
            f.write("ELEMENT STATE COMPARISON\n")
            f.write("-"*80 + "\n")
            headed_state = headed_result.get('element_state', {})
            headless_state = headless_result.get('element_state', {})
            f.write(f"Element Exists - Headed: {headed_state.get('exists')}, Headless: {headless_state.get('exists')}\n")
            f.write(f"Element Visible - Headed: {headed_state.get('visible')}, Headless: {headless_state.get('visible')}\n")
            f.write(f"Has Text - Headed: {headed_state.get('has_text')}, Headless: {headless_state.get('has_text')}\n")
            f.write(f"Headed Text: {headed_state.get('text_content', 'N/A')}\n")
            f.write(f"Headless Text: {headless_state.get('text_content', 'N/A')}\n\n")
            
            f.write("WAIT RESULTS COMPARISON\n")
            f.write("-"*80 + "\n")
            headed_waits = headed_result.get('wait_results', {})
            headless_waits = headless_result.get('wait_results', {})
            for key in ['domcontentloaded', 'load', 'networkidle', 'selector_visible', 'has_text', 'price_pattern']:
                f.write(f"{key}: Headed={headed_waits.get(key)}, Headless={headless_waits.get(key)}\n")
            f.write("\n")
            
            f.write("DIFFERENCES FOUND\n")
            f.write("-"*80 + "\n")
            if comparison.get('differences'):
                for diff in comparison['differences']:
                    f.write(f"Type: {diff['type']}\n")
                    f.write(f"  Headed: {diff.get('headed')}\n")
                    f.write(f"  Headless: {diff.get('headless')}\n\n")
            else:
                f.write("No significant differences found.\n\n")
            
            f.write("ERRORS AND WARNINGS\n")
            f.write("-"*80 + "\n")
            f.write("Headed Errors:\n")
            for error in headed_result.get('errors', []):
                f.write(f"  - {error}\n")
            f.write("\nHeadless Errors:\n")
            for error in headless_result.get('errors', []):
                f.write(f"  - {error}\n")
            f.write("\nHeaded Warnings:\n")
            for warning in headed_result.get('warnings', []):
                f.write(f"  - {warning}\n")
            f.write("\nHeadless Warnings:\n")
            for warning in headless_result.get('warnings', []):
                f.write(f"  - {warning}\n")
        
        print(f"\n{'='*80}")
        print(f"Report saved to: {report_path}")
        print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description='Test Playwright in headed vs headless mode')
    parser.add_argument('--url', type=str, help='URL to test')
    parser.add_argument('--selector', type=str, help='CSS selector for price element')
    parser.add_argument('--config', type=str, default='config.json', help='Config file to read from')
    parser.add_argument('--output', type=str, default='test_artifacts', help='Output directory for artifacts')
    parser.add_argument('--mode', type=str, choices=['both', 'headed', 'headless'], default='both',
                       help='Which mode(s) to test')
    
    args = parser.parse_args()
    
    # Load from config if URL/selector not provided
    if not args.url or not args.selector:
        if os.path.exists(args.config):
            with open(args.config, 'r') as f:
                config = json.load(f)
            watchers = config.get('watchers', [])
            if watchers:
                watcher = watchers[0]  # Use first watcher
                args.url = args.url or watcher.get('url')
                args.selector = args.selector or watcher.get('config', {}).get('selector')
    
    if not args.url or not args.selector:
        print("Error: URL and selector are required. Provide via --url/--selector or config file.")
        sys.exit(1)
    
    print(f"Testing URL: {args.url}")
    print(f"Selector: {args.selector}")
    print(f"Output directory: {args.output}\n")
    
    runner = TestRunner(args.url, args.selector, args.output)
    
    results = {}
    
    # Run headed test
    if args.mode in ['both', 'headed']:
        results['headed'] = runner.run_test('headed', headless=False)
    
    # Run headless test
    if args.mode in ['both', 'headless']:
        results['headless'] = runner.run_test('headless', headless=True)
    
    # Compare if both were run
    if 'headed' in results and 'headless' in results:
        comparison = runner.compare_results(results['headed'], results['headless'])
        
        # Save comparison JSON
        comparison_path = runner.output_dir / "comparison.json"
        with open(comparison_path, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)
        
        # Generate report
        runner.generate_report(results['headed'], results['headless'], comparison)
        
        # Print summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Headed Mode: {'✓ SUCCESS' if results['headed'].get('success') else '✗ FAILED'}")
        if results['headed'].get('price'):
            print(f"  Price: {results['headed']['price']}€")
        print(f"Headless Mode: {'✓ SUCCESS' if results['headless'].get('success') else '✗ FAILED'}")
        if results['headless'].get('price'):
            print(f"  Price: {results['headless']['price']}€")
        print(f"\nDifferences found: {len(comparison.get('differences', []))}")
        print(f"Full report: {runner.output_dir / 'comparison_report.txt'}")
        print("="*80 + "\n")


if __name__ == "__main__":
    main()

