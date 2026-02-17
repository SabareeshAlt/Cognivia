import os
import logging
from functools import lru_cache

# --- CRITICAL: Disable Async for Django ---
os.environ["MILVUS_ASYNC"] = "0"

from pypdf import PdfReader
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

logger = logging.getLogger(__name__)

# --- MANUAL PATH CONFIGURATION ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# List of specific PDF files in the Project folder
pdf_paths = [
    os.path.join(PROJECT_ROOT, "RAG sample 1.pdf"),
    os.path.join(PROJECT_ROOT, "RAG sample 2.pdf"),
    os.path.join(PROJECT_ROOT, "RAG sample 3.pdf"),
]

# Path for the Milvus database file
MILVUS_DB_PATH = os.path.join(PROJECT_ROOT, "milvus_local.db")

def _get_milvus_config():
    """Returns Milvus configuration with manual paths."""
    milvus_uri = os.getenv("ACADEMERAG_MILVUS_URI", MILVUS_DB_PATH)
    milvus_token = os.getenv("ACADEMERAG_MILVUS_TOKEN", "")
    is_cloud = milvus_uri.startswith("https://") or milvus_uri.startswith("http://")
    
    return {
        "uri": milvus_uri,
        "token": milvus_token,
        "collection": "AcademeRAG",
        "model": "mxbai-embed-large",
        "is_cloud": is_cloud
    }

def load_and_chunk_pdfs():
    """Extracts text from the specific list of PDF paths and chunks them."""
    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=200)

    # UPDATED: Now loops through your manual list instead of globbing a folder
    for path in pdf_paths:
        if not os.path.exists(path):
            print(f"⚠️  File not found, skipping: {path}")
            continue

        try:
            reader = PdfReader(path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            
            if not text.strip():
                print(f"⚠️  No text extracted from: {path}")
                continue
                
            chunks = splitter.split_text(text)
            source = os.path.basename(path)
            for chunk in chunks:
                all_chunks.append(Document(page_content=chunk, metadata={"source": source}))
            print(f"  - Successfully loaded: {source}")
        except Exception as e:
            print(f"  - Error loading {path}: {e}")
            
    return all_chunks

def initialize_vector_store(force_reindex=False):
    """Initializes and optionally populates the vector store."""
    cfg = _get_milvus_config()
    embeddings = OllamaEmbeddings(model=cfg["model"])
    
    conn_args = {"uri": cfg["uri"]}
    if cfg["is_cloud"] and cfg["token"]:
        conn_args["token"] = cfg["token"]

    # Lock file safety check
    if not cfg["is_cloud"] and os.path.exists(cfg["uri"] + ".lock"):
        try:
            os.remove(cfg["uri"] + ".lock")
        except: pass

    try:
        vector_store = Milvus(
            collection_name=cfg["collection"],
            embedding_function=embeddings,
            connection_args=conn_args,
            auto_id=True,
            drop_old=force_reindex 
        )
    except Exception as e:
        logger.error(f"Milvus Connection Error: {e}")
        return None

    if not force_reindex:
        try:
            # Check if index has content
            if not vector_store.similarity_search("test", k=1):
                force_reindex = True
        except:
            force_reindex = True

    if force_reindex:
        docs = load_and_chunk_pdfs()
        if docs:
            vector_store.add_documents(docs)
            print(f"✅ Indexed {len(docs)} chunks into Milvus.")
            
    return vector_store

@lru_cache(maxsize=1)
def get_retriever():
    store = initialize_vector_store()
    return store.as_retriever(search_kwargs={"k": 3}) if store else None

def get_rag_chain():
    retriever = get_retriever()
    if not retriever:
        raise ConnectionError("Vector Database unavailable.")
    
    llm = ChatOllama(model="llama3.2", temperature=0.7)
    prompt = ChatPromptTemplate.from_template("""
    You are an intelligent College AI Assistant.
    Answer purely based on the context below.
    
    Context:
    {context}
    
    Question:
    {question}
    """)

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    return (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

def get_optimized_response(question: str) -> str:
    return get_rag_chain().invoke(question)

def stream_optimized_response(question: str):
    for chunk in get_rag_chain().stream(question):
        yield chunk