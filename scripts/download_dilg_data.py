import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import sys

def download_file(url, dest_folder):
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)
    
    local_filename = os.path.join(dest_folder, url.split('/')[-1])
    
    # Check if file already exists to avoid re-downloading (rudimentary check)
    if os.path.exists(local_filename):
        print(f"File {local_filename} already exists. Skipping.")
        return local_filename

    print(f"Downloading {url} to {local_filename}...")
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
        print(f"Downloaded: {local_filename}")
        return local_filename
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None

def main():
    base_url = "https://archive.org/download/20250914.dilg.barangay/"
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/dilg"))
    
    print(f"Fetching file list from {base_url}...")
    try:
        response = requests.get(base_url)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching URL: {e}")
        sys.exit(1)

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Archive.org directory listings usually have links in a table or list
    # We look for links ending in .xlsx and starting with official-list_
    
    links = soup.find_all('a')
    download_count = 0
    
    for link in links:
        href = link.get('href')
        if href and href.endswith('.xlsx') and href.startswith('official-list_'):
            full_url = urljoin(base_url, href)
            download_file(full_url, output_dir)
            download_count += 1
            
    if download_count == 0:
        print("No matching files found to download.")
    else:
        print(f"Successfully processed {download_count} files.")

if __name__ == "__main__":
    main()
