#!/usr/bin/env python3
"""
Extract and crawl DPWH archive files
Analyzes the structure and content of the downloaded archive
"""

import os
import zipfile
import sqlite3
import xml.etree.ElementTree as ET
import json
import pandas as pd
from pathlib import Path
import shutil
from collections import defaultdict, Counter
import re

def extract_zip_files(archive_dir):
    """Extract all zip files in the archive directory"""
    archive_path = Path(archive_dir)
    extract_dir = archive_path / "extracted"
    extract_dir.mkdir(exist_ok=True)
    
    zip_files = list(archive_path.glob("*.zip"))
    print(f"Found {len(zip_files)} zip files to extract")
    
    extracted_count = 0
    for zip_file in zip_files:
        print(f"Extracting {zip_file.name}...")
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            extracted_count += 1
            print(f"✓ Extracted {zip_file.name}")
        except Exception as e:
            print(f"✗ Error extracting {zip_file.name}: {e}")
    
    print(f"Successfully extracted {extracted_count} zip files")
    return extract_dir

def analyze_file_structure(extract_dir):
    """Analyze the structure of extracted files"""
    extract_path = Path(extract_dir)
    
    print(f"\nAnalyzing file structure in {extract_path}")
    
    # Get all files recursively
    all_files = list(extract_path.rglob("*"))
    files = [f for f in all_files if f.is_file()]
    directories = [f for f in all_files if f.is_dir()]
    
    print(f"Total files: {len(files)}")
    print(f"Total directories: {len(directories)}")
    
    # Analyze file extensions
    extensions = Counter()
    file_sizes = defaultdict(list)
    
    for file_path in files:
        ext = file_path.suffix.lower()
        extensions[ext] += 1
        
        try:
            size = file_path.stat().st_size
            file_sizes[ext].append(size)
        except:
            pass
    
    print(f"\nFile extensions found:")
    for ext, count in extensions.most_common(20):
        avg_size = sum(file_sizes[ext]) / len(file_sizes[ext]) if file_sizes[ext] else 0
        print(f"  {ext or '(no extension)'}: {count} files (avg size: {avg_size/1024:.1f} KB)")
    
    return {
        'total_files': len(files),
        'total_dirs': len(directories),
        'extensions': dict(extensions),
        'file_sizes': dict(file_sizes)
    }

def analyze_metadata_files(archive_dir):
    """Analyze the metadata files"""
    archive_path = Path(archive_dir)
    
    print(f"\nAnalyzing metadata files...")
    
    # Analyze meta.xml
    meta_xml = archive_path / "20251016.govph.dpwh.adscurrentarchive.raw_meta.xml"
    if meta_xml.exists():
        print(f"Found meta.xml: {meta_xml.stat().st_size} bytes")
        try:
            tree = ET.parse(meta_xml)
            root = tree.getroot()
            print(f"XML root tag: {root.tag}")
            print(f"XML attributes: {root.attrib}")
        except Exception as e:
            print(f"Error parsing meta.xml: {e}")
    
    # Analyze files.xml
    files_xml = archive_path / "20251016.govph.dpwh.adscurrentarchive.raw_files.xml"
    if files_xml.exists():
        print(f"Found files.xml: {files_xml.stat().st_size} bytes")
        try:
            tree = ET.parse(files_xml)
            root = tree.getroot()
            print(f"Files XML root tag: {root.tag}")
            print(f"Files XML children: {len(root)}")
        except Exception as e:
            print(f"Error parsing files.xml: {e}")
    
    # Analyze meta.sqlite
    meta_sqlite = archive_path / "20251016.govph.dpwh.adscurrentarchive.raw_meta.sqlite"
    if meta_sqlite.exists():
        print(f"Found meta.sqlite: {meta_sqlite.stat().st_size} bytes")
        try:
            conn = sqlite3.connect(meta_sqlite)
            cursor = conn.cursor()
            
            # Get table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"SQLite tables: {[t[0] for t in tables]}")
            
            # Analyze each table
            for table in tables:
                table_name = table[0]
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"  {table_name}: {count} rows")
            
            conn.close()
        except Exception as e:
            print(f"Error analyzing meta.sqlite: {e}")

def sample_data_files(extract_dir, sample_size=10):
    """Sample and analyze some data files"""
    extract_path = Path(extract_dir)
    
    print(f"\nSampling data files...")
    
    # Find common data file types
    data_extensions = ['.csv', '.json', '.xml', '.txt', '.xlsx', '.xls', '.pdf']
    sample_files = []
    
    for ext in data_extensions:
        files = list(extract_path.rglob(f"*{ext}"))
        if files:
            sample_files.extend(files[:sample_size])
    
    print(f"Found {len(sample_files)} sample files to analyze")
    
    for file_path in sample_files[:5]:  # Analyze first 5 files
        print(f"\nAnalyzing: {file_path.name}")
        print(f"Size: {file_path.stat().st_size} bytes")
        
        try:
            if file_path.suffix.lower() == '.csv':
                # Try to read CSV
                df = pd.read_csv(file_path, nrows=5)
                print(f"CSV columns: {list(df.columns)}")
                print(f"CSV shape: {df.shape}")
                
            elif file_path.suffix.lower() == '.json':
                # Try to read JSON
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        print(f"JSON keys: {list(data.keys())}")
                    elif isinstance(data, list):
                        print(f"JSON array length: {len(data)}")
                        
            elif file_path.suffix.lower() in ['.txt', '.xml']:
                # Read first few lines
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = [f.readline().strip() for _ in range(3)]
                    print(f"First lines: {lines}")
                    
        except Exception as e:
            print(f"Error analyzing {file_path.name}: {e}")

def create_data_summary(archive_dir, extract_dir, analysis_results):
    """Create a comprehensive data summary"""
    summary = {
        'archive_info': {
            'source': 'Internet Archive - DPWH Philippines',
            'archive_date': '2025-10-16',
            'total_size_gb': '~60GB',
            'zip_files': 31
        },
        'extraction_results': analysis_results,
        'file_types': analysis_results['extensions'],
        'total_files': analysis_results['total_files'],
        'total_directories': analysis_results['total_dirs']
    }
    
    # Save summary
    summary_file = Path(archive_dir) / "data_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nData summary saved to: {summary_file}")
    return summary

def main():
    archive_dir = "dpwh_archive"
    
    if not Path(archive_dir).exists():
        print(f"Archive directory {archive_dir} not found. Please run download script first.")
        return
    
    print("Starting DPWH archive analysis...")
    
    # Extract zip files
    extract_dir = extract_zip_files(archive_dir)
    
    # Analyze file structure
    analysis_results = analyze_file_structure(extract_dir)
    
    # Analyze metadata files
    analyze_metadata_files(archive_dir)
    
    # Sample data files
    sample_data_files(extract_dir)
    
    # Create summary
    summary = create_data_summary(archive_dir, extract_dir, analysis_results)
    
    print(f"\n{'='*50}")
    print("Analysis Complete!")
    print(f"Extracted files to: {extract_dir}")
    print(f"Total files processed: {summary['total_files']}")
    print(f"File types found: {len(summary['file_types'])}")

if __name__ == "__main__":
    main()
