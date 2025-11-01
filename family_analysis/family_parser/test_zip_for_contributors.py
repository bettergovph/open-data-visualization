#!/usr/bin/env python3
"""
Simple test script to check if COMELEC ZIP files contain contributor information
"""

import zipfile
import os
import glob
from pdf2image import convert_from_path
import pytesseract
import pdfplumber
import re

def test_zip_file(zip_path):
    """Test a ZIP file to see if it contains contributor information"""
    print(f"\n📦 Testing: {os.path.basename(zip_path)}")
    print(f"   Size: {os.path.getsize(zip_path) / (1024*1024):.2f} MB")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            pdf_files = [f for f in zip_ref.namelist() if f.lower().endswith('.pdf')]
            
            if not pdf_files:
                print(f"   ⚠️  No PDF files found in ZIP")
                return
            
            print(f"   📄 Found {len(pdf_files)} PDF files")
            
            # Test with just the first PDF
            if pdf_files:
                test_pdf = pdf_files[0]
                print(f"\n   📋 Testing first PDF: {os.path.basename(test_pdf)}")
                
                # Extract to memory (or temp)
                import tempfile
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_ref.extract(test_pdf, temp_dir)
                    pdf_path = os.path.join(temp_dir, test_pdf)
                    
                    # Try regular text extraction first
                    text = ""
                    try:
                        with pdfplumber.open(pdf_path) as pdf:
                            for page in pdf.pages:
                                page_text = page.extract_text()
                                if page_text:
                                    text += page_text + "\n"
                    except:
                        pass
                    
                    # If no text, try OCR
                    if not text or len(text.strip()) < 100:
                        print(f"      🔍 Attempting OCR...")
                        try:
                            images = convert_from_path(pdf_path, dpi=200)
                            for img in images:
                                ocr_text = pytesseract.image_to_string(img, lang='eng')
                                text += ocr_text + "\n"
                        except Exception as e:
                            print(f"      ⚠️  OCR error: {e}")
                    
                    print(f"      📖 Extracted {len(text)} characters of text")
                    
                    # Look for contributor-related keywords
                    text_upper = text.upper()
                    keywords = {
                        'CONTRIBUTOR': text_upper.count('CONTRIBUTOR'),
                        'DONOR': text_upper.count('DONOR'),
                        'CONTRIBUTION': text_upper.count('CONTRIBUTION'),
                        'DONATION': text_upper.count('DONATION'),
                        'RECEIVED': text_upper.count('RECEIVED'),
                        'STATEMENT': text_upper.count('STATEMENT'),
                        'EXPENDITURE': text_upper.count('EXPENDITURE'),
                    }
                    
                    print(f"\n      📊 Keyword analysis:")
                    found_contributor_keywords = False
                    for keyword, count in keywords.items():
                        if count > 0:
                            print(f"         {keyword}: {count}")
                            if keyword in ['CONTRIBUTOR', 'DONOR', 'CONTRIBUTION', 'DONATION']:
                                found_contributor_keywords = True
                    
                    # Look for potential contributor names
                    lines = text.split('\n')
                    potential_names = []
                    for line in lines:
                        line = line.strip()
                        # Look for lines with 2-4 capitalized words
                        words = line.split()
                        if 2 <= len(words) <= 4:
                            if all(w[0].isupper() if w else False for w in words if w and len(w) > 1):
                                if not any(x in line.upper() for x in ['TOTAL', 'PHP', 'PESO', 'INTRAMUROS', 'MANILA', 'COMMISSION', 'REPUBLIC']):
                                    if len(line) > 5:
                                        potential_names.append(line)
                    
                    print(f"\n      👥 Potential contributor names found: {len(potential_names)}")
                    if potential_names:
                        print(f"      📋 First 10 names:")
                        for name in potential_names[:10]:
                            print(f"         - {name}")
                    else:
                        print(f"      ⚠️  No contributor names detected")
                        print(f"      💡 This PDF may only contain summary totals, not detailed contributor lists")
                    
                    # Show a sample of the text
                    print(f"\n      📄 Sample text (first 500 chars):")
                    print(f"         {text[:500].replace(chr(10), ' ')}")
                    
                    return found_contributor_keywords and len(potential_names) > 0
                    
    except zipfile.BadZipFile:
        print(f"   ❌ ZIP file appears incomplete or corrupted")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    """Find and test COMELEC ZIP files"""
    zip_files = glob.glob('database/*comelec*.zip')
    zip_files.extend(glob.glob('database/*COMELEC*.zip'))
    
    # Filter out directories
    valid_zips = [zf for zf in zip_files if os.path.isfile(zf)]
    
    if not valid_zips:
        print("❌ No COMELEC ZIP files found")
        return
    
    # Sort by size (largest first, likely most complete)
    valid_zips.sort(key=lambda x: os.path.getsize(x), reverse=True)
    
    print(f"📦 Found {len(valid_zips)} COMELEC ZIP files")
    print(f"   Testing the largest file (likely most complete)")
    
    # Test the first (largest) one
    if valid_zips:
        result = test_zip_file(valid_zips[0])
        
        if result:
            print(f"\n✅ Found contributor information in ZIP file!")
        else:
            print(f"\n⚠️  No contributor information detected")
            print(f"   The PDFs may contain only summary totals, not detailed contributor lists")

if __name__ == "__main__":
    main()


