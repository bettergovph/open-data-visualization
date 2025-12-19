
import os
import sys
import subprocess
import shutil

# This script assumes 'pandoc' is installed and available in the WSL PATH.
# It converts the markdown report to a docx file.

MD_FILE = "top_100_mpb_detailed_list.md"
DOCX_FILE = "top_100_mpb_detailed_list.docx"

def main():
    if not os.path.exists(MD_FILE):
        print(f"Error: {MD_FILE} not found.")
        return

    print(f"Converting {MD_FILE} to {DOCX_FILE} using pandoc...")

    cmd = ["pandoc", MD_FILE, "-o", DOCX_FILE]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"Successfully created {DOCX_FILE}")
    except FileNotFoundError:
        print("Error: 'pandoc' command not found. Please install pandoc.")
        print("Try: sudo apt-get install pandoc")
    except subprocess.CalledProcessError as e:
        print(f"Error running pandoc: {e}")

if __name__ == "__main__":
    main()
