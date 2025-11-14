#!/usr/bin/env python3
"""
OCR script to extract GAA page numbers from z?.jpg images and update dpwh-projects.csv
The first column in the images is the GAA page number.
"""

import csv
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional
import pytesseract
from PIL import Image
import cv2
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def preprocess_image(image_path: str) -> np.ndarray:
    """Preprocess image for better OCR results."""
    # Read image
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply threshold to get binary image
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Optional: denoise
    denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)
    
    return denoised


def detect_bordered_tables(image_path: str) -> List[np.ndarray]:
    """Detect bordered tables in image and extract only table regions, ignoring text outside borders."""
    img = cv2.imread(image_path)
    if img is None:
        return []
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    
    # Detect horizontal lines (table borders)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 3, 1))
    horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    
    # Detect vertical lines (table borders)
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 10))
    vertical_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    
    # Combine horizontal and vertical lines
    table_structure = cv2.addWeighted(horizontal_lines, 0.5, vertical_lines, 0.5, 0.0)
    _, table_structure = cv2.threshold(table_structure, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Find contours of table structure
    cnts = cv2.findContours(table_structure, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    
    # Find rectangular table regions
    table_regions = []
    for c in cnts:
        x, y, w_rect, h_rect = cv2.boundingRect(c)
        area = w_rect * h_rect
        
        # Filter for large rectangular regions (likely tables)
        # Tables should be at least 30% of image width and 10% of image height
        if w_rect > w * 0.3 and h_rect > h * 0.1 and area > (w * h * 0.05):
            # Extract table region with small padding
            padding = 10
            x_start = max(0, x - padding)
            y_start = max(0, y - padding)
            x_end = min(w, x + w_rect + padding)
            y_end = min(h, y + h_rect + padding)
            
            table_region = img[y_start:y_end, x_start:x_end]
            if table_region.shape[0] > 50 and table_region.shape[1] > 50:
                table_regions.append(table_region)
    
    # Sort by y-coordinate (top to bottom)
    if table_regions:
        # Get bounding boxes for sorting
        table_boxes = []
        for region in table_regions:
            # Find the original position in the image
            for c in cnts:
                x, y, w_rect, h_rect = cv2.boundingRect(c)
                area = w_rect * h_rect
                if w_rect > w * 0.3 and h_rect > h * 0.1 and area > (w * h * 0.05):
                    table_boxes.append((y, region))
                    break
        
        # Sort by y-coordinate
        table_boxes.sort(key=lambda x: x[0])
        table_regions = [region for _, region in table_boxes]
    
    # If no tables detected, try alternative method: detect by finding grid structure
    if not table_regions:
        # Use HoughLines to detect strong horizontal and vertical lines
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # Detect horizontal lines
        horizontal_lines_img = np.zeros_like(edges)
        lines_h = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=w//2, maxLineGap=10)
        if lines_h is not None:
            for line in lines_h:
                x1, y1, x2, y2 = line[0]
                if abs(y2 - y1) < 5:  # Horizontal line
                    cv2.line(horizontal_lines_img, (x1, y1), (x2, y2), 255, 2)
        
        # Detect vertical lines
        vertical_lines_img = np.zeros_like(edges)
        lines_v = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=h//4, maxLineGap=10)
        if lines_v is not None:
            for line in lines_v:
                x1, y1, x2, y2 = line[0]
                if abs(x2 - x1) < 5:  # Vertical line
                    cv2.line(vertical_lines_img, (x1, y1), (x2, y2), 255, 2)
        
        # Combine to find table grid
        grid = cv2.addWeighted(horizontal_lines_img, 0.5, vertical_lines_img, 0.5, 0.0)
        
        # Find contours of grid
        cnts = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        
        for c in cnts:
            x, y, w_rect, h_rect = cv2.boundingRect(c)
            if w_rect > w * 0.3 and h_rect > h * 0.1:
                padding = 10
                x_start = max(0, x - padding)
                y_start = max(0, y - padding)
                x_end = min(w, x + w_rect + padding)
                y_end = min(h, y + h_rect + padding)
                
                table_region = img[y_start:y_end, x_start:x_end]
                if table_region.shape[0] > 50 and table_region.shape[1] > 50:
                    table_regions.append(table_region)
    
    # If still no tables, fallback to splitting image in half (portrait, 2 tables)
    if not table_regions:
        mid_y = h // 2
        top_table = img[0:mid_y, :]
        bottom_table = img[mid_y:, :]
        if top_table.shape[0] > 50:
            table_regions.append(top_table)
        if bottom_table.shape[0] > 50:
            table_regions.append(bottom_table)
    
    return table_regions


def extract_table_from_image(image_path: str) -> List[Dict[str, str]]:
    """Extract table data from image - handles 2 tables per image with 3 columns."""
    print(f"📸 Processing {image_path}...")
    
    all_rows = []
    
    # Detect and extract only bordered tables
    tables = detect_bordered_tables(image_path)
    print(f"  Found {len(tables)} bordered table(s) in image")
    
    for table_idx, table_img in enumerate(tables):
        print(f"  Processing table {table_idx + 1}...")
        
        # Preprocess table image
        gray = cv2.cvtColor(table_img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Use table-specific OCR mode
        try:
            custom_config = r'--oem 3 --psm 6'  # Uniform block of text
            
            # Get structured data with bounding boxes
            data = pytesseract.image_to_data(thresh, config=custom_config, output_type=pytesseract.Output.DICT)
            
            # Extract table rows from this table (pass table image for bold detection)
            table_rows = extract_table_from_boxes_with_headers(data, table_img.shape[1], table_img)
            all_rows.extend(table_rows)
            print(f"    ✅ Extracted {len(table_rows)} rows from table {table_idx + 1}")
            
        except Exception as e:
            print(f"    ⚠️  Error processing table {table_idx + 1}: {e}")
            # Fallback: try text parsing
            try:
                text = pytesseract.image_to_string(thresh, config=custom_config)
                rows = parse_table_text(text)
                all_rows.extend(rows)
            except Exception as e2:
                print(f"    ❌ Fallback also failed: {e2}")
    
    return all_rows


def detect_bold_text_in_line(table_img: np.ndarray, y: int, height: int, x_start: int, x_end: int) -> bool:
    """Detect if text in a line is bold by analyzing stroke width."""
    # Extract line region
    y_start = max(0, y - height // 2)
    y_end = min(table_img.shape[0], y + height + height // 2)
    x_start_img = max(0, x_start - 10)
    x_end_img = min(table_img.shape[1], x_end + 10)
    
    if y_end <= y_start or x_end_img <= x_start_img:
        return False
    
    line_region = table_img[y_start:y_end, x_start_img:x_end_img]
    if line_region.size == 0:
        return False
    
    # Convert to grayscale if needed
    if len(line_region.shape) == 3:
        gray_line = cv2.cvtColor(line_region, cv2.COLOR_BGR2GRAY)
    else:
        gray_line = line_region
    
    # Threshold
    _, thresh = cv2.threshold(gray_line, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Calculate stroke width - bold text has thicker strokes
    # Use distance transform to find stroke width
    dist = cv2.distanceTransform(thresh, cv2.DIST_L2, 5)
    
    # Bold text typically has thicker strokes (larger distance transform values)
    max_dist = np.max(dist)
    mean_dist = np.mean(dist[dist > 0]) if np.any(dist > 0) else 0
    
    # Bold text usually has mean stroke width > 2.5 pixels
    return mean_dist > 2.5 or max_dist > 4.0


def detect_table_grid(table_img: np.ndarray) -> tuple:
    """Detect all horizontal and vertical lines to create a complete grid structure."""
    gray = cv2.cvtColor(table_img, cv2.COLOR_BGR2GRAY) if len(table_img.shape) == 3 else table_img
    h, w = gray.shape
    
    # Enhance contrast for better line detection
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)
    
    # Detect horizontal lines (row separators)
    # Use larger kernel to catch all horizontal lines
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 2, 1))
    horizontal_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    _, horizontal_lines = cv2.threshold(horizontal_lines, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Detect vertical lines (column separators)
    # Use larger kernel to catch all vertical lines
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 5))
    vertical_lines = cv2.morphologyEx(gray, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    _, vertical_lines = cv2.threshold(vertical_lines, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Find all horizontal line positions (y-coordinates)
    h_contours = cv2.findContours(horizontal_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h_contours = h_contours[0] if len(h_contours) == 2 else h_contours[1]
    
    horizontal_positions = []
    for c in h_contours:
        x, y, w_line, h_line = cv2.boundingRect(c)
        if w_line > w * 0.4:  # Long enough to be a table line
            # Use the center y-coordinate of the line
            horizontal_positions.append(y + h_line // 2)
    
    # Remove duplicates and sort
    horizontal_positions = sorted(set(horizontal_positions))
    
    # Merge very close horizontal lines (within 5 pixels)
    merged_horizontal = []
    for pos in horizontal_positions:
        if not merged_horizontal or pos - merged_horizontal[-1] > 5:
            merged_horizontal.append(pos)
    horizontal_positions = merged_horizontal
    
    # Find all vertical line positions (x-coordinates)
    v_contours = cv2.findContours(vertical_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    v_contours = v_contours[0] if len(v_contours) == 2 else v_contours[1]
    
    vertical_positions = []
    for c in v_contours:
        x, y, w_line, h_line = cv2.boundingRect(c)
        if h_line > h * 0.2:  # Tall enough to be a table line
            # Use the center x-coordinate of the line
            vertical_positions.append(x + w_line // 2)
    
    # Remove duplicates and sort
    vertical_positions = sorted(set(vertical_positions))
    
    # Merge very close vertical lines (within 5 pixels)
    merged_vertical = []
    for pos in vertical_positions:
        if not merged_vertical or pos - merged_vertical[-1] > 5:
            merged_vertical.append(pos)
    vertical_positions = merged_vertical
    
    # Ensure we have boundaries
    if not horizontal_positions:
        horizontal_positions = [0, h]
    if not vertical_positions:
        vertical_positions = [0, w]
    
    # Add image boundaries if not present
    if horizontal_positions[0] > 10:
        horizontal_positions.insert(0, 0)
    if horizontal_positions[-1] < h - 10:
        horizontal_positions.append(h)
    
    if vertical_positions[0] > 10:
        vertical_positions.insert(0, 0)
    if vertical_positions[-1] < w - 10:
        vertical_positions.append(w)
    
    return horizontal_positions, vertical_positions


def extract_cell_text(cell_img: np.ndarray) -> str:
    """Extract text from a single cell image."""
    if cell_img.size == 0:
        return ""
    
    # Check if cell is too small
    h, w = cell_img.shape[:2]
    if h < 10 or w < 10:
        return ""
    
    # Preprocess cell image
    if len(cell_img.shape) == 3:
        gray = cv2.cvtColor(cell_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = cell_img
    
    # Check if cell is mostly empty (low variance indicates mostly blank)
    if np.var(gray) < 100:
        return ""
    
    # Enhance contrast
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Count non-white pixels - if too few, cell is likely empty
    non_white = np.sum(thresh < 255)
    total_pixels = thresh.size
    if non_white / total_pixels < 0.01:  # Less than 1% non-white
        return ""
    
    # Use OCR on cell
    try:
        text = pytesseract.image_to_string(thresh, config='--oem 3 --psm 7')  # Single line
        text = text.strip()
        
        # Filter out obvious garbage
        if len(text) < 2:
            return ""
        
        # Check if text is mostly special characters
        alpha_chars = sum(1 for c in text if c.isalnum())
        if len(text) > 0 and alpha_chars / len(text) < 0.2:
            return ""
        
        return text
    except:
        return ""


def extract_table_from_boxes_with_headers(data: Dict, image_width: int, table_img: np.ndarray = None) -> List[Dict[str, str]]:
    """Extract table rows using detected grid structure - extract values from each cell."""
    rows = []
    
    if table_img is None:
        return rows
    
    # Detect complete grid structure
    horizontal_lines, vertical_lines = detect_table_grid(table_img)
    
    if len(horizontal_lines) < 2 or len(vertical_lines) < 3:
        # Not enough grid lines, use fallback
        return extract_table_fallback(data, image_width, table_img)
    
    # Create grid cells
    # horizontal_lines define row boundaries
    # vertical_lines define column boundaries
    # For 3 columns, we expect at least 4 vertical lines (left, col1-col2, col2-col3, right)
    
    # Extract cell values
    grid_cells = []
    for row_idx in range(len(horizontal_lines) - 1):
        row_cells = []
        y_start = horizontal_lines[row_idx]
        y_end = horizontal_lines[row_idx + 1]
        
        for col_idx in range(len(vertical_lines) - 1):
            x_start = vertical_lines[col_idx]
            x_end = vertical_lines[col_idx + 1]
            
            # Extract cell region (with small padding to avoid borders)
            padding = 2
            cell_img = table_img[y_start + padding:y_end - padding, 
                                 x_start + padding:x_end - padding]
            
            # Extract text from cell
            cell_text = extract_cell_text(cell_img)
            row_cells.append(cell_text)
        
        grid_cells.append(row_cells)
    
    # Process grid cells to extract rows
    # First row is typically header
    header_processed = False
    
    for row_idx, row_cells in enumerate(grid_cells):
        if len(row_cells) < 3:
            continue
        
        # Get cell values (handle cases where we have more or fewer columns)
        col1_text = row_cells[0].strip() if len(row_cells) > 0 else ""
        col2_text = row_cells[1].strip() if len(row_cells) > 1 else ""
        col3_text = row_cells[2].strip() if len(row_cells) > 2 else ""
        
        # If we have more columns, combine them appropriately
        if len(row_cells) > 3:
            # Column 2 might span multiple cells
            col2_text = ' '.join([row_cells[i] for i in range(1, len(row_cells) - 1)]).strip()
            col3_text = row_cells[-1].strip()
        
        # Check if header row
        combined_text = (col1_text + ' ' + col2_text + ' ' + col3_text).upper()
        if not header_processed:
            is_header = (
                ('GAA' in col1_text.upper() or 'PAGE' in col1_text.upper()) and
                ('PROJECT' in col2_text.upper() and 'TITLE' in col2_text.upper()) and
                'AMOUNT' in col3_text.upper()
            )
            if is_header:
                header_processed = True
                continue
        
        # Extract GAA page from column 1
        gaa_page = ""
        gaa_bracket_match = re.search(r'\[(\d{1,4})\]', col1_text)
        if gaa_bracket_match:
            gaa_page = gaa_bracket_match.group(1)
        else:
            gaa_digits = re.sub(r'[^\d]', '', col1_text)
            if gaa_digits and 2 <= len(gaa_digits) <= 4:
                gaa_page = gaa_digits
        
        # Extract amount from column 3
        amount = ""
        amount_match = re.search(r'([\d,]{6,})', col3_text)
        if amount_match:
            amount = amount_match.group(1).replace(',', '')
        
        # Project title from column 2
        project_title = col2_text.strip()
        project_title = re.sub(r'^\W+', '', project_title)
        project_title = re.sub(r'\s+', ' ', project_title).strip()
        
        # Skip if no meaningful data
        if not project_title or len(project_title) < 5:
            continue
        
        # Filter out garbage OCR text
        # Check if text has too many special characters or looks like OCR noise
        alpha_chars = sum(1 for c in project_title if c.isalpha())
        total_chars = len(project_title)
        if total_chars > 0:
            alpha_ratio = alpha_chars / total_chars
            # If less than 30% alphabetic, likely garbage
            if alpha_ratio < 0.3:
                continue
        
        # Check for common OCR garbage patterns
        garbage_patterns = [
            r'^[^\w\s]{3,}',  # Starts with many special chars
            r'[^\w\s]{5,}',   # Many consecutive special chars
            r'^[a-z]{1,2}\s+[a-z]{1,2}\s+[a-z]{1,2}',  # Very short words
        ]
        is_garbage = any(re.search(pattern, project_title) for pattern in garbage_patterns)
        if is_garbage:
            continue
        
        # Skip headers/footers
        if ('DPWH' in project_title.upper() or 'TOTAL' in project_title.upper() or 
            'AMOUNT OF' in project_title.upper() or 'GAA PAGE' in project_title.upper()):
            continue
        
        # Must have at least one word with 3+ characters
        words = project_title.split()
        meaningful_words = [w for w in words if len(w) >= 3 and any(c.isalpha() for c in w)]
        if not meaningful_words:
            continue
        
        # Add row
        rows.append({
            'gaa_page': gaa_page,
            'project_title': project_title,
            'amount': amount
        })
    
    return rows
    # Column 1 (GAA Page): right-justified - text ends at similar x-positions
    # Column 2 (Project Title): left-justified - text starts at similar x-positions
    # Column 3 (Amount): right-justified - text ends at similar x-positions
    
    # Collect right edges (for right-justified columns) and left edges (for left-justified)
    right_edges = []  # For columns 1 and 3 (right-justified)
    left_edges = []   # For column 2 (left-justified)
    
    for y, words in sorted_lines:
        for left, right, text, height in words:
            if text.strip():
                right_edges.append(right)
                left_edges.append(left)
    
    # Find clusters of right edges (column 1 and 3 boundaries)
    # Also identify column 1 by finding natural numbers (GAA page numbers)
    col1_numbers = []  # Track positions of natural numbers (column 1)
    
    for y, words in sorted_lines:
        for left, right, text, height in words:
            text_clean = text.strip()
            if text_clean:
                # Check if it's a natural number (GAA page)
                if re.match(r'^\[?\d{1,4}\]?$', text_clean) or re.match(r'^\d{1,4}$', text_clean):
                    col1_numbers.append((left, right))
    
    if right_edges and left_edges:
        # Sort and find clusters
        right_edges_sorted = sorted(set(right_edges))
        left_edges_sorted = sorted(set(left_edges))
        
        # Find column 1 end by looking at where natural numbers end
        if col1_numbers:
            # Find the rightmost edge of natural numbers (column 1 end)
            col1_rights = [r for l, r in col1_numbers]
            col1_right_hist = {}
            for r in col1_rights:
                bin_r = r // 5
                col1_right_hist[bin_r] = col1_right_hist.get(bin_r, 0) + 1
            if col1_right_hist:
                col1_right_bin = max(col1_right_hist.items(), key=lambda x: x[1])[0]
                col1_end = col1_right_bin * 5 + 15  # Add padding
            else:
                col1_end = max(r for l, r in col1_numbers) + 10 if col1_numbers else image_width * 0.12
        else:
            # Fallback: find the leftmost right edge cluster (column 1 end)
            col1_right_candidates = [r for r in right_edges_sorted if r < image_width * 0.2]
            if col1_right_candidates:
                col1_right_hist = {}
                for r in right_edges:
                    if r < image_width * 0.2:
                        bin_r = r // 5
                        col1_right_hist[bin_r] = col1_right_hist.get(bin_r, 0) + 1
                if col1_right_hist:
                    col1_right_bin = max(col1_right_hist.items(), key=lambda x: x[1])[0]
                    col1_end = col1_right_bin * 5 + 10
                else:
                    col1_end = image_width * 0.12
            else:
                col1_end = image_width * 0.12
        
        # Find column 2 start by looking for words that start with uppercase letters
        col2_uppercase_starts = []  # Track positions of words starting with uppercase
        
        for y, words in sorted_lines:
            for left, right, text, height in words:
                text_clean = text.strip()
                if text_clean:
                    # Check if starts with uppercase letter (Project Title)
                    first_char = text_clean[0]
                    if first_char.isupper() and first_char.isalpha():
                        col2_uppercase_starts.append(left)
                    # Also check for common patterns
                    elif re.match(r'^[A-Z]', text_clean):
                        col2_uppercase_starts.append(left)
        
        # Find the leftmost left edge cluster after column 1 (column 2 start)
        if col2_uppercase_starts:
            # Filter uppercase starts that are after column 1
            col2_starts_after_col1 = [l for l in col2_uppercase_starts if l > col1_end]
            if col2_starts_after_col1:
                # Use the most common left edge of uppercase-starting words
                col2_left_hist = {}
                for l in col2_starts_after_col1:
                    if col1_end < l < image_width * 0.85:
                        bin_l = l // 5
                        col2_left_hist[bin_l] = col2_left_hist.get(bin_l, 0) + 1
                if col2_left_hist:
                    col2_start_bin = min(col2_left_hist.items(), key=lambda x: x[0])[0]
                    col2_start = col2_start_bin * 5
                else:
                    col2_start = min(col2_starts_after_col1) if col2_starts_after_col1 else col1_end + 20
            else:
                col2_start = col1_end + 20
        else:
            # Fallback: use left edges
            col2_left_candidates = [l for l in left_edges_sorted if l > col1_end]
            if col2_left_candidates:
                col2_left_hist = {}
                for l in left_edges:
                    if col1_end < l < image_width * 0.85:
                        bin_l = l // 5
                        col2_left_hist[bin_l] = col2_left_hist.get(bin_l, 0) + 1
                if col2_left_hist:
                    col2_start_bin = min(col2_left_hist.items(), key=lambda x: x[0])[0]
                    col2_start = col2_start_bin * 5
                else:
                    col2_start = col1_end + 20
            else:
                col2_start = col1_end + 20
        
        # Find the rightmost right edge cluster (column 3 end, near right edge)
        col3_right_candidates = [r for r in right_edges_sorted if r > image_width * 0.7]
        if col3_right_candidates:
            # Use the most common right edge in the last 30% of width
            col3_right_hist = {}
            for r in right_edges:
                if r > image_width * 0.7:
                    bin_r = r // 5
                    col3_right_hist[bin_r] = col3_right_hist.get(bin_r, 0) + 1
            if col3_right_hist:
                col3_right_bin = max(col3_right_hist.items(), key=lambda x: x[1])[0]
                col2_end = col3_right_bin * 5 - 10  # Column 2 ends before column 3 starts
            else:
                col2_end = image_width * 0.80
        else:
            col2_end = image_width * 0.80
        
        # Ensure col2_start > col1_end and col2_end > col2_start
        if col2_start <= col1_end:
            col2_start = col1_end + 20
        if col2_end <= col2_start:
            col2_end = image_width * 0.80
    else:
        # Fallback: use fixed percentages
        col1_end = image_width * 0.12
        col2_start = col1_end + 20
        col2_end = image_width * 0.80
    
    # Process each line
    current_row = {}
    header_processed = False
    header_y = None
    
    for y, words in sorted_lines:
        # Sort words by x-coordinate
        words.sort(key=lambda w: w[0])
        
        # Get line boundaries for bold detection
        line_x_start = min(w[0] for w in words)
        line_x_end = max(w[1] for w in words)
        line_height = max(w[3] for w in words) if words else 20
        
        # Separate into 3 columns
        col1_words = []  # GAA Page
        col2_words = []  # Project Title
        col3_words = []  # Amount
        
        for left, right, text, height in words:
            text_clean = text.strip()
            
            # Column 1: Contains natural numbers (GAA page numbers), right-justified
            is_gaa_number = False
            if text_clean:
                # Check for bracket format: [643] or [209]
                if re.match(r'^\[?\d{1,4}\]?$', text_clean):
                    is_gaa_number = True
                # Check if it's mostly digits (natural number)
                elif re.match(r'^\d{1,4}$', text_clean):
                    is_gaa_number = True
                # Check if it starts with digits in brackets
                elif re.match(r'^\[?\d{1,4}', text_clean):
                    is_gaa_number = True
            
            # Column 2: Starts with uppercase letter (Project Title)
            starts_with_uppercase = False
            if text_clean:
                first_char = text_clean[0]
                # Check if starts with uppercase letter (A-Z)
                if first_char.isupper() and first_char.isalpha():
                    starts_with_uppercase = True
                # Also check for common project title patterns
                elif re.match(r'^[A-Z]', text_clean):
                    starts_with_uppercase = True
            
            # Column 3: Contains large numbers with commas (Amount)
            is_amount = False
            if text_clean:
                # Check if it looks like an amount (large number with commas)
                if re.search(r'[\d,]{6,}', text_clean):
                    is_amount = True
            
            # Assign to columns based on characteristics and position
            # Column 1: natural numbers, right-justified, ends before col1_end
            if is_gaa_number or (right <= col1_end + 30 and not starts_with_uppercase and not is_amount):
                col1_words.append(text)
            # Column 2: starts with uppercase, left-justified, between col2_start and col2_end
            elif starts_with_uppercase or (left >= col2_start - 30 and left < col2_end and not is_amount):
                col2_words.append(text)
            # Column 3: amounts (large numbers), right-justified, near right edge
            elif is_amount or (left >= col2_end - 30 or right > image_width * 0.70):
                col3_words.append(text)
            # Fallback: assign based on position only
            elif left < col2_start:
                col1_words.append(text)
            elif left < col2_end:
                col2_words.append(text)
            else:
                col3_words.append(text)
        
        col1_text = ' '.join(col1_words).strip()
        col2_text = ' '.join(col2_words).strip()
        col3_text = ' '.join(col3_words).strip()
        
        # Check if this is a header row
        # Headers are in bold, so check for bold text AND header keywords
        combined_text = (col1_text + ' ' + col2_text + ' ' + col3_text).upper()
        col1_upper = col1_text.upper()
        col2_upper = col2_text.upper()
        col3_upper = col3_text.upper()
        
        # Detect bold text if table image is available
        is_bold = False
        if table_img is not None:
            is_bold = detect_bold_text_in_line(table_img, y, line_height, line_x_start, line_x_end)
        
        # Check for header row pattern
        # Headers are centered, bold, and contain header keywords
        is_header = False
        if not header_processed:
            # Check if text contains header keywords
            has_header_keywords = (
                ('GAA' in col1_upper or 'PAGE' in col1_upper) and 
                ('PROJECT' in col2_upper and 'TITLE' in col2_upper) and 
                'AMOUNT' in col3_upper
            ) or (
                ('GAA' in combined_text or 'PAGE' in combined_text) and 
                ('PROJECT' in combined_text and 'TITLE' in combined_text) and 
                'AMOUNT' in combined_text
            )
            
            # Check if text appears centered (for headers)
            # Centered text has words spread more evenly across columns
            is_centered = False
            if words:
                word_positions = [w[0] for w in words]
                if word_positions:
                    spread = max(word_positions) - min(word_positions)
                    # Centered text spreads across more of the width
                    is_centered = spread > image_width * 0.5
            
            # Header is: bold text OR centered text, with header keywords, in first few rows
            if has_header_keywords:
                if is_bold or is_centered or y < sorted_lines[0][0] + 100:
                    is_header = True
                    header_y = y
        
        if is_header:
            header_processed = True
            continue  # Skip header row
        
        # Extract GAA page from column 1 (GAA Page column)
        gaa_page = ""
        # First try brackets: [643] or [209]
        gaa_bracket_match = re.search(r'\[(\d{1,4})\]', col1_text)
        if gaa_bracket_match:
            gaa_page = gaa_bracket_match.group(1)
        else:
            # Try to extract digits (GAA page numbers are typically 2-4 digits)
            gaa_digits = re.sub(r'[^\d]', '', col1_text)
            if gaa_digits and 2 <= len(gaa_digits) <= 4:
                gaa_page = gaa_digits
            # Also check if there's a number at the start of column 2 (OCR might misplace it)
            elif not col1_text.strip() and col2_text:
                # Check if column 2 starts with a number in brackets or just digits
                gaa_bracket_match = re.search(r'^\[?(\d{1,4})\]?\s+', col2_text)
                if gaa_bracket_match:
                    gaa_page = gaa_bracket_match.group(1)
                    col2_text = col2_text[gaa_bracket_match.end():].strip()
        
        # Extract amount from column 3 (or column 2 if OCR misplaces it)
        amount = ""
        # Try column 3 first
        amount_match = re.search(r'([\d,]{6,})', col3_text)
        if amount_match:
            amount = amount_match.group(1).replace(',', '')
        else:
            # Sometimes amount is at the end of column 2
            amount_match = re.search(r'([\d,]{6,})\s*$', col2_text)
            if amount_match:
                amount = amount_match.group(1).replace(',', '')
                # Remove amount from title
                col2_text = col2_text[:amount_match.start()].strip()
        
        # Project title is column 2
        project_title = col2_text.strip()
        project_title = re.sub(r'^\W+', '', project_title)
        project_title = re.sub(r'\s+', ' ', project_title).strip()
        
        # Skip if no meaningful data
        if not project_title or len(project_title) < 3:
            # Might be continuation
            if current_row.get('project_title') and not amount:
                if col2_text:
                    current_row['project_title'] += ' ' + col2_text
            continue
        
        # Skip if looks like header, summary, or footer
        title_upper = project_title.upper()
        if ('DPWH' in title_upper or 'TOTAL' in title_upper or 
            'AMOUNT OF' in title_upper or 'PROJECTS' in title_upper and 'TOTAL' in combined_text):
            continue
        
        # Skip if this looks like a header row (contains all header keywords)
        if ('GAA' in combined_text or 'PAGE' in combined_text) and \
           ('PROJECT' in combined_text and 'TITLE' in combined_text) and \
           'AMOUNT' in combined_text:
            continue
        
        # If we have a current row and this line has an amount, save current row
        if current_row.get('project_title') and amount:
            rows.append(current_row)
            current_row = {}
        
        # Start or continue row
        if amount:
            # Complete row
            rows.append({
                'gaa_page': gaa_page or current_row.get('gaa_page', ''),
                'project_title': project_title,
                'amount': amount
            })
            current_row = {}
        else:
            # Incomplete row - might continue on next line
            if current_row.get('project_title'):
                current_row['project_title'] += ' ' + project_title
            else:
                current_row = {
                    'gaa_page': gaa_page,
                    'project_title': project_title,
                    'amount': ''
                }
    
    # Add any remaining row
    if current_row.get('project_title'):
        rows.append(current_row)
    
    return rows


def extract_table_from_boxes_old(data: Dict) -> List[Dict[str, str]]:
    """Extract table rows from OCR bounding box data with column detection."""
    rows = []
    
    # Group words by line (similar y-coordinates)
    lines = {}
    n_boxes = len(data['text'])
    
    for i in range(n_boxes):
        text = data['text'][i].strip()
        if not text or int(data['conf'][i]) < 20:  # Lower threshold to get more data
            continue
        
        y = int(data['top'][i])
        x = int(data['left'][i])
        width = int(data['width'][i])
        height = int(data['height'][i])
        
        # Group by y-coordinate (same line if within 20 pixels, accounting for height)
        line_key = None
        for key in lines.keys():
            if abs(key - y) < max(20, height * 0.5):
                line_key = key
                break
        
        if line_key is None:
            line_key = y
        
        if line_key not in lines:
            lines[line_key] = []
        
        lines[line_key].append((x, x + width, text))  # Store (left, right, text)
    
    # Sort lines by y-coordinate
    sorted_lines = sorted(lines.items())
    
    # Detect column boundaries by analyzing x-coordinates
    all_x_positions = []
    for y, words in sorted_lines:
        for left, right, text in words:
            all_x_positions.append(left)
    
    if all_x_positions:
        min_x = min(all_x_positions)
        max_x = max(all_x_positions)
        
        # More sophisticated column detection
        # Find clusters of x-positions (likely column starts)
        sorted_x = sorted(set(all_x_positions))
        if len(sorted_x) > 10:
            # Find gaps that indicate column boundaries
            gaps = []
            for i in range(len(sorted_x) - 1):
                gap = sorted_x[i+1] - sorted_x[i]
                if gap > 30:  # Significant gap indicates column boundary
                    gaps.append((sorted_x[i], gap))
            
            # Use gaps to define columns
            if gaps:
                col1_end = gaps[0][0] + 50 if gaps else 150
                if len(gaps) > 1:
                    col2_end = gaps[1][0] + 50
                else:
                    col2_end = max_x * 0.85
            else:
                col1_end = min(200, max_x * 0.15)
                col2_end = max_x * 0.85
        else:
            col1_end = min(150, max_x * 0.15)
            col2_end = max_x * 0.85
    else:
        col1_end = 150
        col2_end = 1000
    
    # Process each line
    current_row = {}
    for y, words in sorted_lines:
        # Sort words by x-coordinate (left to right)
        words.sort(key=lambda w: w[0])
        
        # Separate into columns
        col1_words = []  # GAA page
        col2_words = []  # Project title
        col3_words = []  # Amount
        
        for left, right, text in words:
            if left < col1_end:
                col1_words.append(text)
            elif left < col2_end:
                col2_words.append(text)
            else:
                col3_words.append(text)
        
        # Build row data
        col1_text = ' '.join(col1_words).strip()
        col2_text = ' '.join(col2_words).strip()
        col3_text = ' '.join(col3_words).strip()
        
        # Extract GAA page
        gaa_page = ""
        # Look for GAA in brackets: [643] or [209]
        gaa_bracket_match = re.search(r'\[(\d{1,4})\]', col1_text + ' ' + col2_text)
        if gaa_bracket_match:
            gaa_page = gaa_bracket_match.group(1)
            # Remove from text
            if gaa_bracket_match.group(0) in col1_text:
                col1_text = col1_text.replace(gaa_bracket_match.group(0), '').strip()
            if gaa_bracket_match.group(0) in col2_text:
                col2_text = col2_text.replace(gaa_bracket_match.group(0), '').strip()
        else:
            # Try digits only from first column
            gaa_digits = re.sub(r'[^\d]', '', col1_text)
            if gaa_digits and len(gaa_digits) <= 4 and len(gaa_digits) >= 2:
                gaa_page = gaa_digits
        
        # Extract amount
        amount = ""
        # Try column 3 first
        amount_match = re.search(r'([\d,]{6,})', col3_text)
        if amount_match:
            amount = amount_match.group(1).replace(',', '')
        else:
            # Try at end of column 2
            amount_match = re.search(r'([\d,]{6,})\s*$', col2_text)
            if amount_match:
                amount = amount_match.group(1).replace(',', '')
                col2_text = col2_text[:amount_match.start()].strip()
        
        # Build project title
        project_title = col2_text.strip()
        
        # Clean up title
        project_title = re.sub(r'^\W+', '', project_title)
        project_title = re.sub(r'\s+', ' ', project_title).strip()
        
        # Skip if no meaningful data
        if not project_title or len(project_title) < 3:
            # Might be continuation of previous row
            if current_row.get('project_title'):
                # Check if this looks like continuation (no amount, short text)
                if not amount and col2_text:
                    current_row['project_title'] += ' ' + col2_text
            continue
        
        # Skip header rows
        if 'DPWH' in project_title.upper() or 'Amount of' in project_title or 'Total' in project_title:
            continue
        
        # If we have a current row and this line has an amount, save current row
        if current_row.get('project_title') and amount:
            rows.append(current_row)
            current_row = {}
        
        # Start or continue row
        if amount:
            # Complete row
            rows.append({
                'gaa_page': gaa_page or current_row.get('gaa_page', ''),
                'project_title': project_title,
                'amount': amount
            })
            current_row = {}
        else:
            # Incomplete row - might continue on next line
            if current_row.get('project_title'):
                current_row['project_title'] += ' ' + project_title
            else:
                current_row = {
                    'gaa_page': gaa_page,
                    'project_title': project_title,
                    'amount': ''
                }
    
    # Add any remaining row
    if current_row.get('project_title'):
        rows.append(current_row)
    
    return rows


def parse_table_line(line: str) -> Optional[Dict[str, str]]:
    """Parse a single line to extract GAA page, project title, and amount."""
    line = line.strip()
    if not line:
        return None
    
    # Skip header lines
    if 'DPWH Projects' in line or 'Amount of' in line or 'Total' in line:
        return None
    
    # Extract amount at the end (look for numbers with commas or just numbers)
    amount_match = re.search(r'([\d,]+)\s*$', line)
    if not amount_match:
        return None
    
    amount = amount_match.group(1).replace(',', '').strip()
    if not amount or len(amount) < 6:  # Amounts should be at least 6 digits
        return None
    
    # Remove amount from line
    line_without_amount = line[:amount_match.start()].strip()
    
    # Extract GAA page - could be in brackets [85] or [209] or just at start
    gaa_page = ""
    
    # Pattern 1: GAA in brackets at start: [85] or [209]
    bracket_match = re.match(r'^\[(\d{1,4})\]\s*', line_without_amount)
    if bracket_match:
        gaa_page = bracket_match.group(1)
        line_without_amount = line_without_amount[bracket_match.end():].strip()
    else:
        # Pattern 2: Number at very start (1-4 digits) followed by space
        start_num_match = re.match(r'^(\d{1,4})\s+', line_without_amount)
        if start_num_match:
            potential_gaa = start_num_match.group(1)
            # Check if it's likely a GAA page (2-4 digits, or common patterns)
            if len(potential_gaa) >= 2 and len(potential_gaa) <= 4:
                gaa_page = potential_gaa
                line_without_amount = line_without_amount[start_num_match.end():].strip()
    
    # Clean up project title - remove OCR artifacts
    project_title = line_without_amount.strip()
    
    # Remove common OCR artifacts
    project_title = re.sub(r'^\W+', '', project_title)  # Remove leading non-word chars
    project_title = re.sub(r'\s+', ' ', project_title)  # Normalize whitespace
    project_title = project_title.strip()
    
    # Skip if title is too short or looks like garbage
    if len(project_title) < 5:
        return None
    
    return {
        'gaa_page': gaa_page,
        'project_title': project_title,
        'amount': amount
    }


def parse_table_text(text: str) -> List[Dict[str, str]]:
    """Parse OCR text to extract table rows, handling multi-line entries."""
    rows = []
    lines = text.split('\n')
    
    current_row = {}
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines and headers
        if not line or 'DPWH Projects' in line or 'Amount of' in line or 'Total' in line:
            i += 1
            continue
        
        # Extract GAA page from brackets: [643] or [637] or [209]
        gaa_match = re.search(r'\[(\d{1,4})\]', line)
        gaa_page = gaa_match.group(1) if gaa_match else ""
        
        # Remove GAA page from line
        if gaa_match:
            line = line[gaa_match.end():].strip()
        
        # Extract amount at the end
        amount_match = re.search(r'([\d,]+)\s*$', line)
        amount = ""
        project_title = ""
        
        if amount_match:
            amount = amount_match.group(1).replace(',', '').strip()
            project_title = line[:amount_match.start()].strip()
        else:
            # No amount on this line - might be a continuation
            project_title = line
        
        # Clean up project title
        project_title = re.sub(r'^\W+', '', project_title)  # Remove leading non-word
        project_title = re.sub(r'\s+', ' ', project_title).strip()
        
        # Check if this is a continuation of previous line
        if current_row.get('project_title') and not amount:
            # This line continues the previous title
            current_row['project_title'] += ' ' + project_title
            i += 1
            continue
        elif current_row.get('project_title') and amount:
            # Previous title is complete, this is a new row
            rows.append(current_row.copy())
            current_row = {}
        
        # Start new row
        if project_title and len(project_title) > 5:
            current_row = {
                'gaa_page': gaa_page or current_row.get('gaa_page', ''),
                'project_title': project_title,
                'amount': amount
            }
            
            # If we have amount, this row is complete
            if amount and len(amount) >= 6:
                rows.append(current_row)
                current_row = {}
        
        i += 1
    
    # Add any remaining row
    if current_row.get('project_title') and current_row.get('amount'):
        rows.append(current_row)
    
    return rows


def fuzzy_match_title(title1: str, title2: str, threshold: float = 0.5) -> bool:
    """Check if two titles are similar enough to be the same project."""
    # Normalize titles
    t1 = normalize_title_for_matching(title1)
    t2 = normalize_title_for_matching(title2)
    
    # Extract key words (3+ characters, excluding common words)
    common_words = {'the', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'along', 'road', 'rd'}
    words1 = set(w for w in re.findall(r'\w{3,}', t1.lower()) if w not in common_words)
    words2 = set(w for w in re.findall(r'\w{3,}', t2.lower()) if w not in common_words)
    
    if not words1 or not words2:
        return False
    
    # Calculate Jaccard similarity
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    similarity = intersection / union if union > 0 else 0
    
    # Also check for chainage markers match (strong indicator)
    chainages1 = set(re.findall(r'K\d+', t1.upper()))
    chainages2 = set(re.findall(r'K\d+', t2.upper()))
    if chainages1 and chainages2:
        chainage_match = len(chainages1.intersection(chainages2)) > 0
        if chainage_match:
            similarity += 0.3  # Boost for chainage match
    
    return similarity >= threshold


def normalize_title_for_matching(title: str) -> str:
    """Normalize title for matching."""
    # Remove leading numbers
    title = re.sub(r'^\d+\s*[.-]?\s*', '', title.strip())
    # Remove extra whitespace
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def create_new_csv_from_ocr(ocr_results: List[Dict[str, str]], output_path: Path) -> None:
    """Create a new CSV file from OCR results."""
    # Filter out invalid rows
    valid_rows = []
    for row in ocr_results:
        title = row.get('project_title', '').strip()
        amount = row.get('amount', '').strip()
        
        # Must have title (at least 3 chars) - amount is optional but preferred
        if title and len(title) >= 3:
            # If no amount, try to extract from title (sometimes OCR puts it there)
            if not amount or len(amount) < 6:
                amount_match = re.search(r'([\d,]{6,})', title)
                if amount_match:
                    amount = amount_match.group(1).replace(',', '')
                    # Remove amount from title
                    title = title[:amount_match.start()].strip()
            
            valid_rows.append({
                'project_title': title,
                'gaa_page': row.get('gaa_page', ''),
                'amount': amount
            })
    
    print(f"\n📝 Creating new CSV with {len(valid_rows)} valid rows from OCR")
    
    # Write new CSV
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['Project Title', 'GAA Page', 'Amount']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in valid_rows:
            # Format amount with commas
            amount = row.get('amount', '').replace(',', '')
            if amount:
                try:
                    amount_int = int(amount)
                    amount_formatted = f"{amount_int:,}"
                except ValueError:
                    amount_formatted = amount
            else:
                amount_formatted = ''
            
            writer.writerow({
                'Project Title': row.get('project_title', ''),
                'GAA Page': row.get('gaa_page', ''),
                'Amount': amount_formatted
            })
    
    print(f"✅ Created new CSV: {output_path}")


def compare_csvs(old_csv_path: Path, new_csv_path: Path) -> None:
    """Compare old and new CSV files."""
    print(f"\n📊 Comparing CSVs:")
    print(f"  Old: {old_csv_path}")
    print(f"  New: {new_csv_path}")
    
    # Read old CSV
    old_projects = []
    with open(old_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            old_projects.append(row)
    
    # Read new CSV
    new_projects = []
    with open(new_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            new_projects.append(row)
    
    print(f"\n  Old CSV: {len(old_projects)} rows")
    print(f"  New CSV: {len(new_projects)} rows")
    print(f"  Difference: {len(new_projects) - len(old_projects)} rows")
    
    # Find matches
    matched = 0
    new_only = 0
    old_only = 0
    
    old_titles = {normalize_title_for_matching(p.get('Project Title', '')): p for p in old_projects}
    new_titles = {normalize_title_for_matching(p.get('Project Title', '')): p for p in new_projects}
    
    for old_title_norm, old_proj in old_titles.items():
        found = False
        for new_title_norm, new_proj in new_titles.items():
            if fuzzy_match_title(old_title_norm, new_title_norm, threshold=0.5):
                found = True
                matched += 1
                old_gaa = old_proj.get('GAA Page', '').strip()
                new_gaa = new_proj.get('GAA Page', '').strip()
                if new_gaa and not old_gaa:
                    print(f"  ✅ Found GAA page for: {old_proj.get('Project Title', '')[:50]}... -> {new_gaa}")
                break
        if not found:
            old_only += 1
    
    for new_title_norm, new_proj in new_titles.items():
        found = False
        for old_title_norm in old_titles.keys():
            if fuzzy_match_title(old_title_norm, new_title_norm, threshold=0.5):
                found = True
                break
        if not found:
            new_only += 1
    
    print(f"\n  📈 Comparison Summary:")
    print(f"    Matched: {matched}")
    print(f"    Only in old CSV: {old_only}")
    print(f"    Only in new CSV: {new_only}")


def update_csv_with_ocr_results(csv_path: Path, ocr_results: List[Dict[str, str]]) -> None:
    """Update CSV file with GAA page numbers from OCR results."""
    # Read existing CSV
    projects = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            projects.append(row)
    
    print(f"\n📋 Found {len(projects)} projects in CSV")
    print(f"📋 Found {len(ocr_results)} rows from OCR")
    
    # Match OCR results to CSV projects
    matched = 0
    for project in projects:
        csv_title = project.get("Project Title", "").strip()
        csv_title_normalized = normalize_title_for_matching(csv_title)
        
        # Try to find matching OCR row
        best_match = None
        best_score = 0
        
        for ocr_row in ocr_results:
            ocr_title = ocr_row.get('project_title', '').strip()
            ocr_title_normalized = normalize_title_for_matching(ocr_title)
            
            # Calculate similarity
            words1 = set(re.findall(r'\w+', csv_title_normalized.lower()))
            words2 = set(re.findall(r'\w+', ocr_title_normalized.lower()))
            
            if words1 and words2:
                intersection = len(words1.intersection(words2))
                union = len(words1.union(words2))
                score = intersection / union if union > 0 else 0
                
                if score > best_score:
                    best_score = score
                    best_match = ocr_row
        
        # If we found a good match (similarity > 0.4), update GAA page
        if best_match and best_score > 0.4:
            gaa_page = best_match.get('gaa_page', '').strip()
            if gaa_page:
                old_gaa = project.get('GAA Page', '').strip()
                project['GAA Page'] = gaa_page
                matched += 1
                status = "🆕" if not old_gaa else "🔄" if old_gaa != gaa_page else "✅"
                print(f"  {status} Matched: {csv_title[:50]}... -> GAA Page: {gaa_page} (score: {best_score:.2f})")
            elif best_score > 0.6:
                # High confidence match but no GAA page - still log it
                print(f"  ⚠️  High match but no GAA: {csv_title[:50]}... (score: {best_score:.2f})")
    
    # Write updated CSV
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['Project Title', 'GAA Page', 'Amount']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for project in projects:
            writer.writerow({
                'Project Title': project.get('Project Title', ''),
                'GAA Page': project.get('GAA Page', ''),
                'Amount': project.get('Amount', '')
            })
    
    print(f"\n✅ Updated {matched} projects with GAA page numbers")


def main():
    """Main function."""
    script_dir = Path(__file__).resolve().parent.parent
    database_dir = script_dir / "database"
    
    # Find all z*.jpg images
    image_files = sorted(database_dir.glob("z*.jpg"))
    
    if not image_files:
        print("❌ No z*.jpg images found in database directory")
        return 1
    
    print(f"🔍 Found {len(image_files)} images to process")
    print()
    
    # OCR all images
    all_ocr_results = []
    for img_path in image_files:
        try:
            rows = extract_table_from_image(str(img_path))
            all_ocr_results.extend(rows)
            print(f"  ✅ Extracted {len(rows)} rows from {img_path.name}")
        except Exception as e:
            print(f"  ❌ Error processing {img_path.name}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n📊 Total rows extracted from OCR: {len(all_ocr_results)}")
    
    # Create new CSV from OCR results
    new_csv_path = database_dir / "dpwh-projects-ocr.csv"
    create_new_csv_from_ocr(all_ocr_results, new_csv_path)
    
    # Compare with old CSV
    old_csv_path = database_dir / "dpwh-projects.csv"
    if old_csv_path.exists():
        compare_csvs(old_csv_path, new_csv_path)
        
        # Also update old CSV with GAA pages where we can match
        update_csv_with_ocr_results(old_csv_path, all_ocr_results)
    else:
        print(f"⚠️  Old CSV not found: {old_csv_path}")
    
    print("\n🎉 OCR processing complete!")
    print(f"  • New CSV created: {new_csv_path}")
    print(f"  • Old CSV updated: {old_csv_path}")
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

