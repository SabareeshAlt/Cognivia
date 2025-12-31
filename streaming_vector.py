"""
Streaming Vector Store Module
Handles PDF processing with streaming/chunking to avoid memory overload
"""

import os
from pathlib import Path
from typing import Generator, List
from pypdf import PdfReader
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
import logging

logger = logging.getLogger(__name__)

# Configuration
BASE_DIR = Path(__file__).parent
PDF_DIR = BASE_DIR / "documents"  # Create 'documents' folder with PDFs
MILVUS_URI = "./milvus_local.db"
COLLECTION_NAME = "AcademeRAG"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


class StreamingPDFProcessor:
    """
    Generator-based PDF processor that streams chunks without loading entire file
    into memory. This prevents OOM errors on large PDFs.
    """
    
    def __init__(self, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap
        logger.info(f"Initialized PDF processor (chunk_size={chunk_size}, overlap={overlap})")
    
    def stream_pdf_chunks(self, pdf_path: str) -> Generator[str, None, None]:
        """
        Stream chunks from a single PDF without loading entire file into memory.
        
        Args:
            pdf_path: Path to PDF file
            
        Yields:
            Text chunks of specified size with overlap
        """
        try:
            logger.info(f"Processing PDF: {pdf_path}")
            reader = PdfReader(pdf_path)
            buffer = ""
            page_count = 0
            
            for page_num, page in enumerate(reader.pages):
                try:
                    text = page.extract_text()
                    if text:
                        buffer += text + "\n"
                        page_count += 1
                        
                        # Yield chunks as buffer fills up
                        while len(buffer) >= self.chunk_size:
                            chunk = buffer[:self.chunk_size]
                            yield chunk
                            # Keep overlap for context continuity
                            buffer = buffer[self.chunk_size - self.overlap:]
                            logger.debug(f"Yielded chunk from page {page_num + 1}")
                
                except Exception as e:
                    logger.warning(f"Error processing page {page_num + 1}: {e}")
                    continue
            
            # Yield remaining buffer
            if buffer.strip():
                yield buffer
                logger.debug("Yielded final buffer chunk")
            
            logger.info(f"Completed processing {pdf_path} ({page_count} pages)")
            
        except Exception as e:
            logger.error(f"Error reading PDF {pdf_path}: {e}")
            raise
    
    def stream_all_pdfs(self, pdf_paths: List[str]) -> Generator[tuple, None, None]:
        """
        Stream chunks from multiple PDFs.
        
        Args:
            pdf_paths: List of PDF file paths
            
        Yields:
            Tuples of (chunk_text, source_file)
        """
        for pdf_path in pdf_paths:
            if not os.path.exists(pdf_path):
                logger.warning(f"PDF not found: {pdf_path}")
                continue
            
            for chunk in self.stream_pdf_chunks(pdf_path):
                yield (chunk, os.path.basename(pdf_path))


class StreamingVectorStore:
    """
    Wrapper around Milvus vector store with streaming document insertion.
    Adds documents in batches to avoid memory issues and improve performance.
    """
    
    def __init__(
        self,
        collection_name: str = COLLECTION_NAME,
        milvus_uri: str = MILVUS_URI,
        batch_size: int = 50
    ):
        self.collection_name = collection_name
        self.milvus_uri = milvus_uri
        self.batch_size = batch_size
        
        # Initialize embeddings
        logger.info("Initializing OllamaEmbeddings...")
        self.embeddings = OllamaEmbeddings(model="mxbai-embed-large")
        
        # Initialize Milvus vector store
        logger.info("Initializing Milvus vector store...")
        self.vector_store = Milvus(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            connection_args={"uri": milvus_uri},
        )
        logger.info("Vector store initialized successfully")
    
    def add_documents_streaming(
        self,
        pdf_processor: StreamingPDFProcessor,
        pdf_paths: List[str],
        drop_old: bool = False
    ) -> int:
        """
        Add documents to vector store using streaming to manage memory.
        
        Args:
            pdf_processor: StreamingPDFProcessor instance
            pdf_paths: List of PDF file paths
            drop_old: Whether to drop old collection before adding
            
        Returns:
            Total number of documents added
        """
        logger.info(f"Starting streaming document addition from {len(pdf_paths)} PDFs")
        
        batch = []
        doc_count = 0
        
        try:
            for chunk_text, source_file in pdf_processor.stream_all_pdfs(pdf_paths):
                # Create document with metadata
                doc = Document(
                    page_content=chunk_text,
                    metadata={"source": source_file}
                )
                batch.append(doc)
                
                # Add batch when it reaches batch_size
                if len(batch) >= self.batch_size:
                    logger.info(f"Adding batch of {len(batch)} documents...")
                    self.vector_store.add_documents(
                        batch,
                        drop_old=drop_old if doc_count == 0 else False
                    )
                    doc_count += len(batch)
                    batch = []
            
            # Add remaining documents
            if batch:
                logger.info(f"Adding final batch of {len(batch)} documents...")
                self.vector_store.add_documents(batch)
                doc_count += len(batch)
            
            logger.info(f"Successfully added {doc_count} documents to vector store")
            return doc_count
            
        except Exception as e:
            logger.error(f"Error during streaming document addition: {e}")
            raise
    
    def get_retriever(self, k: int = 5):
        """
        Get a retriever from the vector store.
        
        Args:
            k: Number of results to retrieve
            
        Returns:
            Retriever instance
        """
        return self.vector_store.as_retriever(search_kwargs={"k": k})


def initialize_vector_store(
    pdf_paths: List[str] = None,
    force_reload: bool = False
):
    """
    Initialize the streaming vector store and load PDFs if needed.
    
    Args:
        pdf_paths: List of PDF paths to load. If None, uses default PDF_DIR
        force_reload: Force reload even if Milvus DB exists
        
    Returns:
        Tuple of (vector_store, retriever)
    """
    # Get PDF paths
    if pdf_paths is None:
        pdf_paths = list(BASE_DIR.glob("*.pdf"))
        logger.info(f"Found {len(pdf_paths)} PDFs in {BASE_DIR}")
    
    pdf_paths = [str(p) for p in pdf_paths]
    
    # Initialize streaming components
    processor = StreamingPDFProcessor()
    vector_store_wrapper = StreamingVectorStore()
    
    # Check if we need to load documents
    needs_loading = force_reload or not os.path.exists(MILVUS_URI)
    
    if needs_loading:
        logger.info("Loading documents into vector store...")
        count = vector_store_wrapper.add_documents_streaming(
            processor,
            pdf_paths,
            drop_old=True
        )
        logger.info(f"Loaded {count} documents")
    else:
        logger.info("Using existing vector store")
    
    # Return the retriever
    retriever = vector_store_wrapper.get_retriever(k=5)
    return vector_store_wrapper.vector_store, retriever


# Module-level initialization for backward compatibility
if __name__ != "__main__":
    try:
        # Try to find PDFs
        pdf_paths = list(BASE_DIR.glob("*.pdf"))
        if pdf_paths:
            logger.info(f"Initializing with {len(pdf_paths)} PDFs")
            _, retriever = initialize_vector_store(pdf_paths)
        else:
            logger.warning(f"No PDFs found in {BASE_DIR}")
            retriever = None
    except Exception as e:
        logger.error(f"Failed to initialize vector store: {e}")
        retriever = None
