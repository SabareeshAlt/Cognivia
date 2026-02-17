import os
import glob
import logging
from functools import lru_cache

# --- CRITICAL: Disable Async for Django ---
os.environ["MILVUS_ASYNC"] = "0"

from dotenv import load_dotenv
from pypdf import PdfReader
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

logger = logging.getLogger(__name__)

# Project Paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = PROJECT_ROOT

# Load .env from project root
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Also create api/documents folder for future uploads
api_docs_dir = os.path.join(PROJECT_ROOT, "api", "documents")
if not os.path.exists(api_docs_dir):
    os.makedirs(api_docs_dir)

def _get_milvus_config():
    """Returns Milvus Cloud configuration. Enforces Zilliz Cloud — no local fallback."""
    milvus_uri = os.getenv("ACADEMERAG_MILVUS_URI", "https://in03-200a60c94a793fc.serverless.aws-eu-central-1.cloud.zilliz.com")
    milvus_token = os.getenv("ACADEMERAG_MILVUS_TOKEN", "4919d7d24e84b881bac067ed51e05c4749fe5af98b16a4d8249dbbff6684e5d86825b2de320d795b33d5a82e540efd86958f289c")

    if not milvus_uri or not milvus_uri.startswith("https://"):
        raise ValueError(
            "ACADEMERAG_MILVUS_URI must be set to a Zilliz Cloud URL (https://...) in .env. "
            "Local milvus-lite is NOT supported."
        )
    if not milvus_token:
        raise ValueError(
            "ACADEMERAG_MILVUS_TOKEN must be set in .env with your Zilliz Cloud API key."
        )

    return {
        "uri": milvus_uri,
        "token": milvus_token,
        "collection": os.getenv("COLLECTION_NAME", "AcademeRAG"),
        "model": os.getenv("EMBEDDING_MODEL", "mxbai-embed-large"),
        "is_cloud": True,
    }

def load_and_chunk_pdfs():
    """Scans the PDF_DIR for any .pdf file and chunks it."""
    pdf_files = glob.glob(os.path.join(PDF_DIR, "*.pdf"))
    if not pdf_files:
        print(f"⚠️  No PDFs found in {PDF_DIR}")
        return []

    print(f"Found {len(pdf_files)} PDFs. Processing...")
    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=200)

    for path in pdf_files:
        try:
            reader = PdfReader(path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            chunks = splitter.split_text(text)
            source = os.path.basename(path)
            for chunk in chunks:
                all_chunks.append(Document(page_content=chunk, metadata={"source": source}))
            print(f"  - Loaded: {source}")
        except Exception as e:
            print(f"  - Error loading {path}: {e}")
    return all_chunks

def initialize_vector_store(force_reindex=False):
    """Initializes and optionally populates the Milvus Cloud vector store."""
    cfg = _get_milvus_config()
    embeddings = OllamaEmbeddings(
        model=cfg["model"],
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
    
    conn_args = {"uri": cfg["uri"], "token": cfg["token"]}

    try:
        vector_store = Milvus(
            collection_name=cfg["collection"],
            embedding_function=embeddings,
            connection_args=conn_args,
            auto_id=True,
            drop_old=force_reindex 
        )
        logger.info(f"✅ Connected to Milvus Cloud: {cfg['uri'][:40]}...")
    except Exception as e:
        logger.error(f"Milvus Cloud Connection Error: {e}")
        return None

    # Auto-Index Check
    if not force_reindex:
        try:
            if not vector_store.similarity_search("test", k=1):
                logger.warning("⚠️  Collection appears empty. Triggering index...")
                force_reindex = True
        except:
            force_reindex = True

    if force_reindex:
        docs = load_and_chunk_pdfs()
        if docs:
            vector_store.add_documents(docs)
            logger.info(f"✅ Indexed {len(docs)} chunks into Milvus Cloud.")
            
    return vector_store

@lru_cache(maxsize=1)
def get_retriever():
    """Singleton accessor for the retriever."""
    store = initialize_vector_store()
    if store:
        return store.as_retriever(search_kwargs={"k": 3})
    return None

def get_rag_chain():
    """Builds the RAG chain."""
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
    """Non-streaming response generator."""
    chain = get_rag_chain()
    return chain.invoke(question)

def stream_optimized_response(question: str):
    """Generator for streaming tokens."""
    chain = get_rag_chain()
    for chunk in chain.stream(question):
        yield chunk