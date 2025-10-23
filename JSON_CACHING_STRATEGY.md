# JSON Caching Strategy

## Overview
Complex tables and visuals that require heavy processing, database queries, or data transformations should be preprocessed and cached as JSON files for optimal performance.

## Caching Candidates

### ✅ **High Priority - Always Cache**
- **Complex Aggregations**: Barangay contractors, project correlations
- **Heavy Database Queries**: Multi-table joins with filtering
- **Data Transformations**: MeiliSearch connections, contractor matching
- **Visual Data**: Chart datasets, map coordinates, statistics
- **Cross-Database Analysis**: Flood-DIME correlations, contractor venn diagrams

### ✅ **Medium Priority - Consider Caching**
- **Filtered Results**: Large datasets with complex filtering
- **Sorted/Ranked Data**: Top performers, rankings, leaderboards
- **Geographic Aggregations**: Region/province/city summaries
- **Time-Series Data**: Year-over-year comparisons, trends

### ❌ **Low Priority - Don't Cache**
- **Simple Lists**: Basic dropdown options, simple filters
- **Real-time Data**: Live counters, dynamic updates
- **User-Specific Data**: Personal dashboards, user preferences
- **Small Datasets**: < 100 records, simple queries

## Implementation Pattern

### 1. **Identify Complex Operations**
```python
# Examples of complex operations that should be cached:
- Multiple database joins
- MeiliSearch API calls
- Data aggregation by location
- Contractor matching across databases
- Geographic clustering
- Statistical calculations
```

### 2. **Create Preprocessing Script**
```python
# analysis/generate_[feature_name].py
def main():
    # Load source data
    # Perform complex processing
    # Generate optimized JSON
    # Save to static/data/
```

### 3. **Update Master Script**
```python
# static/data/generate_all_json.py
'feature_data.json': {
    'script': 'analysis/generate_feature_data.py',
    'description': 'Preprocessed feature data with complex calculations',
    'category': 'processed_data',
    'dependencies': ['Source data', 'APIs']
}
```

### 4. **Frontend Integration**
```javascript
// Load from cached JSON instead of API
const response = await fetch('/static/data/feature_data.json');
const data = await response.json();
```

## Current Cached Features

### 🏘️ **Barangay Contractors**
- **File**: `barangay_contractors.json`
- **Script**: `analysis/generate_barangay_contractors.py`
- **Complexity**: MeiliSearch connections, contractor matching, geographic aggregation
- **Benefit**: Instant modal loading, no API calls

### ⚡ **Fastest Projects**
- **File**: `fastest_dime_projects.json`
- **Complexity**: Date calculations, completion time analysis, contractor processing
- **Benefit**: Pre-calculated rankings, instant table loading

### 🔗 **Flood-DIME Correlations**
- **Files**: `flood_dime_contractor_correlation_*.json`
- **Complexity**: Cross-database matching, fuzzy string matching, statistical analysis
- **Benefit**: Complex correlation data pre-calculated

### 📊 **Contractor Statistics**
- **File**: `contractor_stats_cache.json`
- **Complexity**: Aggregated statistics, performance metrics, suspicion scoring
- **Benefit**: Instant contractor analysis, no real-time calculations

## Performance Benefits

### ⚡ **Speed Improvements**
- **API Calls**: 0ms (cached) vs 200-2000ms (live)
- **Database Queries**: Eliminated for cached data
- **Complex Processing**: Pre-calculated, instant loading
- **User Experience**: Immediate results, no loading spinners

### 💾 **Resource Optimization**
- **Server Load**: Reduced database queries
- **API Rate Limits**: Avoided for cached endpoints
- **Bandwidth**: Smaller JSON files vs large API responses
- **Memory**: Efficient data structures

## Cache Management

### 🔄 **Update Strategy**
```bash
# Update all caches
python3 static/data/generate_all_json.py

# Update specific cache
python3 analysis/generate_feature_data.py
```

### 🗄️ **MongoDB Storage (Future Implementation)**
```python
# Store JSON caches in MongoDB for:
# - Centralized cache management
# - Version control and history
# - Distributed access
# - Cache invalidation strategies
# - Performance analytics

# MongoDB Collections:
# - json_caches: Main cache storage
# - cache_metadata: Generation info, dependencies
# - cache_analytics: Hit rates, performance metrics
```

### 📊 **Hybrid Storage Strategy**
```python
# Current: File-based JSON
# Future: MongoDB + File fallback
# Benefits:
# - Centralized cache management
# - Version history and rollback
# - Distributed cache access
# - Real-time cache updates
# - Performance monitoring
```

### 📅 **Refresh Schedule**
- **Daily**: Real-time critical data
- **Weekly**: Statistical summaries, rankings
- **Monthly**: Historical analysis, trends
- **On-Demand**: Complex correlations, special reports

### 🧹 **Cache Cleanup**
- Remove outdated JSON files
- Archive old versions
- Monitor file sizes
- Update dependencies

## Best Practices

### ✅ **Do**
- Cache complex aggregations
- Pre-process heavy calculations
- Use efficient data structures
- Include metadata (generated_at, version)
- Handle missing data gracefully

### ❌ **Don't**
- Cache simple, fast operations
- Cache user-specific data
- Cache real-time requirements
- Over-cache small datasets
- Ignore cache invalidation

## Future Candidates

### 🎯 **Potential Caching Targets**
- **Map Visualizations**: Geographic clustering, coordinate processing
- **Budget Analysis**: Complex financial calculations, trend analysis
- **Contractor Networks**: Relationship mapping, connection analysis
- **Performance Metrics**: Statistical analysis, benchmarking
- **Report Generation**: Pre-calculated insights, summaries

## Monitoring

### 📊 **Metrics to Track**
- Cache hit rates
- File sizes
- Generation times
- User experience improvements
- Server resource usage

### 🔍 **Debugging**
- Cache validation
- Data freshness checks
- Dependency tracking
- Error handling

---

*This strategy ensures optimal performance for complex data visualizations while maintaining data freshness and system efficiency.*
