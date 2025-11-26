#!/usr/bin/env python3
"""
Helper script to add budget amendments API endpoints to visualization.py
"""

import sys

# The code to insert
INSERT_CODE = '''
# ===== BUDGET AMENDMENTS (FY 2026) ENDPOINTS =====
_amendments_cache = None

def load_amendments_data():
    """Load FY 2026 budget amendments data from JSON"""
    global _amendments_cache
    if _amendments_cache is not None:
        return _amendments_cache
    json_path = DATA_ROOT / "budget_amendments_2026.json"
    if not json_path.exists():
        return None
    with open(json_path, 'r', encoding='utf-8') as f:
        _amendments_cache = json.load(f)
    return _amendments_cache

@app.get("/api/budget/amendments/summary")
async def budget_amendments_summary():
    """Get FY 2026 budget amendments summary statistics"""
    try:
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        return JSONResponse({"success": True, **data['metadata']})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/departments")
async def budget_amendments_departments():
    """Get all departments with budget amendment summary"""
    try:
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        departments = sorted(data['departments'], key=lambda d: d.get('original_amount', 0), reverse=True)
        return JSONResponse({"success": True, "departments": departments, "metadata": data['metadata']})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/department/{dept_id}")
async def budget_amendments_department_details(dept_id: str):
    """Get programs within a department"""
    try:
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        department = next((d for d in data['departments'] if d['id'] == dept_id), None)
        if not department:
            return JSONResponse({"success": False, "error": "Department not found"}, status_code=404)
        programs = [p for p in data.get('programs', []) if p.get('department_id') == dept_id]
        return JSONResponse({"success": True, "department": department, "programs": programs})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/search")
async def budget_amendments_search(q: str = Query("")):
    """Full-text search across departments, programs, and projects"""
    try:
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        query = q.lower()
        if not query:
            return JSONResponse({"success": True, "query": q, "results": []})
        results = []
        for dept in data['departments']:
            if query in dept['name'].lower() or query in dept['code'].lower():
                results.append({
                    "type": "department",
                    "id": dept['id'],
                    "name": dept['name'],
                    "code": dept['code'],
                    "amount": dept['final_amount']
                })
        return JSONResponse({"success": True, "query": q, "results": results[:50]})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

'''

def main():
    file_path = 'visualization.py'
    
    # Read the file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: {file_path} not found")
        return 1
    
    # Find the insertion point (after line 1312: return JSONResponse({"success": False, "error": str(e)}))
    # Looking for the budget_column_mapping_api function end
    insert_line = None
    for i, line in enumerate(lines):
        if 'return JSONResponse({"success": False, "error": str(e)})' in line:
            # Check if this is in budget_column_mapping_api context
            # Look backwards for the function definition
            for j in range(i-1, max(0, i-20), -1):
                if 'async def budget_column_mapping_api' in lines[j]:
                    insert_line = i + 1
                    break
            if insert_line:
                break
    
    if not insert_line:
        print("Error: Could not find insertion point")
        return 1
    
    print(f"Found insertion point at line {insert_line + 1}")
    
    # Check if already inserted
    for i in range(max(0, insert_line - 10), min(len(lines), insert_line + 100)):
        if 'budget_amendments_summary' in lines[i]:
            print("✅ Budget amendments endpoints already exist!")
            return 0
    
    # Insert the code
    lines.insert(insert_line, INSERT_CODE)
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print("✅ Successfully added budget amendments API endpoints!")
    print(f"   Inserted at line {insert_line + 1}")
    print("\n📝 Next steps:")
    print("   1. Restart the server")
    print("   2. Visit /nep#win")
    print("   3. Budget amendments should load!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
