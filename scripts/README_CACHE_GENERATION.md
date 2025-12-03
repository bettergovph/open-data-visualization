# Pre-generate JSON Cache Files for /nep and /budget Pages

This directory contains scripts to pre-generate JSON cache files for heavy processing endpoints, replacing on-demand computation with static file serving.

## Problem

The `/nep` and `/budget` pages have several endpoints that perform heavy processing on each request:
- Database queries across multiple years
- Complex data aggregation and sorting
- Chainage parsing and categorization
- Duplicate detection processing

This causes slow page loads and high server load.

## Solution

Pre-generate JSON cache files for these endpoints and serve them directly, falling back to processing only if cache doesn't exist.

## Scripts

### 1. `pre_generate_nep_budget_json.py`

Pre-generates JSON cache files for heavy endpoints:

**Endpoints cached:**
- `/api/budget/regions` - Yearly region data aggregation
- `/api/budget/nep/year-over-year` - Year-over-year NEP data
- `/api/budget/nep/top-programs` - Top NEP programs by year
- `/api/budget/analysis/comparison-chart` - Budget vs NEP comparison
- `/api/budget/programs/comparison` - Program comparison across years
- `/api/budget/roads-cost-analysis` - Road infrastructure analysis with chainage parsing
- `/api/budget/amendments/departments` - Budget amendments departments
- `/api/budget/amendments/annex-a1-amounts` - Annex A-1 project amounts
- `/api/budget/amendments/annex-a5-amounts` - Annex A-5 project amounts
- `/api/budget/amendments/annex-a4-amounts` - Annex A-4 project amounts
- `/api/budget/amendments/annex-a5-duplicates` - Annex A-5 duplicates
- `/api/budget/amendments/annex-a4-duplicates` - Annex A-4 duplicates
- `/api/budget/department-trends` - Department spending trends

**Usage:**
```bash
cd /home/joebert/open-data-visualization
python3 scripts/pre_generate_nep_budget_json.py
```

**Output:**
Cache files are saved to `static/data/api_cache/` directory.

### 2. `update_visualization_to_use_cache.py`

Updates `visualization.py` endpoints to check for cache files first before processing.

**Usage:**
```bash
cd /home/joebert/open-data-visualization
python3 scripts/update_visualization_to_use_cache.py
```

**Note:** This script creates a backup of `visualization.py` before making changes.

## Manual Endpoint Updates

If you prefer to update endpoints manually, add this pattern at the start of each endpoint function (after the `try:` statement):

```python
@app.get("/api/budget/regions")
async def budget_regions_api(year: str = "2025", limit: int = 8):
    """Get budget regions - no authentication required"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "budget_regions_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    # Check if year-specific data exists
                    year_data = cache_data.get('data', {}).get(year)
                    if year_data:
                        print(f"✅ [budget_regions] Using cached data for year {year}")
                        return JSONResponse(year_data)
            except Exception as cache_err:
                print(f"⚠️ [budget_regions] Error reading cache, falling back to processing: {cache_err}")
        
        # Fall back to processing
        result = await get_budget_regions(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
```

## Cache File Structure

Cache files are JSON files with this structure:
```json
{
  "success": true,
  "data": { ... },
  "generated_at": "2024-01-01T00:00:00",
  "years": [2020, 2021, 2022, ...]
}
```

## Regenerating Cache

Run the pre-generation script whenever:
- Source data is updated (e.g., new budget amendments)
- You want to refresh the cache
- Cache files are missing or corrupted

## Performance Benefits

- **Faster response times**: Serving static JSON is much faster than database queries
- **Reduced server load**: No computation on each request
- **Better scalability**: Can handle more concurrent requests
- **Offline capability**: Cache files can be served from CDN

## Maintenance

1. **Automated regeneration**: Set up a cron job or scheduled task to regenerate cache files periodically
2. **Cache invalidation**: Update cache when source data changes
3. **Monitoring**: Check cache file sizes and generation times

## Example Cron Job

```bash
# Regenerate cache daily at 2 AM
0 2 * * * cd /home/joebert/open-data-visualization && python3 scripts/pre_generate_nep_budget_json.py >> /var/log/cache_generation.log 2>&1
```


