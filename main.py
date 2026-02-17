import json
import os
import sys
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the robust retriever from our vector module
# This handles the Local vs Cloud logic automatically
from .vector import get_retriever

def get_llm_response(question):
    """Get response from LLM with or without RAG"""
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    
    # Initialize the LLM
    llm = ChatOllama(model="llama3.2", temperature=0.7)
    
    # Try to use RAG
    try:
        # Get the retriever from vector.py
        retriever = get_retriever(k=3)
        
        # Retrieve docs
        docs = retriever.invoke(question)
        
        if docs:
            context = "\n\n".join([doc.page_content for doc in docs])
            
            rag_prompt = ChatPromptTemplate.from_template("""
            You are an academic AI assistant.
            Answer strictily based on the Context below.
            
            Context:
            {context}

            User Question:
            {question}
            """)
            
            chain = rag_prompt | llm | StrOutputParser()
            response = chain.invoke({"context": context, "question": question})
            return response
            
    except Exception as e:
        print(f"RAG error (falling back to direct LLM): {e}")
    
    # Fallback: Direct LLM response
    simple_prompt = ChatPromptTemplate.from_template("Answer this question: {question}")
    chain = simple_prompt | llm | StrOutputParser()
    response = chain.invoke({"question": question})
    return response

@csrf_exempt
@require_http_methods(["POST"])
def ask_question(request):
    """Handle questions from the frontend"""
    try:
        data = json.loads(request.body)
        question = data.get('question', '')
        
        if not question:
            return JsonResponse({'error': 'No question provided'}, status=400)
        
        answer = get_llm_response(question)
        return JsonResponse({'answer': answer, 'status': 'success'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    """Health check endpoint"""
    health_status = {'django': True, 'ollama': False, 'vector_store': False}
    
    # Check Ollama
    try:
        import requests
        if requests.get('http://localhost:11434/', timeout=1).status_code == 200:
            health_status['ollama'] = True
    except: pass
    
    # Check Vector Store (using the vector module)
    try:
        get_retriever()
        health_status['vector_store'] = True
    except: pass
    
    return JsonResponse({'status': 'healthy', 'services': health_status})