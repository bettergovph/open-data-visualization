#!/usr/bin/env python3
"""
SEC Philippines Check with SEC Windows Automation
Uses AutoHotkey and Edge browser for automation
"""

import subprocess
import os
import time
import json
from datetime import datetime

class WindowsSECSearch:
    def __init__(self):
        self.results = []
        self.log_file = f"sec_search_windows_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
    def log(self, message):
        """Log message to file and console"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    
    def check_ahk_installed(self):
        """Check if AutoHotkey is installed"""
        self.log("🔍 Checking for AutoHotkey installation...")
        
        # Common AutoHotkey installation paths
        ahk_paths = [
            r"C:\Program Files\AutoHotkey\AutoHotkey.exe",
            r"C:\Program Files (x86)\AutoHotkey\AutoHotkey.exe",
            "autohotkey.exe",  # If in PATH
            "ahk.exe"  # If in PATH
        ]
        
        for path in ahk_paths:
            try:
                result = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.log(f"✅ AutoHotkey found at: {path}")
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        self.log("❌ AutoHotkey not found")
        return None
    
    def check_edge_installed(self):
        """Check if Edge browser is installed"""
        self.log("🔍 Checking for Edge browser installation...")
        
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        ]
        
        for path in edge_paths:
            if os.path.exists(path):
                self.log(f"✅ Edge found at: {path}")
                return path
        
        self.log("❌ Edge browser not found")
        return None
    
    def run_ahk_script(self):
        """Run the AutoHotkey script"""
        self.log("🚀 Running AutoHotkey script...")
        
        ahk_path = self.check_ahk_installed()
        if not ahk_path:
            self.log("❌ Cannot run AHK script - AutoHotkey not found")
            return False
        
        ahk_script = "sec_search_edge_ahk.ahk"
        if not os.path.exists(ahk_script):
            self.log(f"❌ AHK script not found: {ahk_script}")
            return False
        
        try:
            # Run the AHK script
            result = subprocess.run([ahk_path, ahk_script], 
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
        except Exception as e:
            self.log(f"❌ AutoHotkey script error: {e}")
            return False
    
    def try_powershell_automation(self):
        """Try PowerShell automation as alternative"""
        self.log("🔧 Trying PowerShell automation...")
        
        powershell_script = """
        # PowerShell script to automate Edge browser
        $companyName = "kench lightyear"
        $secUrl = "https://checkwithsec.sec.gov.ph/check-with-sec/index"
        
        # Launch Edge
        Start-Process "msedge.exe" -ArgumentList "--new-window", $secUrl
        
        # Wait for browser to open
        Start-Sleep -Seconds 5
        
        # Wait for Cloudflare challenge
        Start-Sleep -Seconds 15
        
        # Try to find and interact with search elements
        Add-Type -AssemblyName System.Windows.Forms
        
        # Send keys to the active window
        [System.Windows.Forms.SendKeys]::SendWait($companyName)
        Start-Sleep -Seconds 2
        
        # Try to submit
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Seconds 5
        
        # Take screenshot
        Add-Type -AssemblyName System.Drawing
        $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($screen.Left, $screen.Top, 0, 0, $screen.Size)
        $bitmap.Save("sec_search_powershell_screenshot.png")
        $graphics.Dispose()
        $bitmap.Dispose()
        
        Write-Host "PowerShell automation completed"
        """
        
        try:
            # Save PowerShell script to file
            with open("sec_search_powershell.ps1", "w", encoding="utf-8") as f:
                f.write(powershell_script)
            
            # Run PowerShell script
            result = subprocess.run([
                "powershell.exe", "-ExecutionPolicy", "Bypass", "-File", "sec_search_powershell.ps1"
            ], capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                self.log("✅ PowerShell automation completed successfully")
                return True
            else:
                self.log(f"❌ PowerShell automation failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log("⏰ PowerShell automation timed out")
            return False
        except Exception as e:
            self.log(f"❌ PowerShell automation error: {e}")
            return False
    
    def try_vbs_automation(self):
        """Try VBScript automation as alternative"""
        self.log("🔧 Trying VBScript automation...")
        
        vbs_script = """
        Set objShell = CreateObject("WScript.Shell")
        Set objIE = CreateObject("InternetExplorer.Application")
        
        ' Launch Edge
        objShell.Run "msedge.exe --new-window https://checkwithsec.sec.gov.ph/check-with-sec/index"
        
        ' Wait for browser to open
        WScript.Sleep 5000
        
        ' Wait for Cloudflare challenge
        WScript.Sleep 15000
        
        ' Try to send keys
        objShell.SendKeys "kench lightyear"
        WScript.Sleep 2000
        
        ' Try to submit
        objShell.SendKeys "{ENTER}"
        WScript.Sleep 5000
        
        ' Take screenshot
        objShell.Run "powershell.exe -Command ""Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{PRTSC}')"""
        
        try:
            # Save VBScript to file
            with open("sec_search_vbs.vbs", "w", encoding="utf-8") as f:
                f.write(vbs_script)
            
            # Run VBScript
            result = subprocess.run(["cscript.exe", "sec_search_vbs.vbs"], 
                                  capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                self.log("✅ VBScript automation completed successfully")
                return True
            else:
                self.log(f"❌ VBScript automation failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log("⏰ VBScript automation timed out")
            return False
        except Exception as e:
            self.log(f"❌ VBScript automation error: {e}")
            return False
    
    def run_all_approaches(self):
        """Try all Windows automation approaches"""
        self.log("🏢 SEC Philippines Windows Search Automation")
        self.log("=" * 60)
        
        # Check prerequisites
        edge_path = self.check_edge_installed()
        if not edge_path:
            self.log("❌ Edge browser not found - please install Microsoft Edge")
            return False
        
        approaches = [
            ("AutoHotkey", self.run_ahk_script),
            ("PowerShell", self.try_powershell_automation),
            ("VBScript", self.try_vbs_automation)
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
    automation = WindowsSECSearch()
    success = automation.run_all_approaches()
    
    if success:
        print("\n✅ At least one approach succeeded!")
        print("📁 Check the generated files for results:")
        print("   - sec_search_edge_log.txt")
        print("   - sec_search_edge_results.txt")
        print("   - sec_search_powershell_screenshot.png")
    else:
        print("\n❌ All approaches failed - manual search may be required")
        print("🌐 Manual search URL: https://checkwithsec.sec.gov.ph/check-with-sec/index")

if __name__ == "__main__":
    main()
