#!/usr/bin/env python3
"""
MongoDB Cache Manager for JSON Caching Strategy
Future implementation for storing JSON caches in MongoDB

This module provides:
- Centralized cache management
- Version control and history
- Distributed cache access
- Cache invalidation strategies
- Performance analytics
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, OperationFailure


class MongoDBCacheManager:
    """Manages JSON caches in MongoDB with versioning and analytics"""
    
    def __init__(self, connection_string: str, database_name: str = "open_data_cache"):
        """
        Initialize MongoDB cache manager
        
        Args:
            connection_string: MongoDB connection string
            database_name: Database name for cache storage
        """
        self.connection_string = connection_string
        self.database_name = database_name
        self.client = None
        self.db = None
        self._connect()
    
    def _connect(self):
        """Establish MongoDB connection"""
        try:
            self.client = MongoClient(self.connection_string)
            self.db = self.client[self.database_name]
            # Test connection
            self.client.admin.command('ping')
            print("✅ Connected to MongoDB cache database")
        except ConnectionFailure as e:
            print(f"❌ Failed to connect to MongoDB: {e}")
            raise
    
    def store_cache(self, cache_name: str, data: Dict, metadata: Dict = None) -> str:
        """
        Store JSON cache in MongoDB with versioning
        
        Args:
            cache_name: Name of the cache (e.g., 'barangay_contractors')
            data: The JSON data to cache
            metadata: Additional metadata about the cache
            
        Returns:
            Version ID of the stored cache
        """
        try:
            # Generate version ID based on content hash
            content_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
            version_id = f"{cache_name}_{content_hash[:8]}_{int(datetime.now().timestamp())}"
            
            # Prepare cache document
            cache_doc = {
                "cache_name": cache_name,
                "version_id": version_id,
                "content_hash": content_hash,
                "data": data,
                "metadata": metadata or {},
                "created_at": datetime.now(),
                "size_bytes": len(json.dumps(data).encode()),
                "is_active": True
            }
            
            # Store in json_caches collection
            result = self.db.json_caches.insert_one(cache_doc)
            
            # Update cache metadata
            self._update_cache_metadata(cache_name, version_id, cache_doc)
            
            print(f"✅ Stored cache '{cache_name}' with version {version_id}")
            return version_id
            
        except OperationFailure as e:
            print(f"❌ Failed to store cache '{cache_name}': {e}")
            raise
    
    def get_cache(self, cache_name: str, version_id: str = None) -> Optional[Dict]:
        """
        Retrieve JSON cache from MongoDB
        
        Args:
            cache_name: Name of the cache to retrieve
            version_id: Specific version to retrieve (latest if None)
            
        Returns:
            Cache data or None if not found
        """
        try:
            query = {"cache_name": cache_name, "is_active": True}
            if version_id:
                query["version_id"] = version_id
            
            cache_doc = self.db.json_caches.find_one(query, sort=[("created_at", -1)])
            
            if cache_doc:
                # Log cache hit
                self._log_cache_access(cache_name, cache_doc["version_id"], "hit")
                return cache_doc["data"]
            else:
                # Log cache miss
                self._log_cache_access(cache_name, version_id or "latest", "miss")
                return None
                
        except OperationFailure as e:
            print(f"❌ Failed to retrieve cache '{cache_name}': {e}")
            return None
    
    def list_cache_versions(self, cache_name: str) -> List[Dict]:
        """List all versions of a cache"""
        try:
            versions = list(self.db.json_caches.find(
                {"cache_name": cache_name},
                {"version_id": 1, "created_at": 1, "size_bytes": 1, "is_active": 1}
            ).sort("created_at", -1))
            
            return versions
        except OperationFailure as e:
            print(f"❌ Failed to list versions for '{cache_name}': {e}")
            return []
    
    def invalidate_cache(self, cache_name: str, version_id: str = None):
        """
        Invalidate cache (mark as inactive)
        
        Args:
            cache_name: Name of the cache to invalidate
            version_id: Specific version to invalidate (all if None)
        """
        try:
            query = {"cache_name": cache_name}
            if version_id:
                query["version_id"] = version_id
            
            result = self.db.json_caches.update_many(
                query,
                {"$set": {"is_active": False, "invalidated_at": datetime.now()}}
            )
            
            print(f"✅ Invalidated {result.modified_count} versions of '{cache_name}'")
            
        except OperationFailure as e:
            print(f"❌ Failed to invalidate cache '{cache_name}': {e}")
    
    def _update_cache_metadata(self, cache_name: str, version_id: str, cache_doc: Dict):
        """Update cache metadata collection"""
        try:
            metadata_doc = {
                "cache_name": cache_name,
                "version_id": version_id,
                "last_updated": datetime.now(),
                "size_bytes": cache_doc["size_bytes"],
                "content_hash": cache_doc["content_hash"],
                "dependencies": cache_doc["metadata"].get("dependencies", []),
                "generation_script": cache_doc["metadata"].get("script", ""),
                "category": cache_doc["metadata"].get("category", "unknown")
            }
            
            self.db.cache_metadata.update_one(
                {"cache_name": cache_name},
                {"$set": metadata_doc},
                upsert=True
            )
            
        except OperationFailure as e:
            print(f"⚠️ Failed to update metadata for '{cache_name}': {e}")
    
    def _log_cache_access(self, cache_name: str, version_id: str, access_type: str):
        """Log cache access for analytics"""
        try:
            access_doc = {
                "cache_name": cache_name,
                "version_id": version_id,
                "access_type": access_type,  # 'hit' or 'miss'
                "accessed_at": datetime.now(),
                "timestamp": datetime.now().isoformat()
            }
            
            self.db.cache_analytics.insert_one(access_doc)
            
        except OperationFailure as e:
            print(f"⚠️ Failed to log cache access: {e}")
    
    def get_cache_analytics(self, cache_name: str = None, days: int = 30) -> Dict:
        """Get cache performance analytics"""
        try:
            start_date = datetime.now() - timedelta(days=days)
            query = {"accessed_at": {"$gte": start_date}}
            if cache_name:
                query["cache_name"] = cache_name
            
            # Get hit/miss statistics
            pipeline = [
                {"$match": query},
                {"$group": {
                    "_id": {"cache_name": "$cache_name", "access_type": "$access_type"},
                    "count": {"$sum": 1}
                }},
                {"$group": {
                    "_id": "$_id.cache_name",
                    "hits": {"$sum": {"$cond": [{"$eq": ["$_id.access_type", "hit"]}, "$count", 0]}},
                    "misses": {"$sum": {"$cond": [{"$eq": ["$_id.access_type", "miss"]}, "$count", 0]}}
                }},
                {"$addFields": {
                    "hit_rate": {"$divide": ["$hits", {"$add": ["$hits", "$misses"]}]}
                }}
            ]
            
            analytics = list(self.db.cache_analytics.aggregate(pipeline))
            return analytics
            
        except OperationFailure as e:
            print(f"❌ Failed to get analytics: {e}")
            return {}
    
    def cleanup_old_versions(self, cache_name: str, keep_versions: int = 5):
        """Clean up old cache versions, keeping only the most recent ones"""
        try:
            # Get versions to keep
            versions_to_keep = list(self.db.json_caches.find(
                {"cache_name": cache_name},
                {"version_id": 1}
            ).sort("created_at", -1).limit(keep_versions))
            
            keep_ids = [v["version_id"] for v in versions_to_keep]
            
            # Delete old versions
            result = self.db.json_caches.delete_many({
                "cache_name": cache_name,
                "version_id": {"$nin": keep_ids}
            })
            
            print(f"✅ Cleaned up {result.deleted_count} old versions of '{cache_name}'")
            
        except OperationFailure as e:
            print(f"❌ Failed to cleanup old versions: {e}")
    
    def get_cache_status(self) -> Dict:
        """Get overall cache system status"""
        try:
            status = {
                "total_caches": self.db.json_caches.count_documents({}),
                "active_caches": self.db.json_caches.count_documents({"is_active": True}),
                "total_size_mb": sum(
                    doc["size_bytes"] for doc in self.db.json_caches.find({}, {"size_bytes": 1})
                ) / (1024 * 1024),
                "cache_names": list(self.db.json_caches.distinct("cache_name")),
                "last_updated": datetime.now().isoformat()
            }
            
            return status
            
        except OperationFailure as e:
            print(f"❌ Failed to get cache status: {e}")
            return {}


def main():
    """Example usage of MongoDB cache manager"""
    # Example connection string (update with your MongoDB instance)
    connection_string = "mongodb://localhost:27017/"
    
    try:
        # Initialize cache manager
        cache_manager = MongoDBCacheManager(connection_string)
        
        # Example: Store a cache
        sample_data = {
            "success": True,
            "barangay_contractors": {
                "sample_barangay": {
                    "contractors": ["Contractor A", "Contractor B"],
                    "projects": ["Project 1", "Project 2"]
                }
            }
        }
        
        metadata = {
            "script": "analysis/generate_barangay_contractors.py",
            "category": "processed_data",
            "dependencies": ["DIME data", "MeiliSearch"]
        }
        
        version_id = cache_manager.store_cache("barangay_contractors", sample_data, metadata)
        print(f"Stored cache with version: {version_id}")
        
        # Example: Retrieve cache
        retrieved_data = cache_manager.get_cache("barangay_contractors")
        if retrieved_data:
            print("✅ Successfully retrieved cache")
        else:
            print("❌ Cache not found")
        
        # Example: Get analytics
        analytics = cache_manager.get_cache_analytics()
        print(f"Cache analytics: {analytics}")
        
        # Example: Get system status
        status = cache_manager.get_cache_status()
        print(f"Cache system status: {status}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
