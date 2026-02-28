import sys
import os
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# --- PATH FIX: Allow importing 'vector.py' from Root ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from vector import get_retriever

# Initialize LLM
llm = ChatOllama(model="llama3.2", temperature=0.7)

def get_rag_chain():
    """Builds the RAG chain using the vector store."""
    retriever = get_retriever()
    if not retriever:
        raise ConnectionError("Vector Database unavailable.")

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
    """Non-streaming response."""
    chain = get_rag_chain()
    return chain.invoke(question)

def stream_optimized_response(question: str):
    """Streaming response generator."""
    chain = get_rag_chain()
    for chunk in chain.stream(question):
        yield chunk

def get_cache_info():
    return get_retriever.cache_info()

def clear_cache():
    get_retriever.cache_clear()