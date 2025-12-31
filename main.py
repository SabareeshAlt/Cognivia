import json
import os
import sys
import warnings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Suppress Milvus async warnings
warnings.filterwarnings("ignore", message=".*AsyncMilvusClient.*")
warnings.filterwarnings("ignore", message=".*no running event loop.*")

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def get_llm_response(question):
    """Get response from LLM with or without RAG"""
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    
    # Initialize the LLM
    llm = ChatOllama(model="llama3.2", temperature=0.7)
    
    # Try to use RAG if vector store exists
    try:
        from langchain_ollama import OllamaEmbeddings
        from langchain_milvus import Milvus
        
        milvus_uri = os.path.join(project_root, "milvus_local.db")
        
        if os.path.exists(milvus_uri):
            embeddings = OllamaEmbeddings(model="mxbai-embed-large")
            
            # Suppress async warnings during Milvus initialization
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                vector_store = Milvus(
                    collection_name="AcademeRAG",
                    embedding_function=embeddings,
                    connection_args={"uri": milvus_uri},
                )
            
            # Retrieve relevant documents
            retriever = vector_store.as_retriever(search_kwargs={"k": 3})
            docs = retriever.invoke(question)
            
            if docs:
                context = "\n\n".join([doc.page_content for doc in docs])
                
                rag_prompt = ChatPromptTemplate.from_template("""
                You are a helpful AI assistant. Answer the question based on the provided context.
                If the context doesn't contain relevant information, say so and provide a general answer.
                
                Context:
                {context}
                
                Question: {question}
                
                Answer:
                """)
                
                chain = rag_prompt | llm
                response = chain.invoke({"context": context, "question": question})
                return response.content
    except Exception as e:
        print(f"RAG error (falling back to direct LLM): {e}")
    
    # Fallback: Direct LLM response without RAG
    simple_prompt = ChatPromptTemplate.from_template("""
    You are a helpful AI assistant. Please answer the following question:
    
    Question: {question}
    
    Answer:
    """)
    
    chain = simple_prompt | llm
    response = chain.invoke({"question": question})
    return response.content


@csrf_exempt
@require_http_methods(["POST"])
def ask_question(request):
    """Handle questions from the frontend"""
    try:
        data = json.loads(request.body)
        question = data.get('question', '')
        
        if not question:
            return JsonResponse({
                'error': 'No question provided'
            }, status=400)
        
        # Get response from LLM
        try:
            answer = get_llm_response(question)
            return JsonResponse({
                'answer': answer,
                'status': 'success'
            })
        except Exception as e:
            error_msg = str(e)
            
            # Check if it's an Ollama connection error
            if "connection" in error_msg.lower() or "refused" in error_msg.lower() or "connect" in error_msg.lower():
                return JsonResponse({
                    'answer': '⚠️ **Ollama is not running.**\n\nPlease start Ollama first:\n```bash\nollama serve\n```\n\nThen ensure models are available:\n```bash\nollama pull llama3.2\nollama pull mxbai-embed-large\n```',
                    'status': 'error',
                    'error_type': 'ollama_not_running'
                })
            else:
                return JsonResponse({
                    'answer': f'⚠️ **Error:** {error_msg}',
                    'status': 'error',
                    'error_type': 'processing_error'
                })
                
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    """Health check endpoint"""
    health_status = {
        'django': True,
        'ollama': False,
        'vector_store': False
    }
    
    # Check Ollama
    try:
        import requests
        response = requests.get('http://localhost:11434/api/tags', timeout=2)
        if response.status_code == 200:
            health_status['ollama'] = True
    except:
        pass
    
    # Check Vector Store
    try:
        milvus_uri = os.path.join(project_root, "milvus_local.db")
        if os.path.exists(milvus_uri):
            health_status['vector_store'] = True
    except:
        pass
    
    return JsonResponse({
        'status': 'healthy' if all(health_status.values()) else 'degraded',
        'services': health_status
    })