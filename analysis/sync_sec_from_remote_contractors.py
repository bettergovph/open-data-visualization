"""
Sync SEC numbers from remote Meilisearch contractors index to local SEC database
Fetches contractor data from remote HTTPS instance and updates local PostgreSQL SEC database
"""

import os
import asyncio
import asyncpg
import requests
import json
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')

# Remote Meilisearch configuration
REMOTE_ADDR = os.getenv('MEILI_HTTPS_ADDR', '')
REMOTE_KEY = os.getenv('MEILI_MASTER_KEY', '')

if not REMOTE_ADDR:
    print("❌ MEILI_HTTPS_ADDR not set")
    exit(1)

if not REMOTE_KEY:
    print("❌ MEILI_MASTER_KEY not set")
    exit(1)

# Ensure remote URL has protocol
if not REMOTE_ADDR.startswith('http'):
    REMOTE_URL = f"https://{REMOTE_ADDR}"
else:
    REMOTE_URL = REMOTE_ADDR

# PostgreSQL SEC database configuration
SEC_DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB_SEC', 'sec'),
    'user': os.getenv('POSTGRES_USER', 'your_database_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'your_database_password')
}

def make_remote_request(endpoint: str, params: Dict = None) -> Optional[Dict]:
    """Make a request to remote Meilisearch instance"""
    url = f"{REMOTE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {REMOTE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error querying remote: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"   Error details: {error_data}")
            except:
                print(f"   Response: {e.response.text}")
        return None

async def get_db_connection():
    """Get PostgreSQL database connection"""
    try:
        conn = await asyncpg.connect(**SEC_DB_CONFIG)
        return conn
    except Exception as e:
        print(f"💥 [PostgreSQL] Error connecting to SEC database: {e}")
        return None

def normalize_contractor_name(name: str) -> str:
    """Normalize contractor name for matching"""
    if not name:
        return ""
    
    # Convert to uppercase and remove extra spaces
    normalized = name.upper().strip()
    
    # Remove common suffixes
    suffixes = [
        ' INC', ' INC.', ' INCORPORATED',
        ' CORP', ' CORP.', ' CORPORATION', 
        ' CO', ' CO.', ' COMPANY',
        ' LTD', ' LTD.', ' LIMITED',
        ' LLC', ' L.L.C.',
        ' ENTERPRISES', ' ENTERPRISE',
        ' CONSTRUCTION', ' CONSTRUCTION CO',
        ' BUILDERS', ' BUILDER',
        ' ENGINEERING', ' ENGINEERING CO',
        ' SERVICES', ' SERVICE',
        ' GROUP', ' GROUP OF COMPANIES',
        ' PHILIPPINES', ' PHILS',
        ' & ASSOCIATES', ' ASSOCIATES',
        ' & PARTNERS', ' PARTNERS',
        ' & SONS', ' SONS',
        ' & CO', ' & CO.',
    ]
    
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
            break
    
    # Remove punctuation and extra spaces
    normalized = ' '.join(normalized.split())
    
    return normalized

def fuzzy_match_name(name1: str, name2: str, threshold: float = 0.85) -> bool:
    """Check if two contractor names are similar enough to be the same company"""
    if not name1 or not name2:
        return False
    
    norm1 = normalize_contractor_name(name1)
    norm2 = normalize_contractor_name(name2)
    
    if norm1 == norm2:
        return True
    
    # Simple similarity check (can be improved with more sophisticated algorithms)
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    if not words1 or not words2:
        return False
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    similarity = len(intersection) / len(union) if union else 0
    return similarity >= threshold

async def fetch_all_remote_contractors() -> List[Dict[str, Any]]:
    """Fetch all contractors from remote Meilisearch instance"""
    print("📥 Fetching all contractors from remote Meilisearch...")
    
    all_contractors = []
    limit = 1000
    offset = 0
    
    while True:
        print(f"   Fetching batch {offset//limit + 1}...")
        
        # Search with empty query to get all documents
        search_params = {
            'q': '',
            'limit': limit,
            'offset': offset
        }
        
        result = make_remote_request('/indexes/contractors/search', search_params)
        
        if not result:
            print("❌ Failed to fetch contractors from remote")
            break
        
        contractors = result.get('hits', [])
        if not contractors:
            break
        
        all_contractors.extend(contractors)
        offset += limit
        
        print(f"   Retrieved {len(contractors)} contractors (total: {len(all_contractors)})")
        
        # Check if we've got all results
        if len(contractors) < limit:
            break
    
    print(f"✅ Total contractors fetched: {len(all_contractors)}")
    return all_contractors

async def get_local_contractors_without_sec(conn) -> List[Dict[str, Any]]:
    """Get local contractors that don't have SEC numbers"""
    query = """
    SELECT 
        id,
        contractor_name,
        sec_number,
        status,
        address,
        created_at,
        updated_at
    FROM contractors 
    WHERE sec_number IS NULL OR sec_number = ''
    ORDER BY contractor_name
    """
    
    rows = await conn.fetch(query)
    contractors = []
    
    for row in rows:
        contractors.append({
            'id': row['id'],
            'contractor_name': row['contractor_name'],
            'sec_number': row['sec_number'],
            'status': row['status'],
            'address': row['address'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        })
    
    return contractors

async def check_existing_sec(conn, sec_number: str) -> Dict[str, Any]:
    """Check if SEC number already exists and get details"""
    query = """
    SELECT id, contractor_name, sec_number, address, secondary_licenses, source
    FROM contractors 
    WHERE sec_number = $1
    """
    
    rows = await conn.fetch(query, sec_number)
    return {
        'exists': len(rows) > 0,
        'count': len(rows),
        'contractors': [dict(row) for row in rows]
    }

async def update_contractor_contact_info(conn, contractor_id: int, address: str = None, phone: str = None, email: str = None) -> bool:
    """Update contractor with contact information only (no SEC number)"""
    try:
        updates = ['updated_at = NOW()']
        params = [contractor_id]
        param_count = 1
        
        if address:
            param_count += 1
            updates.append(f'address = ${param_count}')
            params.append(address)
        
        if phone:
            param_count += 1
            updates.append(f'secondary_licenses = ${param_count}')  # Using secondary_licenses for phone
            params.append(f"Phone: {phone}")
        
        if email:
            param_count += 1
            updates.append(f'source = ${param_count}')  # Using source for email
            params.append(f"Email: {email}")
        
        if len(updates) == 1:  # Only updated_at
            return True  # Nothing to update
        
        query = f"""
        UPDATE contractors 
        SET {', '.join(updates)}
        WHERE id = $1
        """
        
        await conn.execute(query, *params)
        return True
    except Exception as e:
        print(f"❌ Error updating contractor {contractor_id}: {e}")
        return False

async def update_contractor_data(conn, contractor_id: int, sec_number: str, address: str = None, phone: str = None, email: str = None, company_name: str = None) -> Dict[str, Any]:
    """Update contractor with SEC number and additional data, handling duplicates"""
    result = {
        'success': False,
        'action': 'none',
        'message': '',
        'duplicate_count': 0
    }
    
    try:
        # Check if SEC number already exists
        sec_check = await check_existing_sec(conn, sec_number)
        
        if sec_check['exists']:
            result['duplicate_count'] = sec_check['count']
            result['action'] = 'duplicate_sec'
            result['message'] = f"SEC number {sec_number} already exists for {sec_check['count']} contractor(s)"
            
            # Still update contact info if we have it
            if address or phone or email:
                contact_success = await update_contractor_contact_info(conn, contractor_id, address, phone, email)
                if contact_success:
                    result['action'] = 'contact_info_updated'
                    result['message'] += f" - Updated contact info for contractor {contractor_id}"
                    result['success'] = True
                else:
                    result['message'] += f" - Failed to update contact info"
            else:
                result['success'] = True  # No contact info to update, but we handled the duplicate
        else:
            # SEC number doesn't exist, proceed with full update
            updates = ['sec_number = $1', 'updated_at = NOW()']
            params = [sec_number, contractor_id]
            param_count = 2
            
            if address:
                param_count += 1
                updates.append(f'address = ${param_count}')
                params.append(address)
            
            if phone:
                param_count += 1
                updates.append(f'secondary_licenses = ${param_count}')
                params.append(f"Phone: {phone}")
            
            if email:
                param_count += 1
                updates.append(f'source = ${param_count}')
                params.append(f"Email: {email}")
            
            query = f"""
            UPDATE contractors 
            SET {', '.join(updates)}
            WHERE id = $2
            """
            
            await conn.execute(query, *params)
            result['success'] = True
            result['action'] = 'full_update'
            result['message'] = f"Successfully updated contractor {contractor_id} with SEC number and contact info"
        
        return result
        
    except Exception as e:
        result['message'] = f"Error updating contractor {contractor_id}: {e}"
        return result

async def match_and_update_contractors():
    """Main function to match and update contractors with SEC numbers"""
    print("🔗 SEC Number Sync from Remote Contractors")
    print("=" * 80)
    
    # Connect to database
    print("\n📊 Connecting to local SEC database...")
    conn = await get_db_connection()
    if not conn:
        return
    
    try:
        # Fetch remote contractors
        remote_contractors = await fetch_all_remote_contractors()
        if not remote_contractors:
            print("❌ No remote contractors found")
            return
        
        # Fetch local contractors without SEC numbers
        print("\n📋 Fetching local contractors without SEC numbers...")
        local_contractors = await get_local_contractors_without_sec(conn)
        print(f"   Found {len(local_contractors)} local contractors without SEC numbers")
        
        if not local_contractors:
            print("✅ All local contractors already have SEC numbers")
            return
        
        # Create remote contractor lookup by name
        print("\n🔍 Building remote contractor lookup...")
        remote_by_name = {}
        for contractor in remote_contractors:
            # Try different name fields
            name = contractor.get('company_name') or contractor.get('name', '')
            if name:
                normalized = normalize_contractor_name(name)
                if normalized not in remote_by_name:
                    remote_by_name[normalized] = []
                remote_by_name[normalized].append(contractor)
        
        print(f"   Indexed {len(remote_by_name)} unique contractor names from remote")
        
        # Match and update
        print("\n🔄 Matching and updating contractors...")
        matches_found = 0
        updates_successful = 0
        duplicate_sec_count = 0
        contact_info_updates = 0
        flagged_differences = 0
        
        for local_contractor in local_contractors:
            local_name = local_contractor['contractor_name']
            local_id = local_contractor['id']
            
            # Try exact match first
            normalized_local = normalize_contractor_name(local_name)
            exact_matches = remote_by_name.get(normalized_local, [])
            
            if exact_matches:
                # Use the first exact match
                remote_contractor = exact_matches[0]
                sec_number = remote_contractor.get('sec_registration') or remote_contractor.get('sec_number') or remote_contractor.get('secNumber')
                address = remote_contractor.get('address', '')
                phone = remote_contractor.get('phone', '')
                email = remote_contractor.get('email', '')
                company_name = remote_contractor.get('company_name', '')
                
                if sec_number:
                    result = await update_contractor_data(conn, local_id, sec_number, address, phone, email, company_name)
                    
                    if result['action'] == 'full_update':
                        updates_successful += 1
                        print(f"   ✅ {local_name} -> SEC: {sec_number}")
                        if address:
                            print(f"      Address: {address}")
                        if phone:
                            print(f"      Phone: {phone}")
                        if email:
                            print(f"      Email: {email}")
                    elif result['action'] == 'duplicate_sec':
                        duplicate_sec_count += 1
                        print(f"   🔄 {local_name} -> SEC: {sec_number} (DUPLICATE - {result['duplicate_count']} existing)")
                        if result['success']:
                            contact_info_updates += 1
                            print(f"      ✅ Updated contact info only")
                        if address:
                            print(f"      Address: {address}")
                        if phone:
                            print(f"      Phone: {phone}")
                        if email:
                            print(f"      Email: {email}")
                    elif result['action'] == 'contact_info_updated':
                        contact_info_updates += 1
                        print(f"   📞 {local_name} -> Contact info updated (SEC duplicate)")
                    else:
                        print(f"   ❌ Failed to update {local_name}: {result['message']}")
                else:
                    # No SEC number, but try to update contact info if available
                    if address or phone or email:
                        contact_success = await update_contractor_contact_info(conn, local_id, address, phone, email)
                        if contact_success:
                            contact_info_updates += 1
                            print(f"   📞 {local_name} -> Contact info updated (no SEC number)")
                            if address:
                                print(f"      Address: {address}")
                            if phone:
                                print(f"      Phone: {phone}")
                            if email:
                                print(f"      Email: {email}")
                        else:
                            print(f"   ❌ Failed to update contact info for {local_name}")
                    else:
                        print(f"   ⚠️  {local_name} matched but no SEC number or contact info in remote data")
                
                matches_found += 1
                continue
            
            # Try fuzzy matching
            best_match = None
            best_similarity = 0
            
            for norm_name, contractors in remote_by_name.items():
                if fuzzy_match_name(local_name, norm_name):
                    for contractor in contractors:
                        sec_number = contractor.get('sec_number') or contractor.get('secNumber')
                        if sec_number:
                            # Calculate similarity score
                            similarity = len(set(normalized_local.split()) & set(norm_name.split())) / len(set(normalized_local.split()) | set(norm_name.split()))
                            if similarity > best_similarity:
                                best_similarity = similarity
                                best_match = contractor
            
            if best_match and best_similarity >= 0.7:  # 70% similarity threshold
                sec_number = best_match.get('sec_registration') or best_match.get('sec_number') or best_match.get('secNumber')
                address = best_match.get('address', '')
                phone = best_match.get('phone', '')
                email = best_match.get('email', '')
                company_name = best_match.get('company_name', '')
                
                if sec_number:
                    result = await update_contractor_data(conn, local_id, sec_number, address, phone, email, company_name)
                    
                    if result['action'] == 'full_update':
                        updates_successful += 1
                        print(f"   🔍 {local_name} ~> {company_name} -> SEC: {sec_number} (similarity: {best_similarity:.2f})")
                        if address:
                            print(f"      Address: {address}")
                        if phone:
                            print(f"      Phone: {phone}")
                        if email:
                            print(f"      Email: {email}")
                    elif result['action'] == 'duplicate_sec':
                        duplicate_sec_count += 1
                        print(f"   🔄 {local_name} ~> {company_name} -> SEC: {sec_number} (DUPLICATE - {result['duplicate_count']} existing, similarity: {best_similarity:.2f})")
                        if result['success']:
                            contact_info_updates += 1
                            print(f"      ✅ Updated contact info only")
                        if address:
                            print(f"      Address: {address}")
                        if phone:
                            print(f"      Phone: {phone}")
                        if email:
                            print(f"      Email: {email}")
                    elif result['action'] == 'contact_info_updated':
                        contact_info_updates += 1
                        print(f"   📞 {local_name} ~> {company_name} -> Contact info updated (SEC duplicate, similarity: {best_similarity:.2f})")
                    else:
                        print(f"   ❌ Failed to update {local_name}: {result['message']}")
                else:
                    # No SEC number, but try to update contact info if available
                    if address or phone or email:
                        contact_success = await update_contractor_contact_info(conn, local_id, address, phone, email)
                        if contact_success:
                            contact_info_updates += 1
                            print(f"   📞 {local_name} ~> {company_name} -> Contact info updated (no SEC, similarity: {best_similarity:.2f})")
                            if address:
                                print(f"      Address: {address}")
                            if phone:
                                print(f"      Phone: {phone}")
                            if email:
                                print(f"      Email: {email}")
                        else:
                            print(f"   ❌ Failed to update contact info for {local_name}")
                    else:
                        print(f"   ⚠️  {local_name} matched but no SEC number or contact info in remote data")
                
                matches_found += 1
        
        print(f"\n📊 SYNC SUMMARY:")
        print(f"   Local contractors without SEC: {len(local_contractors)}")
        print(f"   Remote contractors available: {len(remote_contractors)}")
        print(f"   Matches found: {matches_found}")
        print(f"   Full updates (SEC + contact): {updates_successful}")
        print(f"   Contact info only updates: {contact_info_updates}")
        print(f"   Duplicate SEC numbers found: {duplicate_sec_count}")
        print(f"   Total successful updates: {updates_successful + contact_info_updates}")
        print(f"   Success rate: {((updates_successful + contact_info_updates)/len(local_contractors)*100):.1f}%")
        
        if duplicate_sec_count > 0:
            print(f"\n⚠️  DUPLICATE SEC NUMBERS DETECTED:")
            print(f"   {duplicate_sec_count} contractors had SEC numbers that already exist in database")
            print(f"   These were flagged for further review")
            print(f"   Contact information was still updated where available")
        
    finally:
        await conn.close()

async def main():
    """Main entry point"""
    await match_and_update_contractors()

if __name__ == "__main__":
    asyncio.run(main())
