#!/usr/bin/env python3
"""
Alternative SEC Search Automation
Uses less common automation tools to bypass detection
"""

import subprocess
import os
import time
import json
from datetime import datetime

class AlternativeSECSearch:
    def __init__(self):
        self.results = []
        self.log_file = f"sec_search_alternative_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
    def log(self, message):
        """Log message to file and console"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    
    def try_ahk_automation(self):
        """Try AutoHotkey automation"""
        self.log("🚀 Trying AutoHotkey automation...")
        
        ahk_script = "sec_search_ahk.ahk"
        if os.path.exists(ahk_script):
            try:
                # Run AHK script
                result = subprocess.run(['autohotkey', ahk_script], 
                                      capture_output=True, text=True, timeout=120)
                
                if result.returncode == 0:
                    self.log("✅ AutoHotkey script completed successfully")
                    return True
                else:
                    self.log(f"❌ AutoHotkey script failed: {result.stderr}")
                    return False
                    
            except subprocess.TimeoutExpired:
                self.log("⏰ AutoHotkey script timed out")
                return False
            except FileNotFoundError:
                self.log("❌ AutoHotkey not found - trying alternative approach")
                return False
        else:
            self.log("❌ AutoHotkey script not found")
            return False
    
    def try_selenium_stealth(self):
        """Try Selenium with stealth mode"""
        self.log("🕵️ Trying Selenium with stealth mode...")
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            import undetected_chromedriver as uc
            
            # Use undetected-chromedriver
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            driver = uc.Chrome(options=options)
            
            # Execute stealth script
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.log("🌐 Navigating to SEC website...")
            driver.get("https://checkwithsec.sec.gov.ph/check-with-sec/index")
            
            # Wait for Cloudflare challenge
            self.log("⏳ Waiting for Cloudflare challenge...")
            time.sleep(20)
            
            # Try to find search elements
            self.log("🔍 Looking for search elements...")
            
            # Wait for page to load
            WebDriverWait(driver, 30).until(
                lambda d: d.title != "Just a moment..."
            )
            
            # Look for search inputs
            search_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='search'], input[name*='search'], input[name*='company']")
            
            if search_inputs:
                self.log(f"✅ Found {len(search_inputs)} search inputs")
                
                # Try to fill the first input
                search_input = search_inputs[0]
                search_input.clear()
                search_input.send_keys("kench lightyear")
                
                # Try to submit
                search_input.send_keys("\n")
                time.sleep(5)
                
                # Get results
                page_source = driver.page_source
                self.log("📄 Page source captured")
                
                # Save results
                with open("sec_search_selenium_results.html", "w", encoding="utf-8") as f:
                    f.write(page_source)
                
                self.log("✅ Selenium automation completed")
                return True
            else:
                self.log("❌ No search inputs found")
                return False
                
        except ImportError:
            self.log("❌ Required packages not installed: pip install selenium undetected-chromedriver")
            return False
        except Exception as e:
            self.log(f"❌ Selenium automation failed: {e}")
            return False
        finally:
            try:
                driver.quit()
            except:
                pass
    
    def try_requests_session(self):
        """Try requests with session management"""
        self.log("🌐 Trying requests with session management...")
        
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            # Create session with retry strategy
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            # Set realistic headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
            
            # First request to get cookies
            self.log("📡 Making initial request...")
            response = session.get("https://checkwithsec.sec.gov.ph/check-with-sec/index", 
                                 headers=headers, timeout=30)
            
            self.log(f"📊 Response status: {response.status_code}")
            self.log(f"🍪 Cookies received: {len(session.cookies)}")
            
            if response.status_code == 200:
                # Wait a bit and try again
                time.sleep(5)
                
                # Second request with cookies
                response2 = session.get("https://checkwithsec.sec.gov.ph/check-with-sec/index", 
                                      headers=headers, timeout=30)
                
                self.log(f"📊 Second request status: {response2.status_code}")
                
                if "Just a moment" not in response2.text:
                    self.log("✅ Successfully bypassed Cloudflare")
                    
                    # Save the page
                    with open("sec_search_requests_results.html", "w", encoding="utf-8") as f:
                        f.write(response2.text)
                    
                    return True
                else:
                    self.log("⚠️ Still on Cloudflare challenge page")
                    return False
            else:
                self.log(f"❌ Request failed with status {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"❌ Requests automation failed: {e}")
            return False
    
    def try_curl_automation(self):
        """Try curl with different approaches"""
        self.log("🌐 Trying curl automation...")
        
        curl_commands = [
            # Basic curl
            f'curl -s -L "https://checkwithsec.sec.gov.ph/check-with-sec/index" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" -o sec_curl_basic.html',
            
            # Curl with cookies
            f'curl -s -L -c cookies.txt "https://checkwithsec.sec.gov.ph/check-with-sec/index" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" -o sec_curl_cookies.html',
            
            # Curl with referer
            f'curl -s -L -H "Referer: https://sec.gov.ph/" "https://checkwithsec.sec.gov.ph/check-with-sec/index" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" -o sec_curl_referer.html'
        ]
        
        for i, cmd in enumerate(curl_commands, 1):
            self.log(f"🔄 Trying curl approach {i}...")
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    # Check if we got actual content
                    filename = f"sec_curl_{['basic', 'cookies', 'referer'][i-1]}.html"
                    if os.path.exists(filename):
                        with open(filename, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        if "Just a moment" not in content and len(content) > 1000:
                            self.log(f"✅ Curl approach {i} succeeded")
                            return True
                        else:
                            self.log(f"⚠️ Curl approach {i} still shows Cloudflare challenge")
                else:
                    self.log(f"❌ Curl approach {i} failed: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                self.log(f"⏰ Curl approach {i} timed out")
            except Exception as e:
                self.log(f"❌ Curl approach {i} error: {e}")
        
        return False
    
    def run_all_approaches(self):
        """Try all automation approaches"""
        self.log("🏢 SEC Philippines Alternative Search Automation")
        self.log("=" * 60)
        
        approaches = [
            ("AutoHotkey", self.try_ahk_automation),
            ("Selenium Stealth", self.try_selenium_stealth),
            ("Requests Session", self.try_requests_session),
            ("Curl Automation", self.try_curl_automation)
        ]
        
        success_count = 0
        
        for name, method in approaches:
            self.log(f"\n🔄 Trying {name} approach...")
            try:
                if method():
                    self.log(f"✅ {name} approach succeeded")
                    success_count += 1
                else:
                    self.log(f"❌ {name} approach failed")
            except Exception as e:
                self.log(f"❌ {name} approach error: {e}")
            
            time.sleep(2)  # Brief pause between attempts
        
        self.log(f"\n📊 Summary: {success_count}/{len(approaches)} approaches succeeded")
        self.log(f"📁 Check log file: {self.log_file}")
        
        return success_count > 0

def main():
    """Main function"""
    automation = AlternativeSECSearch()
    success = automation.run_all_approaches()
    
    if success:
        print("\n✅ At least one approach succeeded!")
    else:
        print("\n❌ All approaches failed - manual search may be required")

if __name__ == "__main__":
    main()
