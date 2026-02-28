"""
Centralized RAG Service Module
Consolidates all RAG logic in a single reusable service
Prevents code duplication across main.py, Gradio.py, and api/views.py
"""

from typing import Optional, List, Dict, Any, AsyncGenerator
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
import logging

logger = logging.getLogger(__name__)


class RAGService:
    """
    Centralized service for RAG operations.
    Handles model initialization, prompt management, and response generation.
    """
    
    def __init__(self, model_name: str = "llama3.2", temperature: float = 0.7):
        """
        Initialize RAG service.
        
        Args:
            model_name: Name of the Ollama model to use
            temperature: Temperature for model generation (0-1)
        """
        logger.info(f"Initializing RAG service with model: {model_name}")
        
        self.model_name = model_name
        self.temperature = temperature
        
        # Initialize the model
        try:
            self.model = OllamaLLM(
                model=model_name,
                temperature=temperature
            )
            logger.info(f"Model '{model_name}' initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize model '{model_name}': {e}")
            raise
        
        # Define system prompt
        self.system_prompt = """
You are an expert academic assistant. Use the following context from academic papers and documents to answer the user's question.

Guidelines:
1. Provide accurate, well-structured answers based on the provided context
2. If the context doesn't contain relevant information, clearly state: "I don't have sufficient information in the provided documents to answer this question."
3. Always cite which document(s) your answer comes from using the [source] notation
4. Be concise but thorough
5. If the question is ambiguous, ask for clarification rather than guessing

Context Documents:
{reviews}

Question:
{question}
"""
        
        # Create prompt template
        self.prompt_template = ChatPromptTemplate.from_template(self.system_prompt)
        
        # Create chain
        self.chain = self.prompt_template | self.model
        
        logger.info("RAG service initialization complete")
    
    def validate_input(self, question: str) -> tuple[bool, Optional[str]]:
        """
        Validate user input.
        
        Args:
            question: User's question
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not question:
            return False, "Question cannot be empty"
        
        if len(question.strip()) < 3:
            return False, "Question must be at least 3 characters long"
        
        if len(question) > 5000:
            return False, "Question is too long (max 5000 characters)"
        
        return True, None
    
    def format_documents(self, docs: List[Document]) -> str:
        """
        Format retrieved documents for the prompt.
        
        Args:
            docs: List of retrieved documents
            
        Returns:
            Formatted string for the prompt
        """
        if not docs:
            return "No relevant documents found in the knowledge base."
        
        formatted = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "Unknown source") if doc.metadata else "Unknown source"
            content = doc.page_content.strip()
            formatted.append(f"[Document {i} - {source}]\n{content}")
        
        return "\n\n---\n\n".join(formatted)
    
    def answer_question(
        self,
        question: str,
        docs: List[Document],
        stream: bool = False
    ) -> str:
        """
        Generate an answer to the question using retrieved documents.
        
        Args:
            question: User's question
            docs: Retrieved documents from vector store
            stream: Whether to stream the response (not implemented here, see stream_answer)
            
        Returns:
            Generated answer
            
        Raises:
            ValueError: If validation fails
            Exception: If model generation fails
        """
        # Validate input
        is_valid, error = self.validate_input(question)
        if not is_valid:
            raise ValueError(error)
        
        # Format documents
        formatted_docs = self.format_documents(docs)
        
        logger.info(f"Generating answer for question: {question[:50]}...")
        
        try:
            # Generate answer
            result = self.chain.invoke({
                "reviews": formatted_docs,
                "question": question
            })
            
            logger.info("Answer generated successfully")
            return result
            
        except TimeoutError:
            logger.error("Model response timeout")
            raise TimeoutError("Model took too long to respond. Please try again.")
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            raise
    
    async def stream_answer(
        self,
        question: str,
        docs: List[Document]
    ) -> AsyncGenerator[str, None]:
        """
        Stream the answer as tokens are generated from the model.
        Provides real-time response feedback to the user.
        
        Args:
            question: User's question
            docs: Retrieved documents from vector store
            
        Yields:
            Answer tokens as they are generated
            
        Raises:
            ValueError: If validation fails
        """
        # Validate input
        is_valid, error = self.validate_input(question)
        if not is_valid:
            raise ValueError(error)
        
        # Format documents
        formatted_docs = self.format_documents(docs)
        
        logger.info(f"Streaming answer for question: {question[:50]}...")
        
        try:
            # Stream answer tokens
            for chunk in self.chain.stream({
                "reviews": formatted_docs,
                "question": question
            }):
                yield chunk
            
            logger.info("Stream completed successfully")
            
        except TimeoutError:
            logger.error("Model response timeout during streaming")
            yield "\n[ERROR] Model response timeout. Please try again."
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
            yield f"\n[ERROR] An error occurred: {str(e)}"
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model configuration."""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "status": "ready"
        }


class RAGChainBuilder:
    """
    Builder for constructing custom RAG chains with different configurations.
    Allows flexibility for different use cases (academic, restaurant reviews, etc.)
    """
    
    def __init__(self):
        self.model_name = "llama3.2"
        self.temperature = 0.7
        self.system_prompt = None
        self.model = None
    
    def with_model(self, model_name: str) -> "RAGChainBuilder":
        """Set the model to use."""
        self.model_name = model_name
        return self
    
    def with_temperature(self, temperature: float) -> "RAGChainBuilder":
        """Set the temperature for generation."""
        if not 0 <= temperature <= 1:
            raise ValueError("Temperature must be between 0 and 1")
        self.temperature = temperature
        return self
    
    def with_system_prompt(self, prompt: str) -> "RAGChainBuilder":
        """Set a custom system prompt."""
        self.system_prompt = prompt
        return self
    
    def build(self) -> RAGService:
        """Build and return the RAGService instance."""
        service = RAGService(
            model_name=self.model_name,
            temperature=self.temperature
        )
        if self.system_prompt:
            service.system_prompt = self.system_prompt
            service.prompt_template = ChatPromptTemplate.from_template(self.system_prompt)
            service.chain = service.prompt_template | service.model
        return service


# Preset configurations for different use cases
def create_academic_rag_service() -> RAGService:
    """Create a RAG service configured for academic/educational content."""
    return RAGService(model_name="llama3.2", temperature=0.3)


def create_conversational_rag_service() -> RAGService:
    """Create a RAG service configured for conversational responses."""
    return RAGService(model_name="llama3.2", temperature=0.7)


def create_detailed_rag_service() -> RAGService:
    """Create a RAG service configured for detailed, comprehensive answers."""
    return RAGService(model_name="llama3.2", temperature=0.5)
