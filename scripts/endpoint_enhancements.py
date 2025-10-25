
# Enhancements for existing endpoints (backward compatible)

# Add to /api/dynasty endpoint:
# - government_branch: str = Query("", description="Filter by government branch")
# - position_category: str = Query("", description="Filter by position category") 
# - appointment_type: str = Query("", description="Filter by appointment type")

# Add to /api/dynasty/family endpoint:
# - position_category: str = Query("", description="Filter by position category")
# - government_branch: str = Query("", description="Filter by government branch")

# These are OPTIONAL parameters - existing calls will work unchanged
