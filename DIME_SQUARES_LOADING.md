# DIME Squares Progressive Loading Implementation

## Summary

Implemented progressive loading for DIME-only project squares on the `/map` page.

## What are "Squares"?

**"Squares"** refer to **DIME-only projects** - infrastructure projects that exist in the DIME (Department of Public Works and Highways) database but are NOT linked to the Flood Control database. These are displayed as **rectangle/square markers** on the map (as opposed to circles which represent Flood Control projects).

## Changes Made

### 1. Initial Loading Pattern
- **Before**: Started loading from offset 1000 (skipping first 1000 projects)
- **After**: Load first **10 squares** on page load (offset 0)

### 2. Progressive Loading
- **Before**: Loaded 100 squares per batch, skipping 1000 each time
- **After**: Load **10 squares per batch** progressively

### 3. Implementation Details

**File Modified**: `templates/map.html`

**Key Changes**:
```javascript
// Initialize offset at 0 instead of 1000
let dimeGlobalOffset = 0;

// Load first 10 squares initially
const initialBatch = allDimeProjectsCache.slice(0, 10);

// Progressive loading: 10 per batch
const batch = allDimeProjectsCache.slice(dimeGlobalOffset, dimeGlobalOffset + 10);
dimeGlobalOffset += 10;
```

## Verification Steps

### To verify the actual count of DIME-only squares:

1. Start the application:
   ```bash
   cd /home/joebert/open-data-visualization
   cargo build && cargo run
   ```

2. In another terminal, query the API:
   ```bash
   curl http://localhost:8889/api/dime/projects/dime-only | jq '.count'
   ```

3. Open the browser console when visiting `/map` and look for:
   ```
   📊 Cached [X] DIME-only projects (squares)
   ```

### To test the progressive loading:

1. Visit `http://localhost:8889/map`
2. Open browser DevTools Console (F12)
3. Observe the loading sequence:
   - Initial: `🔲 Loading initial 10 DIME squares: 10 loaded`
   - Progressive: `🔲 Loading more DIME: offset 10, 10 squares (total loaded: 20/[total])`
   - Continues until all squares are loaded

## Expected Behavior

1. **Page Load**: 
   - 10 Flood Control circles load first
   - 10 DIME-only squares load after 1 second

2. **Progressive Loading**:
   - Every 2 seconds, load 10 more DIME squares
   - Console shows progress: "total loaded: X/Y"
   - Stops when all squares are loaded

3. **Load All Button**:
   - Loads ALL Flood Control projects (9,855) + all DIME squares at once
   - WARNING: May cause browser to freeze on slower devices

## API Endpoint

**Endpoint**: `GET /api/dime/projects/dime-only`

**SQL Query**:
```sql
SELECT id, project_name, description, latitude, longitude, 
       status, city, province, region, contractors, cost
FROM projects
WHERE (meilisearch_id IS NULL OR meilisearch_id = '')
  AND latitude IS NOT NULL AND longitude IS NOT NULL
  AND latitude != 0 AND longitude != 0
```

**Returns**:
```json
{
  "success": true,
  "projects": [...],
  "count": 141  // Actual count will be displayed here
}
```

## Notes

- The user's estimate of **141 squares** will be verified when the API is called
- The actual count may differ and will be logged in the console
- DIME-only projects are those without a `meilisearch_id` (not linked to Flood Control data)
- Progressive loading helps prevent browser freeze on slower devices

