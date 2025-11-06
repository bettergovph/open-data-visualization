#!/usr/bin/env python3
"""
Script to generate province project caches for all provinces
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import the cache generator
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_province_projects_cache import ProvinceProjectsCacheGenerator

# List of all provinces (excluding "All Provinces" and "Compostela Valley" which is now "Davao de Oro")
PROVINCES = [
    'Abra', 'Agusan del Norte', 'Agusan del Sur', 'Aklan', 'Albay', 'Antique', 'Apayao', 'Aurora',
    'Basilan', 'Bataan', 'Batanes', 'Batangas', 'Benguet', 'Biliran', 'Bohol', 'Bukidnon', 'Bulacan',
    'Cagayan', 'Camarines Norte', 'Camarines Sur', 'Camiguin', 'Capiz', 'Catanduanes', 'Cavite', 'Cebu',
    'Davao de Oro', 'Davao del Norte', 'Davao del Sur', 'Davao Oriental', 'Davao Occidental',
    'Dinagat Islands', 'Eastern Samar', 'Guimaras', 'Ifugao', 'Ilocos Norte', 'Ilocos Sur', 'Iloilo',
    'Isabela', 'Kalinga', 'La Union', 'Laguna', 'Lanao del Norte', 'Lanao del Sur', 'Leyte',
    'Maguindanao', 'Marinduque', 'Masbate', 'Metropolitan Manila', 'Misamis Occidental', 'Misamis Oriental',
    'Mountain Province', 'Negros Occidental', 'Negros Oriental', 'North Cotabato', 'Northern Samar',
    'Nueva Ecija', 'Nueva Vizcaya', 'Occidental Mindoro', 'Oriental Mindoro', 'Palawan', 'Pampanga',
    'Pangasinan', 'Quezon', 'Quirino', 'Rizal', 'Romblon', 'Samar', 'Sarangani', 'Shariff Kabunsuan',
    'Siquijor', 'Sorsogon', 'South Cotabato', 'Southern Leyte', 'Sultan Kudarat', 'Sulu',
    'Surigao del Norte', 'Surigao del Sur', 'Tarlac', 'Tawi Tawi', 'Zambales',
    'Zamboanga del Norte', 'Zamboanga del Sur', 'Zamboanga Sibugay'
]

async def generate_all_caches():
    """Generate cache for all provinces"""
    total = len(PROVINCES)
    successful = 0
    failed = []
    
    print(f"🚀 Starting cache generation for {total} provinces...")
    print("=" * 80)
    
    for i, province in enumerate(PROVINCES, 1):
        print(f"\n[{i}/{total}] Processing: {province}")
        print("-" * 80)
        
        try:
            generator = ProvinceProjectsCacheGenerator(province_name=province)
            await generator.generate_cache()
            successful += 1
            print(f"✅ [{i}/{total}] Successfully generated cache for {province}")
        except Exception as e:
            failed.append((province, str(e)))
            print(f"❌ [{i}/{total}] Failed to generate cache for {province}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print(f"📊 Summary:")
    print(f"   Total provinces: {total}")
    print(f"   Successful: {successful}")
    print(f"   Failed: {len(failed)}")
    
    if failed:
        print(f"\n❌ Failed provinces:")
        for province, error in failed:
            print(f"   - {province}: {error}")
    
    print("\n✅ Cache generation complete!")

if __name__ == '__main__':
    asyncio.run(generate_all_caches())

