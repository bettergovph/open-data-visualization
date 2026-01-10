#!/usr/bin/env python3
"""
Build hierarchical JSON tree from CSV data.
Traverses rows and determines hierarchy based on which column the first data appears in.
"""

import sys
import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

def is_bullet(value: str) -> bool:
    """
    Check if a value is a bullet/numbering marker (like 'a.', '1.0', '2.0', etc.).
    Bullets are typically short (1-3 characters) and used for list numbering.
    
    Args:
        value: Cell value to check
    
    Returns:
        True if the value appears to be a bullet marker
    """
    if not value:
        return False
    
    value = value.strip()
    
    # Bullets are typically very short (1-4 characters max)
    # Long values are definitely not bullets (like amounts: '18371150000.0')
    if len(value) > 4:
        return False
    
    # Single letter followed by period (like 'a.', 'b.')
    if len(value) == 2 and value[-1] == '.' and value[0].isalpha():
        return True
    
    # Number followed by period (like '1.', '2.', '10.')
    if value[-1] == '.' and value[:-1].isdigit():
        return True
    
    # Number with decimal (like '1.0', '2.0', '10.0') - but only if short
    if '.' in value and len(value) <= 4:
        parts = value.split('.')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return True
    
    # Just a single character (like 'a', 'b', '1', '2')
    if len(value) == 1 and (value.isalpha() or value.isdigit()):
        return True
    
    return False

def find_hierarchy_info(row: List[str], start_col: int = 1) -> Optional[tuple]:
    """
    Find hierarchy level and value column in a row.
    If a bullet marker is found, the bullet's column determines hierarchy level,
    and the value is in the column immediately to the right.
    If no bullet is found, the first non-empty column is both level and value location.
    
    Args:
        row: List of cell values
        start_col: Column index to start searching from (default: 1)
    
    Returns:
        Tuple of (hierarchy_column, value_column) or None if row is empty
    """
    # First, look for bullet markers
    for i in range(start_col, len(row)):
        if row[i] and row[i].strip():
            value = row[i].strip()
            if is_bullet(value):
                # Found a bullet - hierarchy level is this column, value is next column
                value_col = i + 1
                if value_col < len(row) and row[value_col] and row[value_col].strip():
                    return (i, value_col)
                # Bullet found but no value in next column - skip this row
                return None
    
    # No bullet found - find first non-empty column (it's both level and value)
    for i in range(start_col, len(row)):
        if row[i] and row[i].strip():
            value = row[i].strip()
            # Make sure it's not a bullet (shouldn't happen, but just in case)
            if not is_bullet(value):
                return (i, i)
    
    return None

def parse_hierarchical_csv(csv_path: Path, value_column: int = 10, start_column: int = 1, row_range: tuple = None) -> List[Dict[str, Any]]:
    """
    Parse CSV file and build hierarchical tree structure.
    The hierarchy is determined by which column the first data appears in.
    Lower column numbers = higher in hierarchy (parent).
    Higher column numbers = lower in hierarchy (child).
    
    Args:
        csv_path: Path to CSV file
        value_column: Column index containing the value/amount (default: 10)
        start_column: Column index to start looking for data (default: 1)
        row_range: Optional tuple (start, end) to process only specific rows (1-indexed, inclusive)
    
    Returns:
        List of root nodes in the hierarchy
    """
    print(f"Reading CSV file: {csv_path}")
    
    root_nodes = []
    node_stack = []  # Stack to track current path in hierarchy (each element is a node)
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        
        for row_num, row in enumerate(reader, start=1):
            # Apply row range filter if specified
            if row_range:
                start_row, end_row = row_range
                if row_num < start_row or row_num > end_row:
                    continue
            
            # Skip completely empty rows
            if not any(cell and cell.strip() for cell in row):
                continue
            
            # Find hierarchy level and value column
            hierarchy_info = find_hierarchy_info(row, start_col=start_column)
            
            if hierarchy_info is None:
                # Row only contains bullets without values or is empty, skip
                continue
            
            hierarchy_col, value_col = hierarchy_info
            
            # Get the data value from the value column
            if value_col >= len(row) or not row[value_col]:
                continue
            
            data_value = row[value_col].strip()
            if not data_value:
                continue
            
            amount = None
            
            # Try to get amount from the amount column (typically column 10, index 10)
            if value_column < len(row) and row[value_column]:
                try:
                    amount_str = row[value_column].strip().replace(',', '')
                    if amount_str:
                        amount = float(amount_str)
                except (ValueError, AttributeError):
                    pass
            
            # Create node
            node = {
                "value": data_value,
                "amount": amount,
                "children": []
            }
            
            # Find the correct parent by going up the stack
            # We need to find the most recent node with a hierarchy column < current hierarchy column
            # This handles cases where levels skip (e.g., 0 -> 2, skipping 1)
            parent = None
            while node_stack:
                candidate = node_stack[-1]
                # Get the hierarchy column of the candidate
                candidate_col = candidate.get("_hierarchy_col", start_column)
                if candidate_col < hierarchy_col:
                    # This is a valid parent
                    parent = candidate
                    break
                else:
                    # This node is at same or deeper level, pop it
                    node_stack.pop()
            
            # Store hierarchy column for next iteration
            node["_hierarchy_col"] = hierarchy_col
            
            # Add node to appropriate parent
            if parent is None:
                # Root level node
                root_nodes.append(node)
            else:
                # Child node - add to parent's children
                parent["children"].append(node)
            
            # Push current node to stack
            node_stack.append(node)
            
            # Progress indicator
            if row_num % 10000 == 0:
                print(f"  Processed {row_num} rows...", end='\r')
    
    print(f"\n✓ Processed {row_num} rows")
    print(f"✓ Found {len(root_nodes)} root nodes")
    
    # Clean up temporary _hierarchy_col fields
    def clean_node(n):
        if "_hierarchy_col" in n:
            del n["_hierarchy_col"]
        for child in n["children"]:
            clean_node(child)
    
    for node in root_nodes:
        clean_node(node)
    
    return root_nodes

def count_nodes(nodes: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count nodes in the tree structure."""
    total = len(nodes)
    with_children = sum(1 for n in nodes if n["children"])
    with_amount = sum(1 for n in nodes if n["amount"] is not None)
    
    for node in nodes:
        child_counts = count_nodes(node["children"])
        total += child_counts["total"]
        with_children += child_counts["with_children"]
        with_amount += child_counts["with_amount"]
    
    return {
        "total": total,
        "with_children": with_children,
        "with_amount": with_amount
    }

def main():
    """Main function to build hierarchy."""
    # Get the script directory and project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "data"
    
    # Find CSV file in data directory
    csv_files = list(data_dir.glob("*.csv"))
    
    if not csv_files:
        print(f"Error: No CSV files found in {data_dir}")
        sys.exit(1)
    
    # Use the first CSV file found
    csv_file = csv_files[0]
    
    try:
        # Parse hierarchical structure
        # Value column is typically column K (index 10)
        # Start looking for data from column B (index 1)
        # For testing, you can specify a row range: row_range=(5, 104)
        hierarchy = parse_hierarchical_csv(csv_file, value_column=10, start_column=1, row_range=None)
        
        # Count nodes
        counts = count_nodes(hierarchy)
        print(f"\nTree Statistics:")
        print(f"  Total nodes: {counts['total']}")
        print(f"  Nodes with children: {counts['with_children']}")
        print(f"  Nodes with amounts: {counts['with_amount']}")
        
        # Output results
        output_file = data_dir / f"{csv_file.stem}_hierarchy.json"
        
        print(f"\nWriting hierarchy to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(hierarchy, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Hierarchy saved to {output_file}")
        
        # Print sample of first few levels
        print("\n" + "="*60)
        print("SAMPLE HIERARCHY (first 3 levels):")
        print("="*60)
        def print_sample(nodes, level=0, max_level=2, max_items=3):
            if level > max_level:
                return
            for i, node in enumerate(nodes[:max_items]):
                indent = "  " * level
                amount_str = f" (Amount: {node['amount']})" if node['amount'] else ""
                print(f"{indent}- Level {level}: {node['value'][:60]}{amount_str}")
                if node['children']:
                    print_sample(node['children'], level + 1, max_level, max_items)
            if len(nodes) > max_items:
                print(f"{'  ' * level}... ({len(nodes) - max_items} more)")
        
        print_sample(hierarchy)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
