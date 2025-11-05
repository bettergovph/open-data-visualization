#!/usr/bin/env python3
"""
Process all pd*.jpg images in the database folder using OCR
and write results to senators-relationships.json
"""

import json
import os
import glob
from pathlib import Path
from PIL import Image
import pytesseract

def process_images_with_ocr(database_dir="database", output_file="senators-relationships.json"):
    """
    Process all pd*.jpg files in the database directory using OCR
    and save results to JSON file
    """
    database_path = Path(database_dir)
    output_path = Path(output_file)
    
    # Find all pd*.jpg files
    image_files = sorted(glob.glob(str(database_path / "pd*.jpg")))
    
    if not image_files:
        print(f"No pd*.jpg files found in {database_dir}")
        return
    
    print(f"Found {len(image_files)} image files to process")
    
    # Load existing data if file exists
    existing_data = {}
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            print(f"Loaded existing data with {len(existing_data)} entries")
        except json.JSONDecodeError:
            print("Warning: Existing file is not valid JSON, starting fresh")
            existing_data = {}
    
    # Process each image
    results = {}
    for image_file in image_files:
        filename = os.path.basename(image_file)
        print(f"Processing {filename}...")
        
        try:
            # Open and process image with OCR
            image = Image.open(image_file)
            text = pytesseract.image_to_string(image, lang='eng')
            
            # Clean up the text (remove excessive whitespace)
            text = text.strip()
            
            results[filename] = text
            print(f"  ✓ Extracted {len(text)} characters from {filename}")
            
        except Exception as e:
            print(f"  ✗ Error processing {filename}: {e}")
            # Keep existing data if available, otherwise use empty string
            results[filename] = existing_data.get(filename, "")
    
    # Write results to JSON file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Successfully processed {len(results)} images")
    print(f"✓ Results written to {output_file}")

if __name__ == "__main__":
    process_images_with_ocr()

