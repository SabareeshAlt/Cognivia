'''
milvus_uri = "https://cloud.zilliz.com/orgs/org-ylznfpfacshmpcchxifymn/projects/proj-4f83db2c30bfa02ee2c4d5/clusters/in03-200a60c94a793fc/collections/restaurant_reviews"

# Collection name inside Milvus
collection_name = "AcademeRAG"
'''
#milvus_uri = "https://in03-200a60c94a793fc.serverless.aws-eu-central-1.cloud.zilliz.com"
#4919d7d24e84b881bac067ed51e05c4749fe5af98b16a4d8249dbbff6684e5d86825b2de320d795b33d5a82e540efd86958f289c
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
import os
from langchain_core.documents import Document

# Embeddings model to generate vector embeddings for text content
embeddings = OllamaEmbeddings(model="mxbai-embed-large")

# Local Milvus database URI (using Milvus Lite local file-based DB)
milvus_uri = "https://in03-200a60c94a793fc.serverless.aws-eu-central-1.cloud.zilliz.com"  # Set your actual path here

# Collection name inside Milvus - use a meaningful name for your application
collection_name = "AcademeRAG"

# Initialize the Milvus vector store with your embeddings and connection info
vector_store = Milvus(
    collection_name=collection_name,
    embedding_function=embeddings,
    connection_args={"uri": milvus_uri},
)

# Create retriever interface for querying, returns the top 5 relevant documents by default
retriever = vector_store.as_retriever(search_kwargs={"k": 5})


'''
milvus_uri = "https://in03-200a60c94a793fc.serverless.aws-eu-central-1.cloud.zilliz.com"  # your running Milvus server
collection_name = "AcademeRAG"
"token": "4919d7d24e84b881bac067ed51e05c4749fe5af98b16a4d8249dbbff6684e5d86825b2de320d795b33d5a82e540efd86958f289c"

'''
'''
import os
from functools import lru_cache
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus  # LangChain Milvus vector store [web:63][web:62]

# Local Milvus defaults (update for your setup)
# For Docker Milvus Standalone:
#   docker run -d -p 19530:19530 milvusdb/milvus:latest  [web:54][web:46]
MILVUS_URI = "https://in03-200a60c94a793fc.serverless.aws-eu-central-1.cloud.zilliz.com"   # or "./milvus.db" for Milvus Lite file [web:54]
COLLECTION_NAME = "AcademeRAG"     # must match what vector.py used when ingesting


@lru_cache(maxsize=1)
def get_retriever():
    """Cached retriever - connects once, reuses forever."""
    if not MILVUS_URI or not COLLECTION_NAME:
        raise ValueError("MILVUS_URI and COLLECTION_NAME must be set in Milvus.py")

    # Embedding model served by Ollama: mxbai-embed-large [web:33][web:37]
    embeddings = OllamaEmbeddings(model="mxbai-embed-large")

    vector_store = Milvus(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        connection_args={"uri": MILVUS_URI},  # recommended pattern in LangChain docs [web:63][web:64]
        drop_old=False,
    )
    return vector_store.as_retriever(search_kwargs={"k": 5})


# Manual test: python Milvus.py
if __name__ == "__main__":
    print("Testing Milvus connection...")
    retriever = get_retriever()
    print("✅ Milvus retriever ready!", retriever)
'''

'''
milvus_uri = "https://cloud.zilliz.com/orgs/org-ylznfpfacshmpcchxifymn/projects/proj-4f83db2c30bfa02ee2c4d5/clusters/in03-200a60c94a793fc/collections/restaurant_reviews"

# Collection name inside Milvus
collection_name = "AcademeRAG"
'''
'''
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
import os
from langchain_core.documents import Document

# Embeddings model to generate vector embeddings for text content
embeddings = OllamaEmbeddings(model="mxbai-embed-large")

# Local Milvus database URI (using Milvus Lite local file-based DB)
milvus_uri = "https://cloud.zilliz.com/orgs/org-ylznfpfacshmpcchxifymn/projects/proj-4f83db2c30bfa02ee2c4d5/clusters/in03-200a60c94a793fc/collections/AcademeRAG"

# Collection name inside Milvus
collection_name = "AcademeRAG"

# Initialize the Milvus vector store with your embeddings and connection info
vector_store = Milvus(
    embedding_function=embeddings,
    connection_args={"uri": milvus_uri},
    collection_name=collection_name,
)

# Create retriever interface for querying
retriever = vector_store.as_retriever(search_kwargs={"k": 5})
'''


#Correct code
'''
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus


embeddings = OllamaEmbeddings(model="mxbai-embed-large")

milvus_uri = "https://cloud.zilliz.com/orgs/org-ylznfpfacshmpcchxifymn/projects/proj-4f83db2c30bfa02ee2c4d5/clusters/in03-200a60c94a793fc/collections/AcademeRAG"
collection_name = "AcademeRAG"

vector_store = Milvus(
    collection_name=collection_name,
    embedding_function=embeddings,
    connection_args={
        "uri": milvus_uri,
        "token": "4919d7d24e84b881bac067ed51e05c4749fe5af98b16a4d8249dbbff6684e5d86825b2de320d795b33d5a82e540efd86958f289c",
        "db_name": "AcademeRAG",  # or your DB name
    },
)

retriever = vector_store.as_retriever(search_kwargs={"k": 5})
'''