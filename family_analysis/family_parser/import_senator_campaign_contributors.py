#!/usr/bin/env python3
"""
Import Campaign Contributors from Senator PDFs
Scans 2025_SENATOR*.pdf files and adds "Campaign Contributor" relationships
Uses OCR for image-based PDFs and identifies COMELEC officials separately
"""

import asyncio
import asyncpg
import os
import re
import glob
import zipfile
import tempfile
import pandas as pd
from typing import Dict, List, Optional, Set, Tuple
from dotenv import load_dotenv
import pdfplumber

try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️  OCR libraries not available. Install with: pip install pytesseract pdf2image Pillow")

# Load environment variables
load_dotenv()

class SenatorCampaignContributorImporter:
    def __init__(self):
        self.db_conn = None
        self.campaign_contributor_type_id = None
        self.comelec_chairman_type_id = None
        self.comelec_commissioner_type_id = None
        self.comelec_officer_type_id = None
        self.processed_files = 0
        self.total_names_found = 0
        self.matched_people = 0
        self.added_contributors = 0
        self.added_comelec_officials = 0
        self.comelec_names = set()
        
    async def connect(self):
        """Connect to the dynasty database"""
        self.db_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu'),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        print("✅ Connected to dynasty database")
        
    async def close(self):
        """Close database connection"""
        if self.db_conn:
            await self.db_conn.close()
            print("✅ Database connection closed")
    
    async def ensure_connection_types(self):
        """Ensure all required connection types exist"""
        # Campaign Contributor
        existing = await self.db_conn.fetchrow("""
            SELECT id, code FROM connection_types 
            WHERE name = 'Campaign Contributor' OR name ILIKE '%campaign contributor%'
        """)
        
        if existing:
            self.campaign_contributor_type_id = existing['id']
            print(f"✅ Found 'Campaign Contributor' type (ID: {existing['id']})")
        else:
            max_code = await self.db_conn.fetchval("SELECT MAX(code) FROM connection_types") or 0
            new_code = max_code + 1
            self.campaign_contributor_type_id = await self.db_conn.fetchval("""
                INSERT INTO connection_types (code, name, description)
                VALUES ($1, $2, $3)
                RETURNING id
            """, new_code, 'Campaign Contributor', 'Campaign contributor or donor to political candidate')
            print(f"✅ Created 'Campaign Contributor' type (ID: {self.campaign_contributor_type_id})")
        
        # COMELEC Chairman
        existing = await self.db_conn.fetchrow("""
            SELECT id, code FROM connection_types 
            WHERE name ILIKE '%comelec%chairman%' OR name ILIKE '%chairman%comelec%'
        """)
        
        if existing:
            self.comelec_chairman_type_id = existing['id']
            print(f"✅ Found 'COMELEC Chairman' type (ID: {existing['id']})")
        else:
            max_code = await self.db_conn.fetchval("SELECT MAX(code) FROM connection_types") or 0
            new_code = max_code + 1
            self.comelec_chairman_type_id = await self.db_conn.fetchval("""
                INSERT INTO connection_types (code, name, description)
                VALUES ($1, $2, $3)
                RETURNING id
            """, new_code, 'COMELEC Chairman', 'Chairman of the Commission on Elections')
            print(f"✅ Created 'COMELEC Chairman' type (ID: {self.comelec_chairman_type_id})")
        
        # COMELEC Commissioner
        existing = await self.db_conn.fetchrow("""
            SELECT id, code FROM connection_types 
            WHERE name ILIKE '%comelec%commissioner%' OR name ILIKE '%commissioner%comelec%'
        """)
        
        if existing:
            self.comelec_commissioner_type_id = existing['id']
            print(f"✅ Found 'COMELEC Commissioner' type (ID: {existing['id']})")
        else:
            max_code = await self.db_conn.fetchval("SELECT MAX(code) FROM connection_types") or 0
            new_code = max_code + 1
            self.comelec_commissioner_type_id = await self.db_conn.fetchval("""
                INSERT INTO connection_types (code, name, description)
                VALUES ($1, $2, $3)
                RETURNING id
            """, new_code, 'COMELEC Commissioner', 'Commissioner of the Commission on Elections')
            print(f"✅ Created 'COMELEC Commissioner' type (ID: {self.comelec_commissioner_type_id})")
        
        # COMELEC Officer (generic)
        existing = await self.db_conn.fetchrow("""
            SELECT id, code FROM connection_types 
            WHERE name ILIKE '%comelec%officer%' OR name ILIKE '%officer%comelec%'
        """)
        
        if existing:
            self.comelec_officer_type_id = existing['id']
            print(f"✅ Found 'COMELEC Officer' type (ID: {existing['id']})")
        else:
            max_code = await self.db_conn.fetchval("SELECT MAX(code) FROM connection_types") or 0
            new_code = max_code + 1
            self.comelec_officer_type_id = await self.db_conn.fetchval("""
                INSERT INTO connection_types (code, name, description)
                VALUES ($1, $2, $3)
                RETURNING id
            """, new_code, 'COMELEC Officer', 'Officer or employee of the Commission on Elections')
            print(f"✅ Created 'COMELEC Officer' type (ID: {self.comelec_officer_type_id})")
    
    async def find_senator_by_number(self, senator_number: int) -> Optional[Dict]:
        """Find senator in database by number"""
        # Try different patterns to find senator
        patterns = [
            f"%SENATOR {senator_number}%",
            f"%SENATOR #{senator_number}%",
            f"%SENATOR NO. {senator_number}%",
        ]
        
        for pattern in patterns:
            senator = await self.db_conn.fetchrow("""
                SELECT id, first_name, last_name, position, province, year
                FROM political_dynasties 
                WHERE position ILIKE $1
                AND year >= 2022
                ORDER BY year DESC
                LIMIT 1
            """, pattern)
            
            if senator:
                return dict(senator)
        
        # Fallback: try to find any senator from 2022-2025
        all_senators = await self.db_conn.fetch("""
            SELECT DISTINCT ON (first_name, last_name) 
                id, first_name, last_name, position, province, year
            FROM political_dynasties 
            WHERE position ILIKE '%SENATOR%' AND year >= 2022
            ORDER BY first_name, last_name, year DESC
            LIMIT 24
        """)
        
        # Try to match by list position (assuming senators are numbered 1-24)
        if senator_number <= len(all_senators):
            return dict(all_senators[senator_number - 1])
        
        return None
    
    async def find_person_by_name(self, full_name: str, fuzzy: bool = True) -> Optional[Dict]:
        """Find a person in the database by full name"""
        try:
            full_name = full_name.strip()
            if not full_name:
                return None
            
            # Try exact match
            person = await self.db_conn.fetchrow("""
                SELECT id, first_name, last_name, province, position, year
                FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) = $1
                ORDER BY year DESC
                LIMIT 1
            """, full_name)
            
            if person:
                return dict(person)
            
            if fuzzy:
                # Try case-insensitive match
                person = await self.db_conn.fetchrow("""
                    SELECT id, first_name, last_name, province, position, year
                    FROM political_dynasties 
                    WHERE CONCAT(first_name, ' ', last_name) ILIKE $1
                    ORDER BY year DESC
                    LIMIT 1
                """, full_name)
                
                if person:
                    return dict(person)
                
                # Try partial match (first + last name only)
                parts = full_name.split()
                if len(parts) >= 2:
                    first_name = parts[0]
                    last_name = parts[-1]
                    person = await self.db_conn.fetchrow("""
                        SELECT id, first_name, last_name, province, position, year
                        FROM political_dynasties 
                        WHERE first_name ILIKE $1 AND last_name ILIKE $2
                        ORDER BY year DESC
                        LIMIT 1
                    """, first_name, last_name)
                    
                    if person:
                        return dict(person)
            
            return None
            
        except Exception as e:
            print(f"   ❌ Error finding person '{full_name}': {e}")
            return None
    
    def identify_comelec_officials(self, text: str, names: Set[str]) -> Dict[str, Tuple[str, Optional[int]]]:
        """
        Identify which names are COMELEC officials
        Returns dict mapping name -> (role, relationship_type_id)
        """
        comelec_officials = {}
        text_upper = text.upper()
        
        # Patterns for COMELEC roles
        comelec_patterns = [
            (r'COMELEC\s+CHAIRMAN[:\s]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)', 'Chairman', self.comelec_chairman_type_id),
            (r'CHAIRMAN[:\s]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+).*?COMELEC', 'Chairman', self.comelec_chairman_type_id),
            (r'COMMISSION\s+ON\s+ELECTIONS.*?CHAIRMAN[:\s]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)', 'Chairman', self.comelec_chairman_type_id),
            (r'COMELEC\s+COMMISSIONER[:\s]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)', 'Commissioner', self.comelec_commissioner_type_id),
            (r'COMMISSIONER[:\s]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+).*?COMELEC', 'Commissioner', self.comelec_commissioner_type_id),
            (r'COMELEC.*?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+).*?CHAIRMAN', 'Chairman', self.comelec_chairman_type_id),
            (r'COMELEC.*?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+).*?COMMISSIONER', 'Commissioner', self.comelec_commissioner_type_id),
        ]
        
        for pattern, role, type_id in comelec_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
                name = match.group(1).strip()
                # Try to match this name with names we found
                for found_name in names:
                    if name.upper() in found_name.upper() or found_name.upper() in name.upper():
                        comelec_officials[found_name] = (role, type_id)
                        self.comelec_names.add(found_name)
        
        # Also check if names appear near COMELEC text (within 50 chars)
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if 'COMELEC' in line.upper() or 'COMMISSION ON ELECTIONS' in line.upper():
                # Check surrounding lines
                for check_line_idx in range(max(0, i-2), min(len(lines), i+3)):
                    check_line = lines[check_line_idx]
                    for name in names:
                        # Check if name appears in nearby line
                        if name.upper() in check_line.upper() or any(part in check_line.upper() for part in name.split() if len(part) > 2):
                            if name not in comelec_officials:
                                # Default to COMELEC Officer if not specifically identified
                                comelec_officials[name] = ('Officer', self.comelec_officer_type_id)
                                self.comelec_names.add(name)
        
        return comelec_officials
    
    def extract_text_with_ocr(self, pdf_path: str) -> str:
        """Extract text from PDF using OCR if needed"""
        all_text = ""
        
        # First try regular text extraction
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        all_text += page_text + "\n"
        except Exception as e:
            print(f"   ⚠️  Error reading PDF text: {e}")
        
        # If we got good text, return it
        if all_text and len(all_text.strip()) > 100:
            return all_text
        
        # Otherwise try OCR
        if not OCR_AVAILABLE:
            return all_text
        
        print(f"   🔍 Attempting OCR extraction...")
        try:
            images = convert_from_path(pdf_path, dpi=300)
            for i, image in enumerate(images):
                ocr_text = pytesseract.image_to_string(image, lang='eng')
                all_text += ocr_text + "\n"
            print(f"   ✅ OCR extracted {len(all_text)} characters")
        except Exception as e:
            print(f"   ⚠️  OCR error: {e}")
            print(f"      Make sure tesseract-ocr is installed: sudo apt-get install tesseract-ocr")
        
        return all_text
    
    def extract_names_from_text(self, text: str) -> Set[str]:
        """Extract potential person names from text"""
        names = set()
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Skip common non-name patterns
            skip_patterns = [
                'SENATOR', 'CONTRIBUTOR', 'CAMPAIGN', 'TOTAL', 'AMOUNT', 'PESOS', 'PHP',
                'DATE', 'PAGE', 'SUMMARY', 'REPORT', 'CONTRIBUTION', 'DONATION',
                'PHILIPPINES', 'REPUBLIC', 'PHILIPPINE', 'ELECTION', 'CERTIFIED',
                'VERIFIED', 'APPROVED', 'SIGNED', 'NOTARIZED', 'RECEIVED', 'SUBMITTED'
            ]
            
            if any(skip in line.upper() for skip in skip_patterns):
                continue
            
            # Look for name-like patterns (2-5 words, mostly letters)
            words = [w.replace(',', '').replace('.', '').strip() for w in line.split()]
            words = [w for w in words if w]  # Remove empty
            
            if 2 <= len(words) <= 5:
                # Check if it looks like a name (mostly letters, first word capitalized)
                if all(w.replace('-', '').replace("'", '').replace("’", '').isalpha() 
                       for w in words if w and len(w) > 1):
                    first_word = words[0]
                    if first_word and first_word[0].isupper():
                        # Clean up the name
                        name = ' '.join(words)
                        if len(name) >= 3 and not name.isdigit():
                            names.add(name)
        
        # Pattern: "LASTNAME, Firstname" format
        comma_pattern = r'\b([A-Z][A-Za-z]+),\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        for match in re.finditer(comma_pattern, text):
            last_name = match.group(1)
            first_name = match.group(2)
            names.add(f"{first_name} {last_name}")
        
        return names
    
    async def process_pdf_file(self, pdf_path: str):
        """Process a single PDF file"""
        filename = os.path.basename(pdf_path)
        print(f"\n📄 Processing: {filename}")
        
        # Extract senator number from filename
        match = re.search(r'SENATOR_(\d+)', filename)
        if not match:
            print(f"   ⚠️  Could not extract senator number from filename")
            return
        
        senator_number = int(match.group(1))
        print(f"   🔍 Senator number: {senator_number}")
        
        # Find senator in database
        senator = await self.find_senator_by_number(senator_number)
        if not senator:
            print(f"   ❌ Could not find senator #{senator_number} in database")
            return
        
        print(f"   ✅ Found senator: {senator['first_name']} {senator['last_name']} (ID: {senator['id']})")
        
        # Extract text from PDF (with OCR if needed)
        all_text = self.extract_text_with_ocr(pdf_path)
        
        if not all_text or len(all_text.strip()) < 50:
            print(f"   ⚠️  Could not extract meaningful text from PDF")
            return
        
        print(f"   📖 Extracted {len(all_text)} characters of text")
        
        # Extract names from text
        all_names = self.extract_names_from_text(all_text)
        print(f"   👥 Found {len(all_names)} potential names")
        if all_names and len(all_names) <= 20:  # Show names if reasonable number
            print(f"      Names: {', '.join(list(all_names)[:10])}")
        
        # Filter out senator's own name
        senator_full_name = f"{senator['first_name']} {senator['last_name']}"
        all_names.discard(senator_full_name)
        all_names.discard(senator['first_name'])
        all_names.discard(senator['last_name'])
        
        # Identify COMELEC officials
        comelec_officials = self.identify_comelec_officials(all_text, all_names)
        print(f"   🏛️  Identified {len(comelec_officials)} COMELEC officials")
        
        # Separate contributors from COMELEC officials
        contributor_names = all_names - set(comelec_officials.keys())
        self.total_names_found += len(all_names)
        
        # Process COMELEC officials
        for name, (role, type_id) in comelec_officials.items():
            person = await self.find_person_by_name(name)
            if not person:
                # Try simplified name
                parts = name.split()
                if len(parts) > 2:
                    simple_name = f"{parts[0]} {parts[-1]}"
                    person = await self.find_person_by_name(simple_name)
            
            if person:
                self.matched_people += 1
                # Check if relationship already exists
                existing = await self.db_conn.fetchrow("""
                    SELECT id FROM relationships 
                    WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                """, senator['id'], person['id'], type_id)
                
                if not existing:
                    try:
                        await self.db_conn.execute("""
                            INSERT INTO relationships (
                                person_id, related_person_id, relationship_type,
                                relationship_description, source_url, confidence_level,
                                verified, created_by
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """, 
                        senator['id'], person['id'], type_id,
                        f"COMELEC {role} - appears in {senator['first_name']} {senator['last_name']} campaign report (2025)",
                        filename, 8, False, 'PDF_Import'
                        )
                        
                        self.added_comelec_officials += 1
                        print(f"      🏛️  Added COMELEC {role}: {person['first_name']} {person['last_name']}")
                    except Exception as e:
                        print(f"      ❌ Error adding COMELEC official: {e}")
        
        # Process campaign contributors
        for contributor_name in contributor_names:
            person = await self.find_person_by_name(contributor_name)
            
            if not person:
                # Try simplified name
                parts = contributor_name.split()
                if len(parts) > 2:
                    simple_name = f"{parts[0]} {parts[-1]}"
                    person = await self.find_person_by_name(simple_name)
            
            if not person:
                print(f"      ⚠️  No match found for: {contributor_name}")
                continue
            
            self.matched_people += 1
            
            # Check if relationship already exists
            existing = await self.db_conn.fetchrow("""
                SELECT id FROM relationships 
                WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
            """, senator['id'], person['id'], self.campaign_contributor_type_id)
            
            if existing:
                continue
            
            # Add relationship
            try:
                await self.db_conn.execute("""
                    INSERT INTO relationships (
                        person_id, related_person_id, relationship_type,
                        relationship_description, source_url, confidence_level,
                        verified, created_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, 
                senator['id'], person['id'], self.campaign_contributor_type_id,
                f"Campaign contributor to {senator['first_name']} {senator['last_name']} (2025)",
                filename, 7, False, 'PDF_Import'
                )
                
                self.added_contributors += 1
                print(f"      ✅ Added contributor: {person['first_name']} {person['last_name']}")
                
            except Exception as e:
                print(f"      ❌ Error adding contributor: {e}")
        
        self.processed_files += 1
    
    async def process_all_senator_pdfs(self):
        """Process all senator PDF files and other campaign contribution files"""
        # Look for senator PDFs
        pdf_files = glob.glob('database/2025_SENATOR*.pdf')
        pdf_files.extend(glob.glob('database/*SENATOR*.pdf'))
        pdf_files.extend(glob.glob('database/*CONTRIBUTION*.pdf'))
        pdf_files.extend(glob.glob('database/*COC*.pdf'))
        pdf_files.extend(glob.glob('database/*SOCE*.pdf'))  # Statement of Contributions and Expenditures
        
        # Remove duplicates
        pdf_files = list(set(pdf_files))
        
        if not pdf_files:
            print("❌ No senator or contribution PDF files found in database/ directory")
            print("   Looking for files matching: *SENATOR*.pdf, *CONTRIBUTION*.pdf, *COC*.pdf, *SOCE*.pdf")
            return
        
        print(f"📚 Found {len(pdf_files)} PDF files to process")
        
        for pdf_file in sorted(pdf_files):
            await self.process_pdf_file(pdf_file)
        
        # Print summary
        print(f"\n📊 Processing Summary:")
        print(f"   Files processed: {self.processed_files}")
        print(f"   Total names found: {self.total_names_found}")
        print(f"   People matched in database: {self.matched_people}")
        print(f"   Campaign contributors added: {self.added_contributors}")
        print(f"   COMELEC officials added: {self.added_comelec_officials}")

    async def process_zip_files(self):
        """Process ZIP files that might contain COMELEC contributor data"""
        zip_files = glob.glob('database/*comelec*.zip')
        zip_files.extend(glob.glob('database/*COMELEC*.zip'))
        zip_files.extend(glob.glob('database/*COC*.zip'))
        
        zip_files = list(set(zip_files))
        
        # Filter out directories and incomplete files
        valid_zips = []
        for zf in zip_files:
            if os.path.isdir(zf):
                continue
            size_mb = os.path.getsize(zf) / (1024 * 1024)
            if size_mb > 1:  # Only process files larger than 1MB (likely complete)
                valid_zips.append(zf)
        
        if not valid_zips:
            return
        
        print(f"\n📦 Found {len(valid_zips)} ZIP files to process")
        
        # Process only the first one for testing
        if valid_zips:
            print(f"   Testing with: {os.path.basename(valid_zips[0])}")
            await self.process_zip_file(valid_zips[0])
    
    async def process_zip_file(self, zip_path: str):
        """Process a single ZIP file, extract PDFs and process them"""
        filename = os.path.basename(zip_path)
        print(f"\n📦 Processing ZIP: {filename}")
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get list of PDF files in the ZIP
                pdf_files = [f for f in zip_ref.namelist() if f.lower().endswith('.pdf')]
                
                if not pdf_files:
                    print(f"   ⚠️  No PDF files found in ZIP")
                    return
                
                print(f"   📄 Found {len(pdf_files)} PDF files in ZIP")
                print(f"   📋 Processing first 10 PDFs as test...")
                
                # Create temporary directory for extraction
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Extract and process first 10 PDFs
                    for pdf_file in pdf_files[:10]:
                        try:
                            # Extract PDF to temp directory
                            zip_ref.extract(pdf_file, temp_dir)
                            pdf_path = os.path.join(temp_dir, pdf_file)
                            
                            # Process the PDF (extract senator info from filename or content)
                            print(f"\n      Processing: {os.path.basename(pdf_file)}")
                            await self.process_pdf_from_zip(pdf_path, pdf_file)
                            
                        except Exception as e:
                            print(f"      ⚠️  Error processing {pdf_file}: {e}")
                            continue
                        
        except zipfile.BadZipFile:
            print(f"   ❌ ZIP file appears to be incomplete or corrupted")
            print(f"      File size: {os.path.getsize(zip_path) / (1024*1024):.2f} MB")
            print(f"      ZIP may still be downloading. Wait for download to complete.")
        except zipfile.LargeZipFile:
            print(f"   ⚠️  ZIP file is too large (>2GB), may need 64-bit ZIP support")
        except Exception as e:
            print(f"   ❌ Error processing ZIP file: {e}")
            import traceback
            print(f"      Details: {traceback.format_exc()}")
    
    async def process_pdf_from_zip(self, pdf_path: str, original_path: str):
        """Process a PDF extracted from ZIP - try to identify senator from filename"""
        # Extract senator info from filename
        filename = os.path.basename(original_path)
        
        # Try to extract senator number or name from filename
        senator_match = re.search(r'SENATOR[_\s]*(\d+)', filename.upper())
        senator_name_match = re.search(r'([A-Z][A-Z\s,]+)', filename)
        
        senator = None
        if senator_match:
            senator_number = int(senator_match.group(1))
            senator = await self.find_senator_by_number(senator_number)
        
        # If no senator found, try to extract from PDF content
        if not senator:
            all_text = self.extract_text_with_ocr(pdf_path)
            senator_name = self.extract_senator_name_from_text(all_text)
            if senator_name:
                senator = await self.find_person_by_name(senator_name)
        
        if not senator:
            print(f"      ⚠️  Could not identify senator from filename or content")
            return
        
        print(f"      ✅ Found senator: {senator['first_name']} {senator['last_name']} (ID: {senator['id']})")
        
        # Extract text and process
        all_text = self.extract_text_with_ocr(pdf_path)
        
        if not all_text or len(all_text.strip()) < 50:
            print(f"      ⚠️  Could not extract meaningful text")
            return
        
        # Extract names from text
        all_names = self.extract_names_from_text(all_text)
        print(f"      👥 Found {len(all_names)} potential names")
        
        # Filter out senator's own name
        senator_full_name = f"{senator['first_name']} {senator['last_name']}"
        all_names.discard(senator_full_name)
        all_names.discard(senator['first_name'])
        all_names.discard(senator['last_name'])
        
        # Identify COMELEC officials
        comelec_officials = self.identify_comelec_officials(all_text, all_names)
        print(f"      🏛️  Identified {len(comelec_officials)} COMELEC officials")
        
        # Separate contributors from COMELEC officials
        contributor_names = all_names - set(comelec_officials.keys())
        self.total_names_found += len(all_names)
        
        # Process COMELEC officials and contributors (same logic as regular PDF processing)
        # ... (reuse the processing logic from process_pdf_file)
        for name, (role, type_id) in comelec_officials.items():
            person = await self.find_person_by_name(name)
            if not person:
                parts = name.split()
                if len(parts) > 2:
                    simple_name = f"{parts[0]} {parts[-1]}"
                    person = await self.find_person_by_name(simple_name)
            
            if person:
                self.matched_people += 1
                existing = await self.db_conn.fetchrow("""
                    SELECT id FROM relationships 
                    WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                """, senator['id'], person['id'], type_id)
                
                if not existing:
                    try:
                        await self.db_conn.execute("""
                            INSERT INTO relationships (
                                person_id, related_person_id, relationship_type,
                                relationship_description, source_url, confidence_level,
                                verified, created_by
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """, 
                        senator['id'], person['id'], type_id,
                        f"COMELEC {role} - appears in {senator['first_name']} {senator['last_name']} campaign report (2025)",
                        filename, 8, False, 'PDF_Import'
                        )
                        self.added_comelec_officials += 1
                        print(f"         🏛️  Added COMELEC {role}: {person['first_name']} {person['last_name']}")
                    except Exception as e:
                        print(f"         ❌ Error: {e}")
        
        for contributor_name in contributor_names:
            person = await self.find_person_by_name(contributor_name)
            if not person:
                parts = contributor_name.split()
                if len(parts) > 2:
                    simple_name = f"{parts[0]} {parts[-1]}"
                    person = await self.find_person_by_name(simple_name)
            
            if not person:
                continue
            
            self.matched_people += 1
            existing = await self.db_conn.fetchrow("""
                SELECT id FROM relationships 
                WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
            """, senator['id'], person['id'], self.campaign_contributor_type_id)
            
            if existing:
                continue
            
            try:
                await self.db_conn.execute("""
                    INSERT INTO relationships (
                        person_id, related_person_id, relationship_type,
                        relationship_description, source_url, confidence_level,
                        verified, created_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, 
                senator['id'], person['id'], self.campaign_contributor_type_id,
                f"Campaign contributor to {senator['first_name']} {senator['last_name']} (2025)",
                filename, 7, False, 'PDF_Import'
                )
                self.added_contributors += 1
                print(f"         ✅ Added contributor: {person['first_name']} {person['last_name']}")
            except Exception as e:
                print(f"         ❌ Error: {e}")

    async def process_excel_files(self):
        """Process Excel files that might contain contributor data"""
        excel_files = glob.glob('database/*CONTRIBUTION*.xlsx')
        excel_files.extend(glob.glob('database/*CONTRIBUTION*.xls'))
        excel_files.extend(glob.glob('database/*COC*.xlsx'))
        excel_files.extend(glob.glob('database/*SOCE*.xlsx'))
        
        excel_files = list(set(excel_files))
        
        if not excel_files:
            return
        
        print(f"\n📊 Found {len(excel_files)} Excel files to process")
        
        for excel_file in excel_files:
            await self.process_excel_file(excel_file)
    
    async def process_excel_file(self, excel_path: str):
        """Process a single Excel file"""
        filename = os.path.basename(excel_path)
        print(f"\n📊 Processing Excel: {filename}")
        
        try:
            # Try to read all sheets
            excel_data = pd.read_excel(excel_path, sheet_name=None)
            
            for sheet_name, df in excel_data.items():
                print(f"   📋 Processing sheet: {sheet_name}")
                # Look for columns that might contain names
                name_columns = [col for col in df.columns if any(keyword in col.upper() for keyword in ['NAME', 'CONTRIBUTOR', 'DONOR', 'DONATED BY'])]
                
                if name_columns:
                    print(f"      Found name columns: {name_columns}")
                    # Extract names from these columns
                    for col in name_columns:
                        names = df[col].dropna().astype(str).tolist()
                        for name in names:
                            if len(name.strip()) > 5 and not any(x in name.upper() for x in ['TOTAL', 'SUBtotal', 'PHP', 'PESO']):
                                print(f"      Found potential name: {name}")
                                # TODO: Process this name similarly to PDF processing
        except Exception as e:
            print(f"   ❌ Error processing Excel file: {e}")

async def main():
    """Main function"""
    importer = SenatorCampaignContributorImporter()
    
    try:
        await importer.connect()
        await importer.ensure_connection_types()
        await importer.process_zip_files()  # Process ZIP files first (test with one)
        await importer.process_all_senator_pdfs()
        await importer.process_excel_files()
    finally:
        await importer.close()

if __name__ == "__main__":
    asyncio.run(main())
