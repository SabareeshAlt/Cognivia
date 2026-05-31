"""
rebuild_collection.py
Recreates the AcademeRAG collection on Zilliz Cloud with the correct schema:
  - vector dim=1024 (mxbai-embed-large)
  - COSINE metric
  - AUTOINDEX
  - Scalar INVERTED indexes on source, page_number, chunk_index
"""
import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from pymilvus import MilvusClient, CollectionSchema, DataType, FieldSchema

ZILLIZ_URI = os.environ["ACADEMERAG_MILVUS_URI"]
ZILLIZ_TOKEN = os.environ["ACADEMERAG_MILVUS_TOKEN"]
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "AcademeRAG")
VECTOR_DIM = 1024

def rebuild(uri, token, collection_name, dim):
    client = MilvusClient(uri=uri, token=token, timeout=30)

    # Drop if exists (safety guard)
    if client.has_collection(collection_name):
        logger.info("Collection '%s' exists — dropping before recreate.", collection_name)
        client.drop_collection(collection_name)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not client.has_collection(collection_name):
                break
            time.sleep(0.5)
        logger.info("Collection dropped.")

    # Define schema
    fields = [
        FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(name="page_number", dtype=DataType.INT64),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(
        fields=fields,
        description="AcademeRAG document chunks",
        enable_dynamic_field=True,
    )

    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )

    logger.info("Creating collection '%s' (dim=%d, COSINE, AUTOINDEX)...", collection_name, dim)
    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )

    # Wait for collection to become available
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if client.has_collection(collection_name):
            break
        time.sleep(0.5)

    logger.info("Collection '%s' created. Adding scalar INVERTED indexes...", collection_name)

    # Scalar indexes for fast metadata filtering
    for field, name in [
        ("source", "source_idx"),
        ("page_number", "page_number_idx"),
        ("chunk_index", "chunk_index_idx"),
    ]:
        try:
            scalar_index_params = MilvusClient.prepare_index_params()
            scalar_index_params.add_index(
                field_name=field,
                index_name=name,
                index_type="INVERTED",
            )
            client.create_index(
                collection_name=collection_name,
                index_params=scalar_index_params,
            )
            logger.info("  Scalar index created: %s (%s)", name, field)
        except Exception as e:
            logger.warning("  Scalar index '%s' skipped: %s", name, e)

    # Verify
    info = client.describe_collection(collection_name)
    actual_dim = next(
        (f.get("params", {}).get("dim") for f in info["fields"] if f["name"] == "vector"),
        "unknown"
    )
    stats = client.get_collection_stats(collection_name)
    logger.info("Collection ready. dim=%s | row_count=%s", actual_dim, stats.get("row_count", 0))
    return True

if __name__ == "__main__":
    ok = rebuild(ZILLIZ_URI, ZILLIZ_TOKEN, COLLECTION_NAME, VECTOR_DIM)
    sys.exit(0 if ok else 1)
