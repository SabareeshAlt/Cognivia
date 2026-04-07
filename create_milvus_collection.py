#!/usr/bin/env python3
"""Create (or recreate) Milvus collection schema and ingest all documents."""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Milvus import (  # noqa: E402
    _get_milvus_config,
    collection_exists,
    compute_rebuild_state,
    get_retrieval_diagnostics,
    initialize_vector_store,
)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        force=True,
    )

    parser = argparse.ArgumentParser(description="Bootstrap Milvus collection and ingest documents.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate collection schema before ingest.",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Create/recreate schema only, skip ingestion.",
    )
    parser.add_argument(
        "--recreate-safe",
        action="store_true",
        help="Recreate only when tracked corpus changed; reuse identical existing collection.",
    )
    args = parser.parse_args()

    cfg = _get_milvus_config()
    if cfg is None:
        print("Milvus cloud is disabled/unconfigured. Check .env.", file=sys.stderr)
        return 1
    print(f"Milvus target: {cfg['uri']}", flush=True)
    print(f"Collection: {cfg['collection']}", flush=True)

    if args.recreate and args.recreate_safe:
        print("Use either --recreate or --recreate-safe, not both.", file=sys.stderr)
        return 2

    if args.schema_only:
        store = initialize_vector_store(
            force_reindex=args.recreate,
            recreate_collection_on_sync=args.recreate,
        )
        if not store:
            print("Schema bootstrap failed.", file=sys.stderr)
            return 1
        print("Collection schema is ready.", flush=True)
        return 0

    print("Starting ingestion (schema is ensured before ingest)...", flush=True)
    if args.recreate_safe:
        exists = collection_exists(cfg)
        should_rebuild, reason = compute_rebuild_state(force_reindex=False)
        print(
            f"Safe recreate check: exists={exists} should_rebuild={should_rebuild} reason={reason}",
            flush=True,
        )
        if exists and not should_rebuild:
            print("Collection unchanged. Reusing existing collection without drop.", flush=True)
            store = initialize_vector_store(force_reindex=False, recreate_collection_on_sync=False)
        else:
            print("Change detected (or collection missing). Rebuilding collection now.", flush=True)
            store = initialize_vector_store(force_reindex=True, recreate_collection_on_sync=True)
    else:
        store = initialize_vector_store(
            force_reindex=True if args.recreate else False,
            recreate_collection_on_sync=True,
        )
    if not store:
        diagnostics = get_retrieval_diagnostics()
        source_rows = diagnostics.get("sources", [])
        indexed_any = any(isinstance(row.get("milvus_chunks"), int) and row.get("milvus_chunks", 0) > 0 for row in source_rows)
        if not indexed_any:
            print("Ingestion failed.", file=sys.stderr)
            return 1
        print(
            "Ingestion completed, but LangChain Milvus wrapper is unavailable in this runtime. "
            "Direct Milvus client retrieval will be used.",
            flush=True,
        )
        print("Per-source index status:", flush=True)
        for row in source_rows:
            source = row.get("source", "unknown")
            tracked = row.get("tracked")
            hash_match = row.get("hash_match")
            milvus_chunks = row.get("milvus_chunks")
            chunk_text = (
                str(milvus_chunks)
                if isinstance(milvus_chunks, int)
                else f"error={row.get('milvus_count_error') or 'unavailable'}"
            )
            print(
                f"  - {source}: tracked={tracked} hash_match={hash_match} milvus_chunks={chunk_text}",
                flush=True,
            )
        return 0

    probe = store.similarity_search("collection validation probe", k=3)
    print(f"Collection ready. Probe returned {len(probe)} results.")
    try:
        diagnostics = get_retrieval_diagnostics()
        source_rows = diagnostics.get("sources", [])
        if source_rows:
            print("Per-source index status:", flush=True)
            for row in source_rows:
                source = row.get("source", "unknown")
                tracked = row.get("tracked")
                hash_match = row.get("hash_match")
                milvus_chunks = row.get("milvus_chunks")
                chunk_text = (
                    str(milvus_chunks)
                    if isinstance(milvus_chunks, int)
                    else f"error={row.get('milvus_count_error') or 'unavailable'}"
                )
                print(
                    f"  - {source}: tracked={tracked} hash_match={hash_match} milvus_chunks={chunk_text}",
                    flush=True,
                )
    except Exception as exc:
        print(f"Warning: source verification failed: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
