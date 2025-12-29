'''
milvus_uri = "./milvus_local.db"
collection_name = "AcademeRAG"
'''

#https://cloud.zilliz.com/orgs/org-ylznfpfacshmpcchxifymn/projects/proj-4f83db2c30bfa02ee2c4d5/clusters/in03-200a60c94a793fc/collections/restaurant_reviews
import os
from pypdf import PdfReader
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document

# List of PDF file paths (make sure these paths are correct relative to your project root)
pdf_paths = [
    os.path.join("Project", "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 1.pdf"),
    os.path.join("Project", "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 2.pdf"),
    os.path.join("Project", "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 3.pdf"),
    os.path.join("Project", "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 4.pdf")
]
#os.path.join("Project", "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 3.pdf"),
def pdfs_to_chunks(pdf_paths, chunk_size=1000):
    all_chunks = []
    for path in pdf_paths:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        # Split text into chunks
        for i in range(0, len(text), chunk_size):
            all_chunks.append(text[i:i+chunk_size])
    return all_chunks

# Initialize Ollama Embeddings model
embeddings = OllamaEmbeddings(model="mxbai-embed-large")

# Milvus database URI and collection name
milvus_uri = "./milvus_local.db"
collection_name = "AcademeRAG"

# Check whether to add documents or reuse existing vector store
add_documents = not os.path.exists(milvus_uri)

# Initialize Milvus vector store
vector_store = Milvus(
    collection_name=collection_name,
    embedding_function=embeddings,
    connection_args={"uri": milvus_uri},
)

# Add documents to the vector store if not already present
if add_documents:
    chunks = pdfs_to_chunks(pdf_paths)
    documents = [Document(page_content=chunk) for chunk in chunks]
    vector_store.add_documents(documents, drop_old=True)

# Create retriever with top 5 results returned for queries
retriever = vector_store.as_retriever(search_kwargs={"k": 5})


'''
MILVUS_URI = "./milvus_local.db" 
COLLECTION_NAME = "AcademeRAG"  
'''
'''
import os
import asyncio
from pypdf import PdfReader
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

pdf_paths = [
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 1.pdf",
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 2.pdf",
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 3.pdf",
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 4.pdf",
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 5.pdf"
]

def load_pdfs(pdf_paths):
    documents = []
    for path in pdf_paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"PDF not found: {path}")

        reader = PdfReader(path)
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                documents.append(
                    Document(
                        page_content=text,
                        metadata={"source": path, "page": page_num}
                    )
                )
    return documents

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100
)

docs = load_pdfs(pdf_paths)
chunks = text_splitter.split_documents(docs)

print(f"Total chunks created: {len(chunks)}")

embeddings = OllamaEmbeddings(model="mxbai-embed-large")


MILVUS_URI = "./milvus_local.db" 
COLLECTION_NAME = "AcademeRAG"            

vector_store = Milvus(
    collection_name=COLLECTION_NAME,
    embedding_function=embeddings,
    connection_args={"uri": MILVUS_URI},
    drop_old=True   # ⚠️ IMPORTANT during development
)

vector_store.add_documents(chunks)
collection = vector_store._collection
print(f"Vectors in Milvus: {collection.num_entities}")

retriever = vector_store.as_retriever(
    search_kwargs={"k": 5}
)
'''

'''
milvus_uri = "./milvus_local.db"
collection_name = "AcademeRAG"
'''
'''
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
import os
from pypdf import PdfReader

# List of PDF file paths

pdf_paths = ["Project/RAG sample 1.pdf","Project/RAG sample 2.pdf","Project/RAG sample 3.pdf","Project/RAG sample 4.pdf","Project/RAG sample 5.pdf"]

def pdfs_to_chunks(pdf_paths, chunk_size=1000):
    all_chunks = []
    for path in pdf_paths:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        # Split text into chunks
        for i in range(0, len(text), chunk_size):
            all_chunks.append(text[i:i+chunk_size])
    return all_chunks

embeddings = OllamaEmbeddings(model="mxbai-embed-large")
milvus_uri = "./milvus_local.db"
collection_name = "AcademeRAG"

add_documents = not os.path.exists(milvus_uri)

vector_store = Milvus(
    collection_name=collection_name,
    embedding_function=embeddings,
    connection_args={"uri": milvus_uri},
)

if add_documents:
    chunks = pdfs_to_chunks(pdf_paths)
    documents = [Document(page_content=chunk) for chunk in chunks]
    vector_store.add_documents(documents, drop_old=True)

retriever = vector_store.as_retriever(search_kwargs={"k": 5})
'''
'''
import os
import asyncio
from pypdf import PdfReader
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

pdf_paths = [
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 1.pdf",
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 2.pdf",
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 3.pdf",
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 4.pdf",
    "/Users/apple/Applications/Visual Studio Code/Project/RAG sample 5.pdf"
]


def load_pdfs(pdf_paths):
    documents = []
    for path in pdf_paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"PDF not found: {path}")
        reader = PdfReader(path)
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                documents.append(
                    Document(
                        page_content=text,
                        metadata={"source": path, "page": page_num}
                    )
                )
    return documents


text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100
)

docs = load_pdfs(pdf_paths)
chunks = text_splitter.split_documents(docs)

print(f"Total chunks created: {len(chunks)}")

embeddings = OllamaEmbeddings(model="mxbai-embed-large")

MILVUS_URI = ""  # already filled by you
COLLECTION_NAME = ""  # already filled by you
vector_store = Milvus(
    collection_name=COLLECTION_NAME,
    embedding_function=embeddings,
    connection_args={"uri": MILVUS_URI},
    drop_old=True  # ⚠️ IMPORTANT during development
)

vector_store.add_documents(chunks)
collection = vector_store._collection
print(f"Vectors in Milvus: {collection.num_entities}")

retriever = vector_store.as_retriever(
    search_kwargs={"k": 5}
)
'''