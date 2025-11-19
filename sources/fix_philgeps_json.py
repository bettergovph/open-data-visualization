#!/usr/bin/env python3
"""
Fix the PhilGEPS JSON structure:
1. Restructure registration_details to separate fields
2. Separate company name from type (Partnership, Single Proprietorship, etc.)
"""

import json
import re
from datetime import datetime


def parse_registration_details(reg_details_text: str) -> dict:
    """
    Parse registration details text into structured fields.
    Example input: "Platinum202401-375315-901591731 (Exp:2026-03-15 23:59:59)Mayor's Permit: 0442 (Exp:2025-12-31)Tax Clearance: 05-25B-11-22-R01617-2024M (Exp: 2025-11-22)DTI: 1999546 (Exp: 2030-07-24)"
    """
    parsed = {
        'status': None,
        'philgeps_number': None,
        'philgeps_expiry': None,
        'mayors_permit': None,
        'mayors_permit_expiry': None,
        'tax_clearance': None,
        'tax_clearance_expiry': None,
        'dti': None,
        'dti_expiry': None,
        'sec': None,
        'approved_date': None
    }
    
    if not reg_details_text:
        return parsed
    
    text = reg_details_text.strip()
    
    # Extract status (Platinum, Red, Gold, Silver, and any other color/status)
    # Handle cases like "Platinum(Suspended)" or just "Platinum" or "Red"
    # Match status at the start, optionally followed by (Suspended) or other modifiers
    status_match = re.search(r'^([A-Za-z]+)(?:\([^)]+\))?', text)
    if status_match:
        potential_status = status_match.group(1)
        # Common statuses: Platinum, Red, Gold, Silver, Bronze, Blue, Green, Yellow, Orange, Purple, Black, White
        # Also handle statuses like "Suspended", "Active", "Inactive", etc.
        common_statuses = ['Platinum', 'Red', 'Gold', 'Silver', 'Bronze', 'Blue', 'Green', 
                          'Yellow', 'Orange', 'Purple', 'Black', 'White', 'Suspended', 
                          'Active', 'Inactive', 'Pending', 'Approved', 'Rejected']
        # Accept if it's a known status or a reasonable length (likely a status word)
        if potential_status in common_statuses or (len(potential_status) <= 15 and potential_status[0].isupper()):
            parsed['status'] = potential_status
            
            # Also extract modifier if present (e.g., "Suspended" in "Platinum(Suspended)")
            modifier_match = re.search(r'^[A-Za-z]+\(([^)]+)\)', text)
            if modifier_match:
                parsed['status_modifier'] = modifier_match.group(1)
    
    # Extract registration number (PhilGEPS number) and expiry
    # Pattern: YYYYMM-XXXXX-XXXXXXXXX (Exp:YYYY-MM-DD HH:MM:SS)
    reg_match = re.search(r'(\d{6}-\d+-\d+)\s*\(Exp:([^)]+)\)', text)
    if reg_match:
        parsed['philgeps_number'] = reg_match.group(1)
        parsed['philgeps_expiry'] = reg_match.group(2).strip()
    
    # Extract Mayor's Permit (can have spaces in the permit number like "25 CGP 31921")
    mayor_match = re.search(r"Mayor's Permit:\s*([^(]+?)\s*\(Exp:\s*([^)]+)\)", text, re.I)
    if mayor_match:
        parsed['mayors_permit'] = mayor_match.group(1).strip()
        parsed['mayors_permit_expiry'] = mayor_match.group(2).strip()
    
    # Extract Tax Clearance
    tax_match = re.search(r'Tax Clearance:\s*([^\s(]+(?:\s+[^\s(]+)*)\s*\(Exp:\s*([^)]+)\)', text, re.I)
    if tax_match:
        parsed['tax_clearance'] = tax_match.group(1).strip()
        parsed['tax_clearance_expiry'] = tax_match.group(2).strip()
    
    # Extract DTI
    dti_match = re.search(r'DTI:\s*(\d+)\s*\(Exp:\s*([^)]+)\)', text, re.I)
    if dti_match:
        parsed['dti'] = dti_match.group(1).strip()
        parsed['dti_expiry'] = dti_match.group(2).strip()
    
    # Extract SEC
    sec_match = re.search(r'SEC:\s*([^\s]+)', text, re.I)
    if sec_match:
        parsed['sec'] = sec_match.group(1).strip()
    
    # Extract Approved Date
    approved_match = re.search(r'Approved Date:\s*([^/\s]+/[^/\s]+/[^/\s]+)', text, re.I)
    if approved_match:
        parsed['approved_date'] = approved_match.group(1).strip()
    
    return parsed


def parse_company_name(name_text: str) -> dict:
    """
    Parse company name to separate name from type.
    Examples:
    - "LEGACY CONSTRUCTION CORPORATION/MIGHTY HOK SUMMIT CONSTRUCTION AND DEVELOPMENT CORPORATION JOINT VENTUREPartnership"
      -> name: "LEGACY CONSTRUCTION CORPORATION/MIGHTY HOK SUMMIT CONSTRUCTION AND DEVELOPMENT CORPORATION JOINT VENTURE", type: "Partnership"
    - "QM BUILDERSSingle Proprietorship"
      -> name: "QM BUILDERS", type: "Single Proprietorship"
    """
    if not name_text:
        return {'name': name_text, 'type': None}
    
    # Common business types to look for (ordered by specificity - more specific first)
    business_types = [
        'Single Proprietorship',
        'Individual Local Consultant',
        'Joint Venture',
        'One Person Corporation',
        'Partnership',
        'Corporation',
        'Cooperative',
        'Foundation',
        'Association',
        'OPC',  # One Person Corporation (abbreviation)
        'JV',  # Joint Venture (abbreviation)
        'Incorporated',
        'Inc.',
        'Inc',
        'Corp.',
        'Corp',
        'Ltd.',
        'Ltd',
        'Limited',
    ]
    
    # Try to find business type at the end
    name = name_text
    business_type = None
    
    # Check for each business type (case-insensitive)
    for btype in business_types:
        # Pattern: name ends with business type (no space before it)
        pattern = re.compile(r'(.+?)' + re.escape(btype) + r'$', re.I)
        match = pattern.match(name_text)
        if match:
            name = match.group(1).strip()
            business_type = btype
            break
    
    # If no match found, check if there's a space before the type
    if not business_type:
        for btype in business_types:
            pattern = re.compile(r'(.+?)\s+' + re.escape(btype) + r'$', re.I)
            match = pattern.match(name_text)
            if match:
                name = match.group(1).strip()
                business_type = btype
                break
    
    return {
        'name': name,
        'type': business_type
    }


def fix_result_entry(entry: dict) -> dict:
    """Fix a single result entry"""
    fixed = entry.copy()
    
    # Fix registration_details
    reg_details = entry.get('registration_details', {})
    if isinstance(reg_details, dict):
        # Get the raw registration details text
        raw_reg_text = reg_details.get('Registration Details', '')
        
        # Use parsed details if available, otherwise parse from raw text
        parsed_details = reg_details.get('Parsed Details', {})
        if not parsed_details or not parsed_details.get('status'):
            # Parse from raw text
            parsed_details = parse_registration_details(raw_reg_text)
        
        # Map old field names to new ones if needed
        if parsed_details.get('registration_number') and not parsed_details.get('philgeps_number'):
            parsed_details['philgeps_number'] = parsed_details['registration_number']
            parsed_details['philgeps_expiry'] = parsed_details.get('registration_expiry')
        
        # Restructure registration_details
        fixed_reg_details = {}
        
        # Add status
        if parsed_details.get('status'):
            fixed_reg_details['status'] = parsed_details['status']
        
        # Add status modifier if present
        if parsed_details.get('status_modifier'):
            fixed_reg_details['status_modifier'] = parsed_details['status_modifier']
        
        # Add PhilGEPS number with expiry
        if parsed_details.get('philgeps_number'):
            philgeps_str = parsed_details['philgeps_number']
            if parsed_details.get('philgeps_expiry'):
                philgeps_str += f" (Exp:{parsed_details['philgeps_expiry']})"
            fixed_reg_details['philgeps_number'] = philgeps_str
        
        # Add Mayor's Permit
        if parsed_details.get('mayors_permit'):
            mayor_str = parsed_details['mayors_permit']
            if parsed_details.get('mayors_permit_expiry'):
                mayor_str += f" (Exp:{parsed_details['mayors_permit_expiry']})"
            fixed_reg_details["mayor's_permit"] = mayor_str
        
        # Add Tax Clearance
        if parsed_details.get('tax_clearance'):
            tax_str = parsed_details['tax_clearance']
            if parsed_details.get('tax_clearance_expiry'):
                tax_str += f" (Exp: {parsed_details['tax_clearance_expiry']})"
            fixed_reg_details['tax_clearance'] = tax_str
        
        # Add DTI
        if parsed_details.get('dti'):
            dti_str = parsed_details['dti']
            if parsed_details.get('dti_expiry'):
                dti_str += f" (Exp: {parsed_details['dti_expiry']})"
            fixed_reg_details['dti'] = dti_str
        
        # Add SEC
        if parsed_details.get('sec'):
            fixed_reg_details['sec'] = parsed_details['sec']
        
        # Add Approved Date
        if parsed_details.get('approved_date'):
            fixed_reg_details['approved_date'] = parsed_details['approved_date']
        
        fixed['registration_details'] = fixed_reg_details
        
        # Fix name field
        name_field = reg_details.get('Name', '')
        if name_field:
            parsed_name = parse_company_name(name_field)
            fixed['name'] = parsed_name['name']
            if parsed_name['type']:
                fixed['company_type'] = parsed_name['type']
    
    # Also fix all_results if present
    if 'registration_details' in fixed and isinstance(fixed['registration_details'], dict):
        all_results = fixed['registration_details'].get('all_results', [])
        if all_results:
            fixed_all_results = []
            for result in all_results:
                fixed_result = result.copy()
                
                # Fix name in result
                result_name = result.get('name', '')
                if result_name:
                    parsed_name = parse_company_name(result_name)
                    fixed_result['name'] = parsed_name['name']
                    if parsed_name['type']:
                        fixed_result['company_type'] = parsed_name['type']
                
                # Fix registration_details in result
                result_reg_text = result.get('registration_details', '')
                if result_reg_text:
                    result_parsed = result.get('parsed_details', {})
                    if not result_parsed or not result_parsed.get('status'):
                        result_parsed = parse_registration_details(result_reg_text)
                    
                    fixed_result_reg = {}
                    if result_parsed.get('status'):
                        fixed_result_reg['status'] = result_parsed['status']
                    if result_parsed.get('status_modifier'):
                        fixed_result_reg['status_modifier'] = result_parsed['status_modifier']
                    if result_parsed.get('philgeps_number'):
                        philgeps_str = result_parsed['philgeps_number']
                        if result_parsed.get('philgeps_expiry'):
                            philgeps_str += f" (Exp:{result_parsed['philgeps_expiry']})"
                        fixed_result_reg['philgeps_number'] = philgeps_str
                    if result_parsed.get('mayors_permit'):
                        mayor_str = result_parsed['mayors_permit']
                        if result_parsed.get('mayors_permit_expiry'):
                            mayor_str += f" (Exp:{result_parsed['mayors_permit_expiry']})"
                        fixed_result_reg["mayor's_permit"] = mayor_str
                    if result_parsed.get('tax_clearance'):
                        tax_str = result_parsed['tax_clearance']
                        if result_parsed.get('tax_clearance_expiry'):
                            tax_str += f" (Exp: {result_parsed['tax_clearance_expiry']})"
                        fixed_result_reg['tax_clearance'] = tax_str
                    if result_parsed.get('dti'):
                        dti_str = result_parsed['dti']
                        if result_parsed.get('dti_expiry'):
                            dti_str += f" (Exp: {result_parsed['dti_expiry']})"
                        fixed_result_reg['dti'] = dti_str
                    if result_parsed.get('sec'):
                        fixed_result_reg['sec'] = result_parsed['sec']
                    if result_parsed.get('approved_date'):
                        fixed_result_reg['approved_date'] = result_parsed['approved_date']
                    
                    fixed_result['registration_details'] = fixed_result_reg
                
                fixed_all_results.append(fixed_result)
            
            fixed['registration_details']['all_results'] = fixed_all_results
    
    return fixed


def main():
    input_file = 'database/philgeps_merchant_info_test.json'
    output_file = 'database/philgeps_merchant_info_fixed.json'
    
    print(f"📖 Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"📊 Found {len(data.get('results', []))} entries to fix")
    
    # Fix all results
    fixed_results = []
    for i, entry in enumerate(data.get('results', []), 1):
        if i % 100 == 0:
            print(f"  Processing entry {i}/{len(data.get('results', []))}...")
        fixed_entry = fix_result_entry(entry)
        fixed_results.append(fixed_entry)
    
    # Update data structure
    data['results'] = fixed_results
    data['last_updated'] = datetime.now().isoformat()
    data['fixed_date'] = datetime.now().isoformat()
    
    print(f"💾 Saving fixed data to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Done! Fixed {len(fixed_results)} entries")
    
    # Show a sample of fixed data
    if fixed_results:
        print(f"\n📋 Sample fixed entry:")
        sample = fixed_results[0]
        print(json.dumps({
            'contractor_name': sample.get('contractor_name'),
            'name': sample.get('name'),
            'company_type': sample.get('company_type'),
            'registration_details': sample.get('registration_details')
        }, indent=2)[:1000])


if __name__ == "__main__":
    main()

