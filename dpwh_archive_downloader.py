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
    
    # Archive URLs - both collections
    archive_urls = {
        "collection1": "https://archive.org/download/20251016.govph.dpwh.adscurrentarchive.raw/",
        "collection2": "https://archive.org/download/20251016.govph.dpwh.adscurrentarchive.raw.02/"
    }
    
    # Files to download from both collections
    files_to_download = [
        # Collection 1 files (001-031)
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.001.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.002.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.003.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.004.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.005.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.006.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.007.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.008.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.009.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.010.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.011.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.012.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.013.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.014.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.015.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.016.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.017.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.018.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.019.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.020.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.021.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.022.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.023.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.024.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.025.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.026.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.027.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.028.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.029.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.030.zip"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw.031.zip"),
        # Collection 1 metadata files
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw_archive.torrent"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw_files.xml"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw_meta.sqlite"),
        ("collection1", "20251016.govph.dpwh.adscurrentarchive.raw_meta.xml"),
        
        # Collection 2 files (032-042)
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.032.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.033.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.034.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.035.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.036.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.037.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.038.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.039.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.040.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.041.zip"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.042.zip"),
        # Collection 2 metadata files
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.02_archive.torrent"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.02_files.xml"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.02_meta.sqlite"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.02_meta.xml"),
        ("collection2", "20251016.govph.dpwh.adscurrentarchive.raw.meta.map.zip")
    ]
    
    print(f"Starting download of {len(files_to_download)} files from both collections...")
    print(f"Download directory: {download_dir.absolute()}")
    print(f"Collection 1: {archive_urls['collection1']}")
    print(f"Collection 2: {archive_urls['collection2']}")
    
    successful_downloads = 0
    failed_downloads = []
    
    for i, (collection, filename) in enumerate(files_to_download, 1):
        file_path = download_dir / filename
        base_url = archive_urls[collection]
        url = urljoin(base_url, filename)
        
        # Overwrite existing files to avoid conflicts
        if file_path.exists():
            file_size = file_path.stat().st_size / (1024 * 1024)  # Size in MB
            print(f"Overwriting {filename} (existing file: {file_size:.2f} MB)")
        
        print(f"\n[{i}/{len(files_to_download)}] Downloading {filename} from {collection}")
        
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
