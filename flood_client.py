"""
Flood Control Projects API Client
Handles MeiliSearch integration and data processing for flood control projects
"""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import aiohttp
import pandas as pd
from dataclasses import dataclass, asdict
from urllib.parse import urlencode
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class FloodControlProject:
    """Flood control project data structure"""
    GlobalID: Optional[str] = None
    ProjectDescription: Optional[str] = None
    InfraYear: Optional[str] = None
    Region: Optional[str] = None
    Province: Optional[str] = None
    Municipality: Optional[str] = None
    TypeofWork: Optional[str] = None
    Contractor: Optional[str] = None
    ContractCost: Optional[str] = None
    DistrictEngineeringOffice: Optional[str] = None
    LegislativeDistrict: Optional[str] = None
    ContractID: Optional[str] = None
    ProjectID: Optional[str] = None
    Latitude: Optional[str] = None
    Longitude: Optional[str] = None

@dataclass
class FloodControlStats:
    """Flood control statistics"""
    totalProjects: int = 0
    totalCost: float = 0.0
    uniqueContractors: int = 0
    regions: Dict[str, int] = None
    years: Dict[str, int] = None
    typesOfWork: Dict[str, int] = None
    topContractors: Dict[str, int] = None

    def __post_init__(self):
        if self.regions is None:
            self.regions = {}
        if self.years is None:
            self.years = {}
        if self.typesOfWork is None:
            self.typesOfWork = {}
        if self.topContractors is None:
            self.topContractors = {}

class FloodControlClient:
    """Client for interacting with flood control projects data via MeiliSearch"""
    
    def __init__(self, meilisearch_host: str = None, meilisearch_port: int = None, 
                 meilisearch_api_key: str = None):
        # Use environment variables if not provided - try both naming conventions
        # Use MEILI_HTTP_ADDR or MEILISEARCH_URL environment variables
        meili_addr = os.getenv("MEILI_HTTP_ADDR") or os.getenv("MEILISEARCH_URL", "").replace("http://", "").replace("https://", "")
        if not meili_addr:
            raise ValueError("MEILI_HTTP_ADDR or MEILISEARCH_URL environment variable must be set")
        
        self.meilisearch_host = meilisearch_host or meili_addr.split(":")[0]
        self.meilisearch_port = meilisearch_port or int(meili_addr.split(":")[-1] if ":" in meili_addr else "7700")
        
        # Try both environment variable names for API key
        self.meilisearch_api_key = meilisearch_api_key or \
            os.getenv("MEILISEARCH_MASTER_KEY") or \
            os.getenv("MEILI_MASTER_KEY") or \
            "0jH6Q1HHOBgJ8j3ISMx415T+mOKvURP9RA9FFpjoeco="
        self.base_url = f"http://{self.meilisearch_host}:{self.meilisearch_port}"
        self.index_name = "bettergov_flood_control"
        
        logger.info(f"🔍 MeiliSearch configured: {self.base_url} with index '{self.index_name}'")
        
    async def _make_request(self, endpoint: str, method: str = "GET", 
                           params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """Make HTTP request to MeiliSearch API"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.meilisearch_api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers, params=params) as response:
                        response.raise_for_status()
                        return await response.json()
                elif method == "POST":
                    async with session.post(url, headers=headers, json=data, params=params) as response:
                        response.raise_for_status()
                        return await response.json()
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in _make_request: {e}")
            raise

    async def search_projects(self, query: str = "", filters: Optional[str] = None, 
                            limit: int = 20, offset: int = 0) -> Tuple[List[FloodControlProject], Dict]:
        """Search flood control projects with optional filters"""
        search_params = {
            "q": query,
            "limit": limit,
            "offset": offset,
            "attributesToRetrieve": [
                "GlobalID", "ProjectDescription", "InfraYear", "Region", 
                "Province", "Municipality", "TypeofWork", "Contractor", 
                "ContractCost", "DistrictEngineeringOffice", "LegislativeDistrict",
                "ContractID", "ProjectID", "Latitude", "Longitude"
            ]
        }
        
        if filters:
            search_params["filter"] = filters
            
        try:
            response = await self._make_request(f"indexes/{self.index_name}/search", 
                                              "POST", data=search_params)
            
            projects = []
            for hit in response.get("hits", []):
                project = FloodControlProject(**hit)
                projects.append(project)
            
            # Extract search metadata
            search_metadata = {
                "totalHits": response.get("estimatedTotalHits", 0),
                "processingTimeMs": response.get("processingTimeMs", 0),
                "query": response.get("query", ""),
                "facetsDistribution": response.get("facetsDistribution", {})
            }
            
            return projects, search_metadata
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return [], {}

    async def get_project_by_id(self, project_id: str) -> Optional[FloodControlProject]:
        """Get a specific project by its GlobalID"""
        try:
            response = await self._make_request(f"indexes/{self.index_name}/search", 
                                              "POST", data={
                "q": "",
                "filter": f"GlobalID = '{project_id}'",
                "limit": 1
            })
            
            hits = response.get("hits", [])
            if hits:
                return FloodControlProject(**hits[0])
            return None
            
        except Exception as e:
            logger.error(f"Failed to get project by ID {project_id}: {e}")
            return None

    async def get_statistics(self, filters: Optional[str] = None) -> FloodControlStats:
        """Get comprehensive statistics for flood control projects"""
        try:
            # Get all projects with filters applied
            search_params = {
                "q": "",
                "limit": 10000,  # Get all projects for statistics
                "attributesToRetrieve": [
                    "GlobalID", "ContractCost", "Contractor", "Region", 
                    "InfraYear", "TypeofWork"
                ]
            }
            
            if filters:
                search_params["filter"] = filters
                
            response = await self._make_request(f"indexes/{self.index_name}/search", 
                                              "POST", data=search_params)
            
            hits = response.get("hits", [])
            total_hits = response.get("estimatedTotalHits", 0)
            
            # Calculate statistics
            total_cost = 0.0
            contractors = set()
            regions = {}
            years = {}
            types_of_work = {}
            contractor_counts = {}
            
            for hit in hits:
                # Total cost
                try:
                    contract_cost = hit.get("ContractCost", 0)
                    if isinstance(contract_cost, str):
                        # Remove currency symbols and commas
                        contract_cost = contract_cost.replace("₱", "").replace(",", "").replace(" ", "")
                    cost = float(contract_cost)
                    total_cost += cost
                except (ValueError, TypeError):
                    pass
                
                # Unique contractors
                contractor = hit.get("Contractor")
                if contractor and isinstance(contractor, str) and contractor.strip():
                    contractors.add(contractor)
                    contractor_counts[contractor] = contractor_counts.get(contractor, 0) + 1
                
                # Region distribution
                region = hit.get("Region")
                if region and isinstance(region, str) and region.strip():
                    regions[region] = regions.get(region, 0) + 1
                
                # Year distribution
                year = hit.get("InfraYear")
                if year and isinstance(year, str) and year.strip():
                    years[year] = years.get(year, 0) + 1
                elif year and isinstance(year, (int, float)):
                    # Handle numeric years
                    years[str(year)] = years.get(str(year), 0) + 1
                
                # Type of work distribution
                work_type = hit.get("TypeofWork")
                if work_type and isinstance(work_type, str) and work_type.strip():
                    types_of_work[work_type] = types_of_work.get(work_type, 0) + 1
            
            # Get top 50 contractors
            top_contractors = dict(sorted(contractor_counts.items(), 
                                        key=lambda x: x[1], reverse=True)[:50])
            
            return FloodControlStats(
                totalProjects=total_hits,
                totalCost=total_cost,
                uniqueContractors=len(contractors),
                regions=regions,
                years=years,
                typesOfWork=types_of_work,
                topContractors=top_contractors
            )
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return FloodControlStats()

    async def get_facets(self, facet_name: str, filters: Optional[str] = None) -> Dict[str, int]:
        """Get facet distribution for a specific field"""
        try:
            search_params = {
                "q": "",
                "limit": 0,
                "facets": [facet_name]
            }
            
            if filters:
                search_params["filter"] = filters
                
            response = await self._make_request(f"indexes/{self.index_name}/search", 
                                              "POST", data=search_params)
            
            facets = response.get("facetsDistribution", {})
            return facets.get(facet_name, {})
            
        except Exception as e:
            logger.error(f"Failed to get facets for {facet_name}: {e}")
            return {}

    async def export_data(self, query: str = "", filters: Optional[str] = None, 
                         format: str = "json") -> str:
        """Export flood control data in specified format"""
        try:
            # Get all matching projects
            projects, metadata = await self.search_projects(query, filters, limit=10000)
            
            if format.lower() == "json":
                export_data = {
                    "metadata": metadata,
                    "projects": [asdict(project) for project in projects],
                    "exported_at": datetime.now().isoformat(),
                    "total_count": len(projects)
                }
                return json.dumps(export_data, indent=2, ensure_ascii=False)
            
            elif format.lower() == "csv":
                # Convert to DataFrame and then to CSV
                df_data = [asdict(project) for project in projects]
                df = pd.DataFrame(df_data)
                return df.to_csv(index=False)
            
            else:
                raise ValueError(f"Unsupported export format: {format}")
                
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if MeiliSearch is accessible and the index exists"""
        try:
            # Check if the index exists
            response = await self._make_request(f"indexes/{self.index_name}")
            return "uid" in response
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

# Utility functions for filter building
def build_filter_string(filters: Dict[str, str]) -> str:
    """Build MeiliSearch filter string from dictionary"""
    filter_parts = []
    
    for key, value in filters.items():
        if value and value.strip():
            if key in ["InfraYear"]:
                filter_parts.append(f"{key} = '{value}'")
            else:
                filter_parts.append(f"{key} = '{value}'")
    
    return " AND ".join(filter_parts) if filter_parts else ""

def build_search_url(base_url: str, query: str = "", filters: Optional[Dict[str, str]] = None) -> str:
    """Build search URL with query parameters"""
    params = {}
    if query:
        params["q"] = query
    if filters:
        params["filters"] = json.dumps(filters)
    
    if params:
        return f"{base_url}?{urlencode(params)}"
    return base_url

# Global client instance
flood_client = FloodControlClient()

# Async context manager for session management
class FloodControlSession:
    def __init__(self):
        self.client = FloodControlClient()
    
    async def __aenter__(self):
        return self.client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

# Example usage and testing
async def test_flood_client():
    """Test function for flood client functionality"""
    client = FloodControlClient()
    
    # Test health check
    is_healthy = await client.health_check()
    print(f"MeiliSearch health check: {is_healthy}")
    
    if is_healthy:
        # Test search
        projects, metadata = await client.search_projects("flood", limit=5)
        print(f"Found {len(projects)} projects")
        print(f"Total hits: {metadata.get('totalHits', 0)}")
        
        # Test statistics
        stats = await client.get_statistics()
        print(f"Total projects: {stats.totalProjects}")
        print(f"Total cost: ₱{stats.totalCost:,.2f}")
        print(f"Unique contractors: {stats.uniqueContractors}")

if __name__ == "__main__":
    asyncio.run(test_flood_client())
