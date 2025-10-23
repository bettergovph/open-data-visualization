#!/usr/bin/env python3
"""
Parse SEC results from sec_results directory and extract structured data.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

def parse_sec_file(file_path: str) -> Dict[str, Any]:
    """
    Parse a single SEC result file and extract company information.
    
    Args:
        file_path: Path to the SEC result file
        
    Returns:
        Dictionary containing parsed company data
    """
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Extract contractor name from filename
    contractor_name = Path(file_path).stem
    
    # Check if no results found
    if "No Record found" in content or "Result/s Found: --" in content:
        return {
            "contractor_name": contractor_name,
            "file_path": file_path,
            "status": "no_results",
            "companies": []
        }
    
    # Extract number of results
    results_match = re.search(r"Result/s Found: (\d+)", content)
    num_results = int(results_match.group(1)) if results_match else 0
    
    # Parse companies
    companies = []
    
    # Split content by "COMPANY DETAILS" to get individual company sections
    company_sections = re.split(r"COMPANY DETAILS", content)
    
    for section in company_sections[1:]:  # Skip first empty section
        company_data = parse_company_section(section)
        if company_data:
            companies.append(company_data)
    
    return {
        "contractor_name": contractor_name,
        "file_path": file_path,
        "status": "success" if companies else "no_results",
        "num_results": num_results,
        "companies": companies
    }

def parse_company_section(section: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single company section from SEC results.
    
    Args:
        section: Text section containing company details
        
    Returns:
        Dictionary with company information or None if invalid
    """
    lines = section.strip().split('\n')
    
    company_data = {}
    current_field = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for field labels
        if line == "Company Name":
            current_field = "company_name"
        elif line == "SEC Number":
            current_field = "sec_number"
        elif line == "Date Registered":
            current_field = "date_registered"
        elif line == "Status":
            current_field = "status"
        elif line == "Address":
            current_field = "address"
        elif line == "SECONDARY LICENSE DETAILS":
            current_field = "secondary_licenses"
        elif line == "REPORTORIAL SUBMISSION/S":
            current_field = "reportorial"
        elif current_field and not line.startswith(("COMPANY DETAILS", "SECONDARY LICENSE DETAILS", "REPORTORIAL SUBMISSION/S")):
            # This is a value for the current field
            if current_field == "company_name":
                company_data["company_name"] = line
            elif current_field == "sec_number":
                company_data["sec_number"] = line
            elif current_field == "date_registered":
                company_data["date_registered"] = line
            elif current_field == "status":
                company_data["status"] = line
            elif current_field == "address":
                if "address" not in company_data:
                    company_data["address"] = line
                else:
                    company_data["address"] += " " + line
            elif current_field == "secondary_licenses":
                if "secondary_licenses" not in company_data:
                    company_data["secondary_licenses"] = []
                if line != "No records of secondary licenses were found.":
                    company_data["secondary_licenses"].append(line)
    
    # Only return if we have at least company name and SEC number
    if "company_name" in company_data and "sec_number" in company_data:
        return company_data
    
    return None

def parse_all_sec_results(sec_results_dir: str = "sec_results") -> Dict[str, Any]:
    """
    Parse all SEC result files in the directory.
    
    Args:
        sec_results_dir: Directory containing SEC result files
        
    Returns:
        Dictionary containing all parsed data
    """
    results = {
        "summary": {
            "total_files": 0,
            "successful_parses": 0,
            "no_results": 0,
            "total_companies": 0,
            "unique_companies": 0
        },
        "contractors": {},
        "companies": []
    }
    
    sec_path = Path(sec_results_dir)
    if not sec_path.exists():
        print(f"Directory {sec_results_dir} does not exist")
        return results
    
    # Get all .txt files
    txt_files = list(sec_path.glob("*.txt"))
    results["summary"]["total_files"] = len(txt_files)
    
    print(f"Processing {len(txt_files)} SEC result files...")
    
    all_companies = []
    unique_sec_numbers = set()
    
    for i, file_path in enumerate(txt_files, 1):
        if i % 100 == 0:
            print(f"Processed {i}/{len(txt_files)} files...")
            
        try:
            parsed_data = parse_sec_file(str(file_path))
            contractor_name = parsed_data["contractor_name"]
            
            results["contractors"][contractor_name] = parsed_data
            
            if parsed_data["status"] == "success":
                results["summary"]["successful_parses"] += 1
                results["summary"]["total_companies"] += len(parsed_data["companies"])
                
                for company in parsed_data["companies"]:
                    all_companies.append(company)
                    if company.get("sec_number"):
                        unique_sec_numbers.add(company["sec_number"])
            else:
                results["summary"]["no_results"] += 1
                
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            results["contractors"][parsed_data["contractor_name"]] = {
                "contractor_name": parsed_data["contractor_name"],
                "file_path": str(file_path),
                "status": "error",
                "error": str(e),
                "companies": []
            }
    
    results["companies"] = all_companies
    results["summary"]["unique_companies"] = len(unique_sec_numbers)
    
    return results

def save_parsed_results(results: Dict[str, Any], output_file: str = "parsed_sec_results.json"):
    """
    Save parsed results to JSON file.
    
    Args:
        results: Parsed results dictionary
        output_file: Output JSON file path
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Results saved to {output_file}")

def generate_summary_report(results: Dict[str, Any]) -> str:
    """
    Generate a human-readable summary report.
    
    Args:
        results: Parsed results dictionary
        
    Returns:
        Summary report string
    """
    summary = results["summary"]
    
    report = f"""
SEC Results Parsing Summary
==========================

Files Processed: {summary['total_files']}
Successful Parses: {summary['successful_parses']}
No Results Found: {summary['no_results']}
Total Companies Found: {summary['total_companies']}
Unique Companies: {summary['unique_companies']}

Success Rate: {(summary['successful_parses'] / summary['total_files'] * 100):.1f}%
"""
    
    return report

def main():
    """Main function to parse SEC results."""
    print("Starting SEC results parsing...")
    
    # Parse all results
    results = parse_all_sec_results()
    
    # Save to JSON
    save_parsed_results(results)
    
    # Generate and print summary
    summary_report = generate_summary_report(results)
    print(summary_report)
    
    # Save summary to file
    with open("sec_parsing_summary.txt", 'w', encoding='utf-8') as f:
        f.write(summary_report)
    
    print("Parsing complete!")

if __name__ == "__main__":
    main()
