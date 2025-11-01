#!/usr/bin/env python3
"""
Query the Philippine government data loaded in ChromaDB
"""

import chromadb
from chromadb.config import Settings


def query_documents(collection, query_text, n_results=5):
    """Search legislative documents"""
    print(f"\n🔍 Searching documents for: '{query_text}'")
    print("=" * 80)
    
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    
    if not results['ids'][0]:
        print("No results found.")
        return
    
    for i, (doc_id, metadata, document, distance) in enumerate(zip(
        results['ids'][0],
        results['metadatas'][0],
        results['documents'][0],
        results['distances'][0]
    ), 1):
        relevance = 1 - distance
        print(f"\n{i}. {metadata['doc_name']} - Congress {metadata['congress']}")
        print(f"   Relevance: {relevance:.3f} | Type: {metadata['document_type'].upper()}")
        print(f"   Preview: {document[:200]}...")
        print(f"   Document ID: {doc_id}")


def query_persons(collection, query_text, n_results=5):
    """Search for persons"""
    print(f"\n🔍 Searching persons for: '{query_text}'")
    print("=" * 80)
    
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    
    if not results['ids'][0]:
        print("No results found.")
        return
    
    for i, (doc_id, metadata, distance) in enumerate(zip(
        results['ids'][0],
        results['metadatas'][0],
        results['distances'][0]
    ), 1):
        relevance = 1 - distance
        print(f"\n{i}. {metadata['full_name']}")
        print(f"   Relevance: {relevance:.3f}")
        if metadata.get('nickname'):
            print(f"   Nickname: {metadata['nickname']}")
        print(f"   Person ID: {doc_id}")


def query_memberships(collection, query_text, n_results=5):
    """Search memberships/positions"""
    print(f"\n🔍 Searching memberships for: '{query_text}'")
    print("=" * 80)
    
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    
    if not results['ids'][0]:
        print("No results found.")
        return
    
    for i, (doc_id, metadata, document, distance) in enumerate(zip(
        results['ids'][0],
        results['metadatas'][0],
        results['documents'][0],
        results['distances'][0]
    ), 1):
        relevance = 1 - distance
        print(f"\n{i}. {metadata['position']} - {metadata.get('locality', metadata.get('province', 'N/A'))}")
        print(f"   Relevance: {relevance:.3f}")
        print(f"   Party: {metadata.get('party', 'N/A')} | Year: {metadata.get('year', 'N/A')}")
        print(f"   Region: {metadata.get('region', 'N/A')}")
        print(f"   Person ID: {metadata['person_id']}")


def filter_by_metadata(collection, filters):
    """Query with metadata filters"""
    print(f"\n🔍 Filtering with metadata: {filters}")
    print("=" * 80)
    
    results = collection.get(
        where=filters,
        limit=10
    )
    
    if not results['ids']:
        print("No results found.")
        return
    
    print(f"Found {len(results['ids'])} results:")
    for i, (doc_id, metadata) in enumerate(zip(results['ids'], results['metadatas']), 1):
        print(f"\n{i}. {metadata}")
        print(f"   ID: {doc_id}")


def main():
    """Main function with example queries"""
    print("Philippine Government Data - ChromaDB Query Examples")
    print("=" * 80)
    
    # Connect to existing database
    db_path = "./chroma_philippine_data"
    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(anonymized_telemetry=False)
    )
    
    # Get collections
    try:
        documents_collection = client.get_collection("philippine_documents")
        persons_collection = client.get_collection("philippine_persons")
        memberships_collection = client.get_collection("philippine_memberships")
        
        print(f"\n✓ Connected to ChromaDB at: {db_path}")
        print(f"  - Documents: {documents_collection.count()} records")
        print(f"  - Persons: {persons_collection.count()} records")
        print(f"  - Memberships: {memberships_collection.count()} records")
        
        # Example 1: Search documents by topic
        query_documents(
            documents_collection,
            "infrastructure development and transportation projects",
            n_results=3
        )
        
        # Example 2: Search for mayors in NCR
        query_memberships(
            memberships_collection,
            "Mayor National Capital Region Manila",
            n_results=5
        )
        
        # Example 3: Filter documents by congress number
        print("\n\n" + "=" * 80)
        print("Example: Filter documents from 20th Congress")
        print("=" * 80)
        filter_by_metadata(
            documents_collection,
            {"congress": 20}
        )
        
        # Example 4: Interactive mode
        print("\n\n" + "=" * 80)
        print("Interactive Query Mode")
        print("=" * 80)
        print("\nAvailable collections:")
        print("  1. Documents (legislative bills)")
        print("  2. Persons (politicians)")
        print("  3. Memberships (political positions)")
        print("  q. Quit")
        
        while True:
            choice = input("\nSelect collection (1-3) or 'q' to quit: ").strip()
            
            if choice == 'q':
                break
            
            if choice not in ['1', '2', '3']:
                print("Invalid choice. Please enter 1, 2, 3, or 'q'")
                continue
            
            query = input("Enter search query: ").strip()
            if not query:
                continue
            
            n_results = input("Number of results (default 5): ").strip()
            n_results = int(n_results) if n_results.isdigit() else 5
            
            if choice == '1':
                query_documents(documents_collection, query, n_results)
            elif choice == '2':
                query_persons(persons_collection, query, n_results)
            elif choice == '3':
                query_memberships(memberships_collection, query, n_results)
        
        print("\n✓ Query session ended")
        
    except ValueError as e:
        print(f"\n✗ Error: Collection not found - {e}")
        print("Please run load_philippine_data_to_chromadb.py first to create the database.")


if __name__ == "__main__":
    main()

