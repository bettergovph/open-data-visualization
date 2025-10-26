#!/usr/bin/env python3
"""
Main script to download, extract, analyze, and visualize DPWH archive data
Orchestrates the entire data pipeline
"""

import os
import sys
import subprocess
from pathlib import Path
import time

def run_script(script_name, description):
    """Run a Python script and handle errors"""
    print(f"\n{'='*60}")
    print(f"🚀 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run([sys.executable, script_name], 
                              capture_output=True, text=True, check=True)
        print(result.stdout)
        if result.stderr:
            print("Warnings/Errors:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running {script_name}:")
        print(f"Return code: {e.returncode}")
        print(f"Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ Script {script_name} not found")
        return False

def check_dependencies():
    """Check if required dependencies are installed"""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        'requests', 'pandas', 'matplotlib', 'seaborn', 'plotly', 'numpy'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package}")
    
    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Please install them with: pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies satisfied")
    return True

def main():
    print("🇵🇭 DPWH Archive Data Pipeline")
    print("Department of Public Works and Highways - Philippines")
    print("Internet Archive Collection Analysis")
    
    # Check dependencies
    if not check_dependencies():
        return
    
    # Step 1: Download files
    if not run_script("dpwh_archive_downloader.py", "Downloading DPWH Archive Files"):
        print("❌ Download failed. Please check your internet connection and try again.")
        return
    
    # Check if download was successful
    archive_dir = Path("dpwh_archive")
    zip_files = list(archive_dir.glob("*.zip"))
    
    if len(zip_files) < 31:
        print(f"⚠️  Warning: Only {len(zip_files)} zip files downloaded (expected 31)")
        print("You may want to re-run the download script to get missing files.")
    
    # Step 2: Extract and analyze
    if not run_script("dpwh_archive_analyzer.py", "Extracting and Analyzing Archive Data"):
        print("❌ Analysis failed. Please check the extracted files.")
        return
    
    # Step 3: Create visualizations
    if not run_script("dpwh_data_visualizer.py", "Creating Data Visualizations"):
        print("❌ Visualization failed. Please check the analysis results.")
        return
    
    # Final summary
    print(f"\n{'='*60}")
    print("🎉 DPWH Archive Analysis Complete!")
    print(f"{'='*60}")
    
    # Check outputs
    outputs = {
        "Download Directory": "dpwh_archive/",
        "Extracted Data": "dpwh_archive/extracted/",
        "Analysis Summary": "dpwh_archive/data_summary.json",
        "Visualization Report": "dpwh_analysis_report.html"
    }
    
    print("\n📁 Generated Files:")
    for name, path in outputs.items():
        if Path(path).exists():
            print(f"✅ {name}: {path}")
        else:
            print(f"❌ {name}: {path} (not found)")
    
    print(f"\n🔗 Archive Source: https://archive.org/download/20251016.govph.dpwh.adscurrentarchive.raw/")
    print(f"📊 Open dpwh_analysis_report.html in your browser to view the interactive report")

if __name__ == "__main__":
    main()
