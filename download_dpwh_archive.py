#!/usr/bin/env python3
"""
Download script for DPWH archive from Internet Archive
Downloads all zip files from the collection
"""

import os
import requests
import time
from urllib.parse import urljoin
from pathlib import Path

def download_file(url, filename, chunk_size=8192):
    """Download a file with progress tracking"""
    print(f"Downloading {filename}...")
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        print(f"\rProgress: {progress:.1f}% ({downloaded}/{total_size} bytes)", end='', flush=True)
        
        print(f"\n✓ Downloaded {filename}")
        return True
        
    except Exception as e:
        print(f"\n✗ Error downloading {filename}: {e}")
        return False

def main():
    # Create download directory
    download_dir = Path("dpwh_archive")
    download_dir.mkdir(exist_ok=True)
    
    # Base URL for the archive (corrected collection path)
    base_url = "https://archive.org/download/20251016.govph.dpwh.adscurrentarchive.raw.02/"
    
    # List of files to download from the new collection
    files_to_download = [
        # Zip files from the new collection (032-042)
        "20251016.govph.dpwh.adscurrentarchive.raw.032.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.033.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.034.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.035.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.036.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.037.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.038.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.039.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.040.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.041.zip",
        "20251016.govph.dpwh.adscurrentarchive.raw.042.zip",
        # Additional metadata files
        "20251016.govph.dpwh.adscurrentarchive.raw.02_archive.torrent",
        "20251016.govph.dpwh.adscurrentarchive.raw.02_files.xml",
        "20251016.govph.dpwh.adscurrentarchive.raw.02_meta.sqlite",
        "20251016.govph.dpwh.adscurrentarchive.raw.02_meta.xml",
        "20251016.govph.dpwh.adscurrentarchive.raw.meta.map.zip"
    ]
    
    print(f"Starting download of {len(files_to_download)} files...")
    print(f"Download directory: {download_dir.absolute()}")
    print(f"Collection URL: {base_url}")
    
    successful_downloads = 0
    failed_downloads = []
    
    for i, filename in enumerate(files_to_download, 1):
        file_path = download_dir / filename
        url = urljoin(base_url, filename)
        
        # Skip if file already exists
        if file_path.exists():
            file_size = file_path.stat().st_size / (1024 * 1024)  # Size in MB
            print(f"Skipping {filename} (already exists, {file_size:.2f} MB)")
            successful_downloads += 1
            continue
        
        print(f"\n[{i}/{len(files_to_download)}] Downloading {filename}")
        
        if download_file(url, file_path):
            successful_downloads += 1
        else:
            failed_downloads.append(filename)
        
        # Small delay between downloads to be respectful
        time.sleep(1)
    
    print(f"\n{'='*50}")
    print(f"Download Summary:")
    print(f"✓ Successful: {successful_downloads}")
    print(f"✗ Failed: {len(failed_downloads)}")
    
    if failed_downloads:
        print(f"\nFailed downloads:")
        for filename in failed_downloads:
            print(f"  - {filename}")
    
    print(f"\nFiles saved to: {download_dir.absolute()}")

if __name__ == "__main__":
    main()
