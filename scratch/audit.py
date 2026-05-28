import os
import sys

# Connect to Milvus locally and audit
try:
    from pymilvus import MilvusClient
except ImportError:
    print("pymilvus not installed")
    sys.exit(1)

def audit():
    try:
        client = MilvusClient(uri="http://127.0.0.1:19530")
        collections = client.list_collections()
        print(f"Collections: {collections}")
        
        if "academerag" in collections:
            desc = client.describe_collection("academerag")
            print(f"Schema: {desc}")
            
            stats = client.get_collection_stats("academerag")
            print(f"Stats: {stats}")
            
            # check vectors
            res = client.query(collection_name="academerag", filter="pk >= 0", output_fields=["pk", "vector"], limit=10)
            print(f"Vectors sample size: {len(res)}")
            if res:
                v = res[0]["vector"]
                print(f"Sample Vector Dimension: {len(v)}")
                # check norm
                norm = sum(x*x for x in v)
                print(f"Sample Vector Norm: {norm}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    audit()
