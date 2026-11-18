"""Build a compact exact-title fallback index for project-details popups."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static/nep-preview"
CONTEXT = STATIC / "project-context"
BUCKET_COUNT = 64


def normalize(value: object) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def bucket(value: str) -> str:
    value_hash = 2166136261
    for byte in value.encode("utf-8"):
        value_hash = ((value_hash ^ byte) * 16777619) & 0xFFFFFFFF
    return f"{value_hash & (BUCKET_COUNT - 1):02x}"


def main() -> None:
    shards: dict[str, list[dict[str, object]]] = {f"{i:02x}": [] for i in range(BUCKET_COUNT)}
    rows_by_id: dict[str, dict[str, object]] = {}
    coverage = STATIC / "hgab-document-coverage-shards"
    for path in sorted(coverage.glob("projects-*.json")):
        for row in json.loads(path.read_text()).get("rows", []):
            rows_by_id[str(row.get("hgabId") or "")] = {
                "hgabId": row.get("hgabId"), "title": row.get("title"),
                "office": row.get("office"), "region": row.get("region"),
                "amountPesos": row.get("amountPesos"),
            }
    # Keep titles from the comparison set too; these are the rows with parsed
    # POW totals and supporting-document amount work.
    comparison = json.loads((STATIC / "expectation-vs-reality-data.json").read_text())
    for row in comparison.get("projects", []):
        rows_by_id.setdefault(str(row.get("hgabId") or ""), {
            "hgabId": row.get("hgabId"), "title": row.get("title"),
            "office": row.get("office"), "region": row.get("region"),
            "amountPesos": row.get("allocationPesos"),
        })
    for row in rows_by_id.values():
        title = str(row.get("title") or "").strip()
        normalized = normalize(title)
        if not normalized or not row.get("hgabId"):
            continue
        shards[bucket(normalized)].append({"normalizedTitle": normalized, **row})

    context_manifest_path = CONTEXT / "manifest.json"
    context_manifest = json.loads(context_manifest_path.read_text())
    titles_by_id = {str(row["hgabId"]): str(row["title"]) for row in rows_by_id.values() if row.get("hgabId") and row.get("title")}
    for key, meta in context_manifest["shards"].items():
        path = CONTEXT / meta["path"]
        data = json.loads(path.read_text())
        changed = False
        for row in data.get("projects", []):
            title = titles_by_id.get(str(row.get("hgabId") or ""))
            if title and row.get("title") != title:
                row["title"] = title
                changed = True
        if changed:
            raw = (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            path.write_bytes(raw)
            meta["bytes"] = len(raw)
            meta["version"] = hashlib.sha256(raw).hexdigest()[:8]
    context_manifest["sourceVersion"] = hashlib.sha256(json.dumps(titles_by_id, sort_keys=True).encode()).hexdigest()[:16]
    context_manifest_path.write_text(json.dumps(context_manifest, ensure_ascii=False, separators=(",", ":")) + "\n")

    target = CONTEXT / "title-index"
    target.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"schemaVersion": 1, "shards": {}}
    for key, rows in shards.items():
        raw = (json.dumps({"rows": rows}, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        filename = f"{key}.json"
        (target / filename).write_bytes(raw)
        manifest["shards"][key] = {
            "path": filename,
            "version": hashlib.sha256(raw).hexdigest()[:10],
            "rows": len(rows),
            "bytes": len(raw),
        }
    raw_manifest = (json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    (target / "manifest.json").write_bytes(raw_manifest)
    print(f"Wrote title lookup for {sum(len(rows) for rows in shards.values()):,} projects")


if __name__ == "__main__":
    main()
