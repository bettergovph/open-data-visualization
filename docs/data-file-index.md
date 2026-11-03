# Structured data file index

The searchable file inventory is maintained outside this guide at:

- `/Users/joebertj/nep/analysis_output/data-file-index.csv`
- Generator: `/Users/joebertj/nep/index_workspace_data.py`

Regenerate after moving, adding, or refreshing source datasets with:

```sh
python3 /Users/joebertj/nep/index_workspace_data.py
```

The index currently covers both the `nep` and `open-data-visualization` workspaces and contains 18,484 files: 2,931 under `nep` and 15,553 under `open-data-visualization`. It includes CSV, TSV, JSON/JSONL, Parquet, SQLite, DuckDB, XML, GeoJSON, YAML, SQL, Feather, and Arrow files. PDFs and Excel/spreadsheet files are intentionally excluded because their contents need document parsing. Common build/vendor directories such as `.git`, `node_modules`, `target`, and Python caches are skipped.

CSV columns include workspace, relative path, format, bytes, modified time, row/record count where available, top-level structure, fields/columns/tables, a source hint, and any scan note. JSON counts summarize top-level arrays; they do not imply cross-file deduplication. Large JSON files over 50 MB are indexed by path and metadata without parsing their contents. Parquet metadata comes from the local DuckDB CLI; SQLite files are opened read-only.
