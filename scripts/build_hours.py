#!/usr/bin/env python3
"""
Build hours.json - Analyze file dates and git commits to calculate hours spent per project
Uses Cursor usage data when available for accurate hour tracking
"""

import os
import json
import subprocess
import csv
import requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import re

# Project directories to analyze
PROJECT_DIRS = [
    ("/home/joebert/open-data-visualization", "visualization (probono)"),
    ("~/bettergov", "bettergov (probono)"),
    ("~/AI/kenchlightyear_web", "kenchlightyear_web"),
    ("~/AI/books", "books"),
    ("~/AI/awesh", "awesh"),
    ("~/AI/aiops", "aiops"),
]

def expand_path(path):
    """Expand ~ and resolve to absolute path"""
    return str(Path(path).expanduser().resolve())

def extract_date_from_filename(filename):
    """Extract date from filename patterns like YYYYMMDD, YYYY-MM-DD, etc."""
    # Pattern 1: YYYYMMDD
    match = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
    if match:
        try:
            return datetime.strptime(match.group(0), '%Y%m%d').date()
        except:
            pass
    
    # Pattern 2: YYYY-MM-DD
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if match:
        try:
            return datetime.strptime(match.group(0), '%Y-%m-%d').date()
        except:
            pass
    
    # Pattern 3: YYYY_MM_DD
    match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
    if match:
        try:
            return datetime.strptime(match.group(0), '%Y_%m_%d').date()
        except:
            pass
    
    return None

def get_file_modification_date(filepath):
    """Get file modification date"""
    try:
        return datetime.fromtimestamp(os.path.getmtime(filepath)).date()
    except:
        return None

def get_git_commits_for_file(filepath, project_dir):
    """Get git commit dates for a file"""
    commits = []
    try:
        # Get relative path from project root
        rel_path = os.path.relpath(filepath, project_dir)
        
        # Get git log for this file
        result = subprocess.run(
            ['git', 'log', '--format=%ai', '--', rel_path],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        # Parse ISO format date
                        dt = datetime.fromisoformat(line.replace(' +', '+').replace(' -', '-'))
                        commits.append(dt.date())
                    except:
                        pass
    except:
        pass
    
    return commits

def get_git_commits_by_date(project_dir):
    """Get all git commits grouped by date"""
    commits_by_date = defaultdict(list)
    
    try:
        result = subprocess.run(
            ['git', 'log', '--format=%ai|%s', '--all'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if '|' in line:
                    date_str, message = line.split('|', 1)
                    try:
                        dt = datetime.fromisoformat(date_str.replace(' +', '+').replace(' -', '-'))
                        commits_by_date[dt.date()].append({
                            'time': dt,
                            'message': message
                        })
                    except:
                        pass
    except:
        pass
    
    return commits_by_date

def get_cursor_cookie():
    """Get Cursor session cookie from various sources"""
    # 1. Check environment variable
    cookie = (os.environ.get('CURSOR_SESSION_COOKIE') or 
              os.environ.get('CURSOR_COOKIE') or
              os.environ.get('WORKOS_CURSOR_SESSION_TOKEN'))
    if cookie:
        return cookie
    
    # 2. Check for cookie file
    cookie_file = Path.home() / '.cursor_cookie'
    if cookie_file.exists():
        try:
            cookie_value = cookie_file.read_text().strip()
            # Handle full cookie format: WorkosCursorSessionToken=value
            if '=' in cookie_value:
                return cookie_value
            else:
                return f'WorkosCursorSessionToken={cookie_value}'
        except:
            pass
    
    # 3. Check in project directory
    cookie_file = Path('cursor_cookie.txt')
    if cookie_file.exists():
        try:
            cookie_value = cookie_file.read_text().strip()
            # Handle full cookie format: WorkosCursorSessionToken=value
            if '=' in cookie_value:
                return cookie_value
            else:
                return f'WorkosCursorSessionToken={cookie_value}'
        except:
            pass
    
    return None

def download_cursor_usage(start_date_ms, end_date_ms):
    """Download Cursor usage data from API"""
    url = f"https://cursor.com/api/dashboard/export-usage-events-csv?startDate={start_date_ms}&endDate={end_date_ms}&strategy=tokens"
    
    usage_by_date = defaultdict(float)
    
    # Get cookie
    session_cookie = get_cursor_cookie()
    
    if not session_cookie:
        print(f"   ⚠️  No Cursor session cookie found")
        print(f"   💡 To get your cookie:")
        print(f"      1. Open Cursor/Perplexity browser")
        print(f"      2. Go to cursor.com and log in")
        print(f"      3. Open Developer Tools (F12)")
        print(f"      4. Go to Application/Storage > Cookies > cursor.com")
        print(f"      5. Find 'WorkosCursorSessionToken' or 'session' cookie and copy its value")
        print(f"      6. Set it as: export CURSOR_SESSION_COOKIE='WorkosCursorSessionToken=value'")
        print(f"         OR save it to ~/.cursor_cookie or cursor_cookie.txt")
        return {}
    
    # Try using requests first
    try:
        from datetime import datetime as dt
        start_dt = dt.fromtimestamp(start_date_ms / 1000)
        end_dt = dt.fromtimestamp(end_date_ms / 1000)
        print(f"📥 Downloading Cursor usage data...")
        print(f"   📅 Date range: {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}")
        print(f"   🔗 URL: {url[:100]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/csv',
            'Referer': 'https://cursor.com/dashboard'
        }
        
        # Set cookie - handle different formats
        if '=' in session_cookie:
            # Full cookie string like "WorkosCursorSessionToken=abc123" or "session=abc123"
            headers['Cookie'] = session_cookie
        else:
            # Just the cookie value - try WorkosCursorSessionToken first (newer format)
            headers['Cookie'] = f'WorkosCursorSessionToken={session_cookie}'
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse CSV
        csv_data = response.text
        if not csv_data.strip():
            print(f"   ⚠️  Empty response from Cursor API")
            return {}
        
        reader = csv.DictReader(csv_data.splitlines())
        
        for row in reader:
            # Parse timestamp - Cursor CSV format may vary
            timestamp_str = (row.get('timestamp') or row.get('time') or 
                           row.get('date') or row.get('created_at') or
                           row.get('Timestamp') or row.get('Time') or
                           row.get('Date'))
            
            if not timestamp_str:
                continue
            
            try:
                # Try various timestamp formats
                dt = None
                
                # Try ISO format
                try:
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except:
                    pass
                
                # Try Unix timestamp (milliseconds)
                if not dt:
                    try:
                        ts = float(timestamp_str) / 1000
                        dt = datetime.fromtimestamp(ts)
                    except:
                        pass
                
                # Try common date formats
                if not dt:
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                        try:
                            dt = datetime.strptime(timestamp_str.split('.')[0], fmt)
                            break
                        except:
                            continue
                
                if not dt:
                    continue
                
                date = dt.date()
                
                # Get duration/hours - Cursor may track actual time
                duration = (row.get('duration') or row.get('time_spent') or 
                           row.get('hours') or row.get('Duration') or
                           row.get('Hours'))
                
                if duration:
                    try:
                        hours = float(duration)
                        usage_by_date[date] += hours
                        continue
                    except:
                        pass
                
                # Estimate from tokens
                tokens = (row.get('tokens') or row.get('token_count') or 
                         row.get('Tokens') or row.get('tokenCount'))
                
                if tokens:
                    try:
                        # Rough estimate: tokens used indicate work done
                        # 10,000 tokens ≈ 1 hour of coding work
                        hours = float(tokens) / 10000
                        usage_by_date[date] += hours
                        continue
                    except:
                        pass
                
                # Estimate from events - each event is some work
                # Default: 0.25 hours per event (15 minutes)
                usage_by_date[date] += 0.25
                
            except Exception as e:
                continue
        
        # Cap each day at 16 hours (human limit)
        for date in usage_by_date:
            usage_by_date[date] = min(usage_by_date[date], 16.0)
        
        print(f"   ✅ Loaded usage data for {len(usage_by_date)} days")
        return usage_by_date
        
    except ImportError:
        print(f"   ⚠️  requests library not available, trying curl...")
        # Fallback to curl
        try:
            cookie_header = f"session={session_cookie}" if session_cookie else ""
            curl_cmd = ['curl', '-s', '-H', f'Cookie: {cookie_header}', url]
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout:
                csv_data = result.stdout
                # Parse CSV same way as requests version
                reader = csv.DictReader(csv_data.splitlines())
                for row in reader:
                    # Same parsing logic as above (would need to duplicate)
                    pass
        except Exception as e:
            print(f"   ⚠️  Curl also failed: {e}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"   ⚠️  Authentication failed - cookie may be expired")
            print(f"   💡 Please update your CURSOR_SESSION_COOKIE")
        else:
            print(f"   ⚠️  HTTP error: {e}")
    except Exception as e:
        print(f"   ⚠️  Could not download Cursor usage data: {e}")
        print(f"   💡 Tip: Check your cookie or download CSV manually from cursor.com/dashboard")
    
    return usage_by_date

def estimate_hours_from_commits(commits_by_date, cursor_usage=None):
    """Estimate hours based on commit patterns and Cursor usage"""
    hours_by_date = defaultdict(float)
    
    for date, commits in commits_by_date.items():
        # Sort commits by time
        sorted_commits = sorted(commits, key=lambda x: x['time'])
        
        if not sorted_commits:
            continue
        
        # Calculate time span of commits on this day
        first_commit = sorted_commits[0]['time']
        last_commit = sorted_commits[-1]['time']
        
        # Time difference in hours
        time_diff = (last_commit - first_commit).total_seconds() / 3600
        
        commit_count = len(commits)
        
        # If we have Cursor usage data, use it as base
        if cursor_usage and date in cursor_usage:
            cursor_hours = cursor_usage[date]
            # Combine with commit-based estimation
            # Cursor data is primary, commits add context
            estimated_hours = max(cursor_hours, time_diff + (commit_count * 0.3))
            # Cap at 16 hours (human limit)
            estimated_hours = min(estimated_hours, 16.0)
        else:
            # No Cursor data - estimate from commits
            # Realistic range: 4-16 hours per day (human work day, not AI)
            # Cap at 24 hours maximum (human limit)
            
            # Base hours from time span between first and last commit
            # If commits span a long time, that's actual work time
            base_hours = time_diff
            
            # Add hours per commit (more commits = more work)
            # Each commit represents work, but don't overestimate
            commit_hours = min(commit_count * 0.5, 8.0)  # Max 8 hours from commits alone
            
            # Total estimation
            estimated_hours = base_hours + commit_hours
            
            # If commits span less than 4 hours but we have commits, assume at least 4 hours
            if time_diff < 4.0 and commit_count > 0:
                estimated_hours = max(estimated_hours, 4.0)
            
            # If we have many commits but short time span, likely intensive work session
            if commit_count >= 5 and time_diff < 2.0:
                estimated_hours = max(estimated_hours, 6.0)
            
            # Cap at realistic maximum: 16 hours (very long day, but human limit)
            estimated_hours = min(estimated_hours, 16.0)
        
        hours_by_date[date] = estimated_hours
    
    return hours_by_date

def analyze_project(project_path, project_name, cursor_usage=None, target_year=None, apply_cursor_directly=False):
    """Analyze a project directory"""
    project_path = expand_path(project_path)
    
    if not os.path.exists(project_path):
        print(f"⚠️  Project directory not found: {project_path}")
        return []
    
    print(f"📁 Analyzing project: {project_name} ({project_path})")
    
    hours_data = []
    
    # Get git commits by date
    all_commits_by_date = get_git_commits_by_date(project_path)
    
    # Filter commits by year if specified (for hours estimation)
    commits_by_date = all_commits_by_date
    if target_year:
        filtered_commits = defaultdict(list)
        for date, commits in all_commits_by_date.items():
            if date.year == target_year:
                filtered_commits[date] = commits
        commits_by_date = filtered_commits
    
    # Only apply Cursor usage directly if explicitly requested
    # Otherwise, it will be applied proportionally in main()
    cursor_for_this_project = cursor_usage if apply_cursor_directly else None
    hours_from_commits = estimate_hours_from_commits(commits_by_date, cursor_for_this_project)
    
    # Also analyze files
    file_dates = defaultdict(list)
    
    # Walk through project directory
    for root, dirs, files in os.walk(project_path):
        # Skip hidden directories and common ignore patterns
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'target', '.git']]
        
        for filename in files:
            # Skip hidden files and common ignore patterns
            if filename.startswith('.'):
                continue
            
            filepath = os.path.join(root, filename)
            
            # Try to extract date from filename
            filename_date = extract_date_from_filename(filename)
            
            # Get modification date
            mod_date = get_file_modification_date(filepath)
            
            # Use filename date if available, otherwise use modification date
            file_date = filename_date or mod_date
            
            if file_date:
                # Filter by year if specified
                if target_year and file_date.year != target_year:
                    continue
                file_dates[file_date].append(filepath)
    
    # Combine file dates and commit dates
    all_dates = set(hours_from_commits.keys()) | set(file_dates.keys())
    
    # Only use Cursor usage if explicitly requested for this project
    if cursor_for_this_project:
        # Filter Cursor usage by year
        filtered_cursor = {date: hours for date, hours in cursor_for_this_project.items() if date.year == target_year}
        all_dates.update(filtered_cursor.keys())
        cursor_for_this_project = filtered_cursor
    
    for date in sorted(all_dates):
        # Filter by year
        if target_year and date.year != target_year:
            continue
        
        # Start with hours from commits (which may include Cursor data if apply_cursor_directly)
        hours = hours_from_commits.get(date, 0.0)
        
        # If we have Cursor usage but no commits, use Cursor data directly (only if apply_cursor_directly)
        if hours == 0.0 and cursor_for_this_project and date in cursor_for_this_project:
            hours = cursor_for_this_project[date]
        
        # If we have files modified on this date but no commits/Cursor data, estimate 4-8 hours
        if date in file_dates and hours == 0.0:
            # More files = more work, but be realistic
            file_count = len(file_dates.get(date, []))
            hours = min(4.0 + (file_count * 0.1), 8.0)
            # Cap at 16 hours (human limit)
            hours = min(hours, 16.0)
        
        if hours > 0:
            # Final safety check: cap at 16 hours (human limit)
            hours = min(hours, 16.0)
            hours_data.append({
                'project': project_name,
                'date': date.isoformat(),
                'hours': round(hours, 2),
                'files_count': len(file_dates.get(date, []))
            })
    
    print(f"   ✅ Found {len(hours_data)} days with activity")
    return hours_data

def main():
    """Main function to build hours.json"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Build hours.json from git commits and Cursor usage')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                       help='Filter by year (default: current year)')
    args = parser.parse_args()
    
    target_year = args.year
    
    print(f"🚀 Building hours.json for year {target_year}...")
    print()
    
    # Download Cursor usage data (January 1 of target year to December 31)
    start_date = datetime(target_year, 1, 1)
    end_date = datetime(target_year, 12, 31, 23, 59, 59)
    
    # If current year, use today as end date
    if target_year == datetime.now().year:
        end_date = datetime.now()
    
    start_date_ms = int(start_date.timestamp() * 1000)
    end_date_ms = int(end_date.timestamp() * 1000)
    
    cursor_usage = download_cursor_usage(start_date_ms, end_date_ms)
    print()
    
    all_hours = []
    
    # Analyze each project (without Cursor data first to get actual work per project)
    project_hours_list = []
    for project_path, project_name in PROJECT_DIRS:
        project_hours = analyze_project(project_path, project_name, None, target_year)
        project_hours_list.append((project_name, project_hours))
    
    # Now apply Cursor usage data proportionally based on actual work per project
    # Only apply to projects that have activity, and split proportionally
    if cursor_usage:
        from datetime import date as date_type, timedelta
        
        # Calculate work per day per project (using date strings for consistency)
        daily_work = defaultdict(lambda: defaultdict(float))
        for project_name, project_hours in project_hours_list:
            for entry in project_hours:
                date_str = entry['date']
                daily_work[date_str][project_name] += entry['hours']
        
        # Apply Cursor data proportionally to projects with activity
        for cursor_date, cursor_hours in cursor_usage.items():
            if cursor_date.year != target_year:
                continue
            
            date_str = cursor_date.isoformat()
            
            if date_str in daily_work:
                # Calculate total work across all projects for this day
                total_work = sum(daily_work[date_str].values())
                if total_work > 0:
                    # Split Cursor hours proportionally based on actual work
                    for project_name in daily_work[date_str]:
                        project_ratio = daily_work[date_str][project_name] / total_work
                        additional_hours = cursor_hours * project_ratio
                        
                        # Add to the project's hours for that day
                        for project_name_check, project_hours in project_hours_list:
                            if project_name_check == project_name:
                                for entry in project_hours:
                                    if entry['date'] == date_str:
                                        entry['hours'] = min(entry['hours'] + additional_hours, 16.0)
                                        break
                else:
                    # No work tracked in any project, but Cursor shows activity
                    # For past 3 months, attribute to "visualization (probono)" (main project)
                    three_months_ago = datetime.now() - timedelta(days=90)
                    if cursor_date >= three_months_ago.date():
                        # Attribute to "visualization (probono)"
                        for project_name_check, project_hours in project_hours_list:
                            if project_name_check == "visualization (probono)":
                                # Check if entry exists for this date
                                found = False
                                for entry in project_hours:
                                    if entry['date'] == date_str:
                                        entry['hours'] = min(entry['hours'] + cursor_hours, 16.0)
                                        found = True
                                        break
                                if not found:
                                    # Create new entry (no commits since no git activity tracked)
                                    project_hours.append({
                                        'project': 'visualization (probono)',
                                        'date': date_str,
                                        'hours': min(cursor_hours, 16.0),
                                        'files_count': 0
                                    })
                                break
    
    # Flatten all hours
    for project_name, project_hours in project_hours_list:
        all_hours.extend(project_hours)
    
    # Cap total hours per day across all projects at 16 hours
    from datetime import date as date_type
    hours_by_date = defaultdict(float)
    for entry in all_hours:
        entry_date = entry['date']
        hours_by_date[entry_date] += entry['hours']
    
    # If a day exceeds 16 hours, scale down proportionally
    for date_str, total_hours in hours_by_date.items():
        if total_hours > 16.0:
            scale_factor = 16.0 / total_hours
            for entry in all_hours:
                if entry['date'] == date_str:
                    entry['hours'] = round(entry['hours'] * scale_factor, 2)
    
    # Sort by date (newest first)
    all_hours.sort(key=lambda x: x['date'], reverse=True)
    
    # Calculate totals
    total_hours = sum(item['hours'] for item in all_hours)
    hours_by_project = defaultdict(float)
    for item in all_hours:
        hours_by_project[item['project']] += item['hours']
    
    # Build output structure
    output = {
        'generated_at': datetime.now().isoformat(),
        'year': target_year,
        'total_hours': round(total_hours, 2),
        'projects': dict(hours_by_project),
        'entries': all_hours
    }
    
    # Write to file
    output_path = Path('static/data/hours.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"✅ Generated hours.json for year {target_year}")
    print(f"   📊 Total hours: {total_hours:.2f}")
    print(f"   📁 Projects: {len(hours_by_project)}")
    print(f"   📅 Days tracked: {len(all_hours)}")
    print(f"   💾 Saved to: {output_path}")
    
    # Print project breakdown
    print()
    print("📊 Hours by project:")
    for project, hours in sorted(hours_by_project.items(), key=lambda x: x[1], reverse=True):
        print(f"   {project}: {hours:.2f} hours")

if __name__ == '__main__':
    main()


