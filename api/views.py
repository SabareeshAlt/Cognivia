from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

# Import your RAG components
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from vector import retriever # This works because vector.py is at the project root

# --- Initialize Model and Chain ---
# This code runs once when the Django server starts
print("Loading model and creating RAG chain...")
model = OllamaLLM(model="llama2:latest")

template = """
You are an expert academic assistant. Use the following context from academic papers to answer the user's question.
If you don't know the answer from the context, just say that you don't know. Don't try to make up an answer.

Context:
{reviews}

Question:
{question}
"""
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model
print("RAG chain created successfully.")
# ------------------------------------


@csrf_exempt  # Disables CSRF protection for this API view, simplifying POST requests from JS
def ask_question(request):
    """
    Handles POST requests to the /api/ask/ endpoint.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        # Decode request body and load JSON data
        data = json.loads(request.body.decode('utf-8'))
        question = data.get('question')

        if not question:
            return JsonResponse({'error': 'The "question" field is required.'}, status=400)

        # Retrieve relevant documents from the vector store
        docs = retriever.invoke(question)
        
        # Format the context from the retrieved documents
        context = "\n\n---\n\n".join([doc.page_content for doc in docs])
        
        # Invoke the RAG chain with the context and question
        result = chain.invoke({"reviews": context, "question": question})
        
        return JsonResponse({'answer': result})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)