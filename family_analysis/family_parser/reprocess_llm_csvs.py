#!/usr/bin/env python3
"""
Reprocess previously saved LLM CSVs and fix missing relationship types (e.g., Successor/Predecessor).

This script:
- Loads .env for DB config
- Uses the EnvLLMCSVProcessor (which ensures connection types and middle_name column)
- Iterates llm_relationships_*.csv files in this directory and reprocesses them
"""

import os
import asyncio
from dotenv import load_dotenv

from automate_perplexity_relationships import EnvLLMCSVProcessor


async def main():
    load_dotenv()

    # Find CSVs to reprocess
    csv_files = sorted([
        f for f in os.listdir('.')
        if f.startswith('llm_relationships_') and f.endswith('.csv')
    ])

    if not csv_files:
        print("📁 No llm_relationships_*.csv files found to reprocess")
        return

    print(f"🔁 Reprocessing {len(csv_files)} CSV files:")
    for f in csv_files:
        print(f"   - {f}")

    processor = EnvLLMCSVProcessor()
    try:
        await processor.connect()            # ensures middle_name + connection_types exist
        await processor.setup_connection_types()

        for csv_file in csv_files:
            await processor.process_csv_file(csv_file)
            print()

        await processor.show_relationship_summary()
    finally:
        await processor.close()


if __name__ == "__main__":
    asyncio.run(main())


