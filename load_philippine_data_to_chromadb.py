#!/usr/bin/env python3
"""
Download Philippine government data from HuggingFace and load into ChromaDB
for semantic search capabilities.
"""

import chromadb
from chromadb.config import Settings
from datasets import load_dataset
from tqdm import tqdm
import os


def load_persons_to_chromadb(client, batch_size=100):
    """Load persons data into ChromaDB collection"""
    print("\n=== Loading Persons Data ===")
    
    # Load dataset
    print("Downloading persons dataset from HuggingFace...")
    persons = load_dataset("bettergovph/raw-philippine-data", "persons", split="train")
    
    # Create or get collection
    collection = client.get_or_create_collection(
        name="philippine_persons",
        metadata={"description": "Philippine politicians and public officials"}
    )
    
    print(f"Processing {len(persons)} person records...")
    
    # Prepare batches
    ids = []
    documents = []
    metadatas = []
    
    for i, person in enumerate(tqdm(persons)):
        # Create searchable text from person data
        name_parts = []
        if person.get('first_name'):
            name_parts.append(person['first_name'])
        if person.get('middle_name'):
            name_parts.append(person['middle_name'])
        if person.get('last_name'):
            name_parts.append(person['last_name'])
        if person.get('name_suffix'):
            name_parts.append(person['name_suffix'])
        
        full_name = ' '.join(name_parts)
        
        # Create document text for embedding
        doc_text = f"Name: {full_name}"
        if person.get('nickname'):
            doc_text += f" (Nickname: {person['nickname']})"
        
        ids.append(person['id'])
        documents.append(doc_text)
        metadatas.append({
            'first_name': person.get('first_name', ''),
            'middle_name': person.get('middle_name', ''),
            'last_name': person.get('last_name', ''),
            'name_suffix': person.get('name_suffix', ''),
            'nickname': person.get('nickname', ''),
            'full_name': full_name
        })
        
        # Add batch when reached batch_size
        if len(ids) >= batch_size:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            ids, documents, metadatas = [], [], []
    
    # Add remaining items
    if ids:
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
    
    print(f"✓ Loaded {collection.count()} persons into ChromaDB")
    return collection


def load_memberships_to_chromadb(client, batch_size=100):
    """Load memberships (political positions) data into ChromaDB collection"""
    print("\n=== Loading Memberships Data ===")
    
    # Load dataset
    print("Downloading memberships dataset from HuggingFace...")
    memberships = load_dataset("bettergovph/raw-philippine-data", "memberships", split="train")
    
    # Create or get collection
    collection = client.get_or_create_collection(
        name="philippine_memberships",
        metadata={"description": "Political positions and party affiliations"}
    )
    
    print(f"Processing {len(memberships)} membership records...")
    
    # Prepare batches
    ids = []
    documents = []
    metadatas = []
    
    for i, membership in enumerate(tqdm(memberships)):
        # Create searchable text from membership data
        doc_text = f"Position: {membership.get('position', 'Unknown')}"
        if membership.get('party'):
            doc_text += f", Party: {membership['party']}"
        if membership.get('region'):
            doc_text += f", Region: {membership['region']}"
        if membership.get('province'):
            doc_text += f", Province: {membership['province']}"
        if membership.get('locality'):
            doc_text += f", Locality: {membership['locality']}"
        doc_text += f", Year: {membership.get('year', 'Unknown')}"
        
        ids.append(membership['id'])
        documents.append(doc_text)
        metadatas.append({
            'person_id': membership.get('person_id', ''),
            'party': membership.get('party', ''),
            'region': membership.get('region', ''),
            'province': membership.get('province', ''),
            'locality': membership.get('locality', ''),
            'position': membership.get('position', ''),
            'year': int(membership.get('year', 0))
        })
        
        # Add batch when reached batch_size
        if len(ids) >= batch_size:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            ids, documents, metadatas = [], [], []
    
    # Add remaining items
    if ids:
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
    
    print(f"✓ Loaded {collection.count()} memberships into ChromaDB")
    return collection


def load_documents_to_chromadb(client, batch_size=50):
    """Load legislative documents into ChromaDB collection"""
    print("\n=== Loading Documents Data ===")
    
    # Load dataset
    print("Downloading documents dataset from HuggingFace...")
    documents_data = load_dataset("bettergovph/raw-philippine-data", "documents", split="train")
    
    # Create or get collection
    collection = client.get_or_create_collection(
        name="philippine_documents",
        metadata={"description": "Legislative bills and documents"}
    )
    
    print(f"Processing {len(documents_data)} document records...")
    
    # Prepare batches
    ids = []
    documents = []
    metadatas = []
    
    for i, doc in enumerate(tqdm(documents_data)):
        # Use actual document content for embedding (this is the most valuable for semantic search)
        content = doc.get('content', '')
        
        # Skip empty documents
        if not content or len(content.strip()) < 10:
            continue
        
        # Truncate very long documents to avoid embedding limits (adjust as needed)
        max_length = 8000  # ChromaDB can handle longer but this is reasonable
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        doc_id = doc['id']
        doc_type = doc.get('document_type', 'unknown')
        congress = doc.get('congress', 0)
        doc_number = doc.get('document_number', 0)
        
        ids.append(doc_id)
        documents.append(content)
        metadatas.append({
            'document_type': doc_type,
            'congress': int(congress),
            'document_number': int(doc_number),
            'doc_name': f"{doc_type.upper()}-{doc_number}",
            'content_length': len(doc.get('content', ''))
        })
        
        # Add batch when reached batch_size (smaller batches for large documents)
        if len(ids) >= batch_size:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            ids, documents, metadatas = [], [], []
    
    # Add remaining items
    if ids:
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
    
    print(f"✓ Loaded {collection.count()} documents into ChromaDB")
    return collection


def main():
    """Main function to load all data into ChromaDB"""
    print("Philippine Government Data → ChromaDB Loader")
    print("=" * 60)
    
    # Initialize ChromaDB client (persistent storage)
    db_path = "./chroma_philippine_data"
    print(f"\nInitializing ChromaDB at: {db_path}")
    
    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(
            anonymized_telemetry=False
        )
    )
    
    # Load all datasets
    try:
        persons_collection = load_persons_to_chromadb(client)
        memberships_collection = load_memberships_to_chromadb(client)
        documents_collection = load_documents_to_chromadb(client)
        
        print("\n" + "=" * 60)
        print("✓ All data successfully loaded into ChromaDB!")
        print(f"\nDatabase location: {os.path.abspath(db_path)}")
        print("\nCollections created:")
        print(f"  - philippine_persons: {persons_collection.count()} records")
        print(f"  - philippine_memberships: {memberships_collection.count()} records")
        print(f"  - philippine_documents: {documents_collection.count()} records")
        
        # Example query
        print("\n" + "=" * 60)
        print("Example: Searching documents for 'infrastructure'...")
        results = documents_collection.query(
            query_texts=["infrastructure development projects"],
            n_results=3
        )
        
        print(f"\nFound {len(results['ids'][0])} results:")
        for i, (doc_id, metadata, distance) in enumerate(zip(
            results['ids'][0], 
            results['metadatas'][0],
            results['distances'][0]
        ), 1):
            print(f"\n{i}. {metadata['doc_name']} (Congress {metadata['congress']})")
            print(f"   Relevance score: {1 - distance:.3f}")
            print(f"   Document ID: {doc_id}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise


if __name__ == "__main__":
    main()




