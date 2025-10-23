#!/usr/bin/env python3
"""
MongoDB Cache Configuration
Example configuration for MongoDB cache integration

Usage:
    # Enable MongoDB caching
    python3 static/data/generate_all_json.py --mongodb "mongodb://localhost:27017/"
    
    # Or set environment variable
    export MONGODB_CONNECTION_STRING="mongodb://localhost:27017/"
    python3 static/data/generate_all_json.py
"""

import os
from typing import Optional

# MongoDB Configuration
MONGODB_CONFIG = {
    # Connection settings
    "connection_string": os.getenv("MONGODB_CONNECTION_STRING", "mongodb://localhost:27017/"),
    "database_name": os.getenv("MONGODB_DATABASE_NAME", "open_data_cache"),
    
    # Cache settings
    "enable_mongodb_cache": os.getenv("ENABLE_MONGODB_CACHE", "false").lower() == "true",
    "cache_ttl_days": int(os.getenv("CACHE_TTL_DAYS", "30")),
    "max_versions_per_cache": int(os.getenv("MAX_VERSIONS_PER_CACHE", "5")),
    
    # Performance settings
    "connection_timeout": int(os.getenv("MONGODB_CONNECTION_TIMEOUT", "30")),
    "server_selection_timeout": int(os.getenv("MONGODB_SERVER_SELECTION_TIMEOUT", "5")),
    
    # Analytics settings
    "enable_analytics": os.getenv("ENABLE_CACHE_ANALYTICS", "true").lower() == "true",
    "analytics_retention_days": int(os.getenv("ANALYTICS_RETENTION_DAYS", "90")),
}

def get_mongodb_connection_string() -> Optional[str]:
    """Get MongoDB connection string from environment or config"""
    return MONGODB_CONFIG["connection_string"] if MONGODB_CONFIG["enable_mongodb_cache"] else None

def get_mongodb_database_name() -> str:
    """Get MongoDB database name"""
    return MONGODB_CONFIG["database_name"]

def is_mongodb_enabled() -> bool:
    """Check if MongoDB caching is enabled"""
    return MONGODB_CONFIG["enable_mongodb_cache"]

def get_cache_ttl_days() -> int:
    """Get cache TTL in days"""
    return MONGODB_CONFIG["cache_ttl_days"]

def get_max_versions() -> int:
    """Get maximum versions to keep per cache"""
    return MONGODB_CONFIG["max_versions_per_cache"]

def get_connection_timeout() -> int:
    """Get MongoDB connection timeout"""
    return MONGODB_CONFIG["connection_timeout"]

def get_server_selection_timeout() -> int:
    """Get MongoDB server selection timeout"""
    return MONGODB_CONFIG["server_selection_timeout"]

def is_analytics_enabled() -> bool:
    """Check if cache analytics is enabled"""
    return MONGODB_CONFIG["enable_analytics"]

def get_analytics_retention_days() -> int:
    """Get analytics retention period in days"""
    return MONGODB_CONFIG["analytics_retention_days"]

# Example usage
if __name__ == "__main__":
    print("MongoDB Cache Configuration:")
    print(f"  Connection String: {get_mongodb_connection_string()}")
    print(f"  Database Name: {get_mongodb_database_name()}")
    print(f"  MongoDB Enabled: {is_mongodb_enabled()}")
    print(f"  Cache TTL: {get_cache_ttl_days()} days")
    print(f"  Max Versions: {get_max_versions()}")
    print(f"  Analytics Enabled: {is_analytics_enabled()}")
    print(f"  Analytics Retention: {get_analytics_retention_days()} days")
