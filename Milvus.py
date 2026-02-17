import os
import logging
import warnings
from functools import lru_cache

# --- CRITICAL: Disable Async for Django ---
os.environ["MILVUS_ASYNC"] = "0"

# Suppress deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*pkg_resources.*')

from dotenv import load_dotenv
from pypdf import PdfReader
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- PATH CONFIGURATION ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "documents")

# Load .env from project root
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

COLLECTION_NAME = os.getenv("COLLECTION_NAME", "AcademeRAG")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "mxbai-embed-large")
LLM_MODEL = os.getenv("ACADEMERAG_LLM_MODEL", "llama3.2")

# Ensure documents directory exists
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

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
        "collection": COLLECTION_NAME,
        "model": EMBEDDING_MODEL,
        "is_cloud": True,
    }

def get_pdf_files():
    """Get list of PDF files from documents directory."""
    pdf_files = []
    
    # Check documents directory
    if os.path.exists(DOCUMENTS_DIR):
        for filename in os.listdir(DOCUMENTS_DIR):
            if filename.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(DOCUMENTS_DIR, filename))
    
    # Also check root directory for RAG sample PDFs
    for filename in ["RAG sample 1.pdf", "RAG sample 2.pdf", "RAG sample 3.pdf"]:
        root_path = os.path.join(PROJECT_ROOT, filename)
        if os.path.exists(root_path):
            pdf_files.append(root_path)
    
    return pdf_files

def load_and_chunk_pdfs():
    """Extracts text from PDF files and chunks them."""
    logger.info("=" * 60)
    logger.info("📚 Loading and Processing PDFs")
    logger.info("=" * 60)
    
    pdf_files = get_pdf_files()
    
    if not pdf_files:
        logger.warning(f"⚠️  No PDF files found!")
        logger.warning(f"   Searched in: {DOCUMENTS_DIR}")
        logger.warning(f"   Also checked root: {PROJECT_ROOT}")
        logger.warning("💡 Please add PDF files to continue.")
        return []
    
    logger.info(f"✅ Found {len(pdf_files)} PDF file(s):")
    for pdf_path in pdf_files:
        logger.info(f"   📄 {os.path.basename(pdf_path)}")
    
    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    for pdf_path in pdf_files:
        try:
            logger.info(f"\n📖 Processing: {os.path.basename(pdf_path)}")
            reader = PdfReader(pdf_path)
            
            # Extract text from all pages
            text = ""
            for i, page in enumerate(reader.pages, 1):
                page_text = page.extract_text() or ""
                text += page_text
                if i % 10 == 0:
                    logger.info(f"   ⏳ Processed {i}/{len(reader.pages)} pages")
            
            logger.info(f"   ✅ Extracted {len(reader.pages)} pages, {len(text)} characters")
            
            if not text.strip():
                logger.warning(f"   ⚠️  No text extracted from {os.path.basename(pdf_path)}")
                continue
            
            # Split into chunks
            chunks = splitter.split_text(text)
            source = os.path.basename(pdf_path)
            
            for chunk in chunks:
                all_chunks.append(Document(
                    page_content=chunk,
                    metadata={"source": source}
                ))
            
            logger.info(f"   ✂️  Created {len(chunks)} chunks")
            
        except Exception as e:
            logger.error(f"   ❌ Error processing {os.path.basename(pdf_path)}: {e}")
            continue
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Total: {len(all_chunks)} chunks from {len(pdf_files)} PDF(s)")
    logger.info("=" * 60)
    
    return all_chunks

def initialize_vector_store(force_reindex=False):
    """Initializes and optionally populates the Milvus Cloud vector store."""
    logger.info("\n" + "=" * 60)
    logger.info("🚀 Initializing Milvus Cloud Vector Store")
    logger.info("=" * 60)
    
    cfg = _get_milvus_config()
    
    logger.info(f"📊 Configuration:")
    logger.info(f"   Cloud URI: {cfg['uri'][:40]}...")
    logger.info(f"   Collection: {cfg['collection']}")
    logger.info(f"   Embedding Model: {cfg['model']}")
    
    try:
        # Initialize embeddings
        logger.info(f"\n🔧 Loading embedding model: {cfg['model']}")
        embeddings = OllamaEmbeddings(
            model=cfg["model"],
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
        logger.info("   ✅ Embedding model loaded")
        
        conn_args = {"uri": cfg["uri"], "token": cfg["token"]}
        
        if force_reindex:
            logger.info(f"\n� Force reindex: creating new collection with documents...")
            
            # Load and chunk PDFs
            docs = load_and_chunk_pdfs()
            
            if not docs:
                logger.error("❌ No documents to index!")
                return None
            
            # Create vector store with documents (drops old collection)
            logger.info(f"\n🔄 Creating Milvus Cloud collection and adding {len(docs)} chunks...")
            vector_store = Milvus.from_documents(
                documents=docs,
                embedding=embeddings,
                collection_name=cfg["collection"],
                connection_args=conn_args,
            )
            logger.info(f"✅ Vector store created with {len(docs)} chunks")
            
        else:
            # Connect to existing cloud collection
            logger.info(f"\n🔌 Connecting to existing Milvus Cloud collection...")
            vector_store = Milvus(
                collection_name=cfg["collection"],
                embedding_function=embeddings,
                connection_args=conn_args,
            )
            logger.info("   ✅ Connected to Milvus Cloud")
        
        # Verify the store works
        logger.info("\n🧪 Testing vector store...")
        try:
            test_results = vector_store.similarity_search("test query", k=1)
            logger.info(f"   ✅ Vector store is operational (found {len(test_results)} result(s))")
        except Exception as e:
            logger.warning(f"   ⚠️  Test query returned: {e}")
            if not force_reindex:
                logger.info("   💡 Collection may be empty. Run setup_milvus.py to index documents.")
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ Milvus Cloud Vector Store Ready!")
        logger.info("=" * 60 + "\n")
        
        return vector_store
        
    except Exception as e:
        logger.error(f"\n❌ Error initializing vector store: {e}")
        import traceback
        traceback.print_exc()
        return None

@lru_cache(maxsize=1)
def get_retriever():
    """Singleton accessor for the retriever."""
    logger.info("🔍 Getting retriever instance...")
    store = initialize_vector_store()
    if store:
        retriever = store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 3}
        )
        logger.info("✅ Retriever ready")
        return retriever
    logger.error("❌ Failed to create retriever")
    return None

def get_rag_chain():
    """Builds the RAG chain."""
    logger.info("🔗 Building RAG chain...")
    retriever = get_retriever()
    if not retriever:
        raise ConnectionError("Vector Database unavailable.")
    
    llm = ChatOllama(
        model=LLM_MODEL,
        base_url="http://localhost:11434",
        temperature=0.7
    )
    
    prompt = ChatPromptTemplate.from_template("""
    You are an intelligent College AI Assistant.
    Answer purely based on the context below.
    
    Context:
    {context}
    
    Question:
    {question}
    
    Answer:""")
    
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)
    
    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    
    logger.info("✅ RAG chain built successfully")
    return chain

def get_optimized_response(question: str) -> str:
    """Non-streaming response generator."""
    logger.info(f"💬 Processing question: {question[:50]}...")
    chain = get_rag_chain()
    answer = chain.invoke(question)
    logger.info(f"✅ Generated answer ({len(answer)} chars)")
    return answer

def stream_optimized_response(question: str):
    """Generator for streaming tokens."""
    logger.info(f"💬 Processing streaming question: {question[:50]}...")
    chain = get_rag_chain()
    for chunk in chain.stream(question):
        yield chunk

# Test function
def test_vector_store():
    """Test the vector store setup."""
    print("\n" + "=" * 60)
    print("🧪 Testing Milvus Vector Store")
    print("=" * 60 + "\n")
    
    store = initialize_vector_store(force_reindex=False)
    
    if store:
        print("\n✅ Vector store is working!")
        
        # Test query
        print("\n🔍 Running test query...")
        results = store.similarity_search("What is this document about?", k=3)
        
        print(f"\n📊 Found {len(results)} results:")
        for i, doc in enumerate(results, 1):
            print(f"\n{i}. Source: {doc.metadata.get('source', 'Unknown')}")
            print(f"   Content: {doc.page_content[:150]}...")
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
    else:
        print("\n❌ Vector store failed to initialize")

if __name__ == "__main__":
    test_vector_store()
