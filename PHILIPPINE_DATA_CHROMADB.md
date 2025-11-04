# Philippine Government Data → ChromaDB

This guide explains how to download and load the [BetterGov.PH Philippine dataset](https://huggingface.co/datasets/bettergovph/raw-philippine-data) into ChromaDB for semantic search.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements_chromadb.txt
```

### 2. Load Data into ChromaDB

This will download the dataset from HuggingFace and load it into a local ChromaDB instance:

```bash
python load_philippine_data_to_chromadb.py
```

This creates a `chroma_philippine_data/` directory with three collections:
- **philippine_persons** - 45.4k politicians and public officials
- **philippine_memberships** - 86.2k political positions and party affiliations  
- **philippine_documents** - Legislative bills (Senate & House)

The loading process will show progress bars and takes approximately 5-15 minutes depending on your connection speed.

### 3. Query the Data

```bash
python query_philippine_data.py
```

This provides:
- Example queries for each collection
- Interactive query mode
- Metadata filtering examples

## Why ChromaDB?

**ChromaDB is ideal for this dataset because:**

1. **Semantic Search** - Find documents by meaning, not just keywords
   - Search "infrastructure projects" and find bills about roads, bridges, transportation
   - No need to know exact bill numbers or titles

2. **Vector Embeddings** - Automatically creates embeddings for:
   - Full legislative document content (most valuable)
   - Person names and information
   - Political positions and affiliations

3. **Metadata Filtering** - Combine semantic search with filters:
   - Congress number, document type, region, party, year, etc.

4. **Local & Fast** - No API keys needed, runs entirely on your machine

## Alternative Options

### For Different Use Cases:

1. **DuckDB** (included in original dataset) - Best for:
   - SQL queries and analytics
   - Relational joins between persons/memberships
   - Traditional database operations
   - Already provided by the dataset maintainers

2. **Weaviate** - Best for:
   - Production deployments
   - Multiple vector models
   - More advanced filtering
   - RESTful API needs

3. **Qdrant** - Best for:
   - Very large scale (millions of documents)
   - Advanced filtering requirements
   - Distributed deployments

4. **FAISS** - Best for:
   - Maximum speed
   - Research/prototyping
   - No metadata needed

**Recommendation:** Stick with ChromaDB for this use case. It's the best balance of ease-of-use, features, and performance for local semantic search over government documents.

## Usage Examples

### Python API

```python
import chromadb

# Connect to database
client = chromadb.PersistentClient(path="./chroma_philippine_data")

# Get collection
documents = client.get_collection("philippine_documents")

# Semantic search
results = documents.query(
    query_texts=["infrastructure development projects"],
    n_results=5
)

# With metadata filters
results = documents.query(
    query_texts=["education reform"],
    n_results=5,
    where={"congress": 20}  # Only 20th Congress
)

# Get by ID
doc = documents.get(ids=["specific-document-id"])
```

### Search Memberships

```python
# Find all mayors in a region
memberships = client.get_collection("philippine_memberships")

results = memberships.query(
    query_texts=["Mayor Quezon City"],
    n_results=10
)

# Filter by metadata
results = memberships.get(
    where={
        "position": "MAYOR",
        "region": "NATIONAL CAPITAL REGION"
    },
    limit=20
)
```

### Search Persons

```python
persons = client.get_collection("philippine_persons")

# Find person by name
results = persons.query(
    query_texts=["Juan dela Cruz"],
    n_results=5
)
```

## Data Structure

### Documents Collection
- **ID**: Document identifier
- **Content**: Full legislative text (embedded for semantic search)
- **Metadata**: 
  - `document_type`: 'sb' (Senate Bill) or 'hb' (House Bill)
  - `congress`: Congress number (e.g., 20)
  - `document_number`: Bill number
  - `content_length`: Original content length

### Persons Collection
- **ID**: Person identifier
- **Content**: Full name (embedded for search)
- **Metadata**:
  - `first_name`, `middle_name`, `last_name`, `name_suffix`
  - `nickname`
  - `full_name`: Combined name

### Memberships Collection
- **ID**: Membership identifier
- **Content**: Position details (embedded for search)
- **Metadata**:
  - `person_id`: Link to person
  - `party`: Political party
  - `region`, `province`, `locality`: Geographic info
  - `position`: Role (Mayor, Councilor, etc.)
  - `year`: Year of position

## Database Location

The ChromaDB database is stored at:
```
./chroma_philippine_data/
```

You can:
- Copy this folder to backup the database
- Move it to different locations (update path in scripts)
- Delete it to start fresh

## Performance Tips

1. **Batch Size**: Adjust in loading script if needed
   - Larger batches = faster loading (but more memory)
   - Default is optimized for most systems

2. **Document Truncation**: Very long documents are truncated to 8000 chars
   - Modify `max_length` in script if needed
   - Balance between context and embedding quality

3. **Embedding Model**: ChromaDB uses default model
   - Can configure custom models in ChromaDB settings
   - See ChromaDB docs for advanced configuration

## Troubleshooting

### "Collection not found" error
Run the loader script first: `python load_philippine_data_to_chromadb.py`

### Out of memory during loading
Reduce batch sizes in the loader script (lines with `batch_size=`)

### Slow queries
- ChromaDB builds indexes automatically
- First queries may be slower
- Consider using metadata filters to reduce search space

## Next Steps

1. **Combine with Original DuckDB**: Use DuckDB for analytics, ChromaDB for search
2. **Build a Web Interface**: Create Flask/FastAPI app with search UI
3. **Add Relationships**: Link persons → memberships → documents
4. **Export Results**: Query ChromaDB, export to CSV/JSON for visualization

## Links

- [Dataset on HuggingFace](https://huggingface.co/datasets/bettergovph/raw-philippine-data)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [BetterGov.PH](https://bettergov.ph/)

## License

Dataset: CC0 1.0 Universal (Public Domain)
Scripts: Same as project license




