#!/usr/bin/env python3
"""
Scheduled Wikipedia Scraper for Political Dynasty Relationships
Automated system to run the scraper on a schedule
"""

import asyncio
import schedule
import time
import logging
from datetime import datetime
import os
from optimized_wiki_scraper import OptimizedWikipediaScraper

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wiki_scraper.log'),
        logging.StreamHandler()
    ]
)

class ScheduledWikiScraper:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    async def run_scraper(self):
        """Run the Wikipedia scraper"""
        try:
            self.logger.info("🚀 Starting scheduled Wikipedia scraper...")
            
            async with OptimizedWikipediaScraper() as scraper:
                results = await scraper.scrape_two_family_provinces(limit=19)
                
                # Log summary
                total_relationships = sum(
                    len(province['results']) 
                    for province in results 
                    for result in province['results'] 
                    for rel in result['relationships']
                )
                
                target_relationships = sum(
                    len([rel for rel in result['relationships'] if rel.get('is_target_family', False)])
                    for province in results 
                    for result in province['results']
                )
                
                self.logger.info(f"✅ Scraping complete! Found {total_relationships} total relationships, {target_relationships} target family relationships")
                
        except Exception as e:
            self.logger.error(f"❌ Error in scheduled scraper: {e}")

    def run_sync(self):
        """Synchronous wrapper for the async scraper"""
        asyncio.run(self.run_scraper())

def main():
    """Main scheduling function"""
    scraper = ScheduledWikiScraper()
    
    # Schedule the scraper to run daily at 2 AM
    schedule.every().day.at("02:00").do(scraper.run_sync)
    
    # Also run once immediately for testing
    scraper.logger.info("🔄 Running initial scraper execution...")
    scraper.run_sync()
    
    scraper.logger.info("📅 Scheduler started. Running daily at 2:00 AM...")
    
    # Keep the scheduler running
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    main()
