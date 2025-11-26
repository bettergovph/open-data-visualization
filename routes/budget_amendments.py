"""
Budget Amendments API Routes
Serves FY 2026 budget amendment data from parsed JSON.
"""

from flask import Blueprint, jsonify, request
import json
from pathlib import Path

bp = Blueprint('budget_amendments', __name__, url_prefix='/api/budget/amendments')

# Cache for JSON data
_data_cache = None

def load_amendments_data():
    """Load amendments data from JSON file"""
    global _data_cache
    
    if _data_cache is not None:
        return _data_cache
    
    json_path = Path('static/data/budget_amendments_2026.json')
    
    if not json_path.exists():
        return None
    
    with open(json_path, 'r', encoding='utf-8') as f:
        _data_cache = json.load(f)
    
    return _data_cache

@bp.route('/summary')
def get_summary():
    """Get high-level summary statistics"""
    data = load_amendments_data()
    
    if not data:
        return jsonify({
            "success": False,
            "error": "Data not available"
        }), 404
    
    return jsonify({
        "success": True,
        **data['metadata']
    })

@bp.route('/departments')
def get_departments():
    """Get all departments with budget summary"""
    data = load_amendments_data()
    
    if not data:
        return jsonify({
            "success": False,
            "error": "Data not available"
        }), 404
    
    # Sort by original amount descending
    departments = sorted(
        data['departments'],
        key=lambda d: d.get('original_amount', 0),
        reverse=True
    )
    
    return jsonify({
        "success": True,
        "departments": departments,
        "metadata": data['metadata']
    })

@bp.route('/department/<dept_id>')
def get_department_details(dept_id):
    """Get programs within a department"""
    data = load_amendments_data()
    
    if not data:
        return jsonify({
            "success": False,
            "error": "Data not available"
        }), 404
    
    # Find department
    department = next(
        (d for d in data['departments'] if d['id'] == dept_id),
        None
    )
    
    if not department:
        return jsonify({
            "success": False,
            "error": "Department not found"
        }), 404
    
    # Filter programs by department
    programs = [
        p for p in data.get('programs', [])
        if p.get('department_id') == dept_id
    ]
    
    return jsonify({
        "success": True,
        "department": department,
        "programs": programs
    })

@bp.route('/search')
def search_amendments():
    """Full-text search across departments, programs, and projects"""
    data = load_amendments_data()
    
    if not data:
        return jsonify({
            "success": False,
            "error": "Data not available"
        }), 404
    
    query = request.args.get('q', '').lower()
    
    if not query:
        return jsonify({
            "success": True,
            "query": query,
            "results": []
        })
    
    results = []
    
    # Search departments
    for dept in data['departments']:
        if query in dept['name'].lower() or query in dept['code'].lower():
            results.append({
                "type": "department",
                "id": dept['id'],
                "name": dept['name'],
                "code": dept['code'],
                "amount": dept['final_amount']
            })
    
    # Search programs
    for prog in data.get('programs', []):
        if query in prog.get('name', '').lower():
            results.append({
                "type": "program",
                "id": prog['id'],
                "name": prog['name'],
                "department_id": prog.get('department_id'),
                "amount": prog.get('final_amount', 0)
            })
    
    # Search projects
    for proj in data.get('projects', []):
        if query in proj.get('name', '').lower():
            results.append({
                "type": "project",
                "id": proj['id'],
                "name": proj['name'],
                "department_id": proj.get('department_id'),
                "amount": proj.get('final_amount', 0)
            })
    
    return jsonify({
        "success": True,
        "query": query,
        "results": results[:50]  # Limit to 50 results
    })
