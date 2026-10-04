"""
test_generation.py
Validates the Cognivia Answer Generation pipeline using gemma4:latest.
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

try:
    from database import _retrieve_docs, _format_context
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
except ImportError as e:
    logger.error("Failed to import required modules: %s", e)
    sys.exit(1)

def run_generation_test():
    query = "What is the role of deep learning in computer vision?"
    logger.info("Testing Query: '%s'", query)
    
    # 1. Retrieve Context
    try:
        docs = _retrieve_docs(query)
        logger.info("Retrieved %d documents for context.", len(docs))
    except Exception as e:
        logger.error("Retrieval Failed: %s", e)
        return

    if not docs:
        logger.warning("No context retrieved. Cannot validate generation.")
        return

    # 2. Format Context
    context_text = _format_context(docs)
    logger.info("Formatted context length: %d chars", len(context_text))

    # 3. Setup LLM (gemma4:latest)
    llm_model = os.environ.get("COGNIVIA_LLM_MODEL", os.environ.get("ACADEMERAG_LLM_MODEL", "gemma4:latest"))
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    logger.info("Initializing LLM: %s at %s", llm_model, ollama_url)
    
    try:
        llm = ChatOllama(model=llm_model, base_url=ollama_url, temperature=0.1)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an academic assistant. Answer the user's question based strictly on the provided Context. Cite the source document and page number for every claim."),
            ("human", "Context:\n{context}\n\nQuestion: {question}")
        ])
        
        chain = prompt | llm | StrOutputParser()
        
        logger.info("--- GENERATING ANSWER ---")
        answer = chain.invoke({"context": context_text, "question": query})
        
        logger.info("=== Final Answer ===")
        print("\n" + answer + "\n")
        logger.info("====================")
        
    except Exception as e:
        logger.error("LLM Generation Failed: %s", e)

if __name__ == "__main__":
    run_generation_test()
