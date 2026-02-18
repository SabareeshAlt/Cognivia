"""
Django REST API for RAG System
Complete implementation with streaming and proper error handling
"""

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.decorators.http import condition
import json
import logging
import os

logger = logging.getLogger(__name__)

def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Environment variable '{name}' is required")
    return value.strip()


def _build_rag_answer(question: str, docs) -> str:
    """Build an answer using Ollama, grounded by retrieved docs."""
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate

    context = "\n\n".join([d.page_content for d in docs])

    prompt = ChatPromptTemplate.from_template(
        """
You are an academic AI assistant for a college knowledge system.

You must answer the user's question strictly using ONLY the information provided in the context below.

Rules you must follow:
- If the answer is clearly found in the context, provide a concise, accurate response.
- If the context does NOT contain enough information to answer correctly, respond with:
  "I am not trained on this data source or the uploaded documents do not contain this information."
- Do NOT use outside knowledge.
- Do NOT guess.
- Do NOT hallucinate.
- If partial information is present, say what is known and clearly mention what is missing.

Context:
{context}

User Question:
{question}

Final Answer:
"""
    )

    llm = ChatOllama(
        model=_required_env("ACADEMERAG_LLM_MODEL"),
        temperature=float(_required_env("ACADEMERAG_LLM_TEMPERATURE")),
    )

    chain = prompt | llm
    resp = chain.invoke({"context": context, "question": question})
    return resp.content


@require_http_methods(["POST"])
@csrf_exempt
def ask_question(request):
    """Handle POST requests to /api/ask/"""

    try:
        data = json.loads(request.body.decode("utf-8"))
        question = data.get("question", "").strip()

        if not question:
            logger.warning("Empty question received")
            return JsonResponse(
                {"error": 'The "question" field is required', "success": False},
                status=400,
            )

        # Lazy import so Django startup/reloader doesn't initialize Milvus/Ollama.
        from vector import get_retriever

        try:
            retriever = get_retriever(k=int(_required_env("ACADEMERAG_TOP_K")))
            docs = retriever.invoke(question)
        except Exception as e:
            logger.error(f"Vector retrieval failed: {e}")
            return JsonResponse(
                {
                    "error": "Vector store retrieval failed",
                    "details": str(e),
                    "success": False,
                },
                status=500,
            )

        if not docs:
            return JsonResponse(
                {
                    "answer": "I could not find any relevant information in the knowledge base to answer your question.",
                    "sources": [],
                    "success": True,
                }
            )

        try:
            answer = _build_rag_answer(question, docs)
            sources = sorted(
                {
                    (d.metadata or {}).get("source", "Unknown")
                    for d in docs
                }
            )
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return JsonResponse(
                {"error": "Failed to generate answer", "details": str(e), "success": False},
                status=500,
            )

        return JsonResponse({"answer": answer, "sources": sources, "success": True})

    except json.JSONDecodeError:
        logger.error("Invalid JSON received")
        return JsonResponse(
            {"error": "Invalid JSON in request body", "success": False}, status=400
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return JsonResponse(
            {"error": f"Server error: {str(e)}", "success": False}, status=500
        )


@require_http_methods(["POST"])
@csrf_exempt
def stream_answer(request):
    """Streaming endpoint for real-time responses (Server-Sent Events)."""

    try:
        data = json.loads(request.body.decode("utf-8"))
        question = data.get("question", "").strip()

        if not question:
            return JsonResponse(
                {"error": 'The "question" field is required', "success": False},
                status=400,
            )

        def event_stream():
            try:
                yield f"data: {json.dumps({'status': 'processing', 'message': 'Retrieving context...'})}\n\n"

                from vector import get_retriever

                retriever = get_retriever(k=int(_required_env("ACADEMERAG_TOP_K")))
                docs = retriever.invoke(question)

                yield f"data: {json.dumps({'status': 'retrieved', 'count': len(docs)})}\n\n"

                if not docs:
                    yield f"data: {json.dumps({'status': 'complete', 'answer': 'I could not find any relevant information in the knowledge base to answer your question.', 'sources': []})}\n\n"
                    return

                # For now, generate the final answer in one step (still streamed as events).
                answer = _build_rag_answer(question, docs)
                sources = sorted({(d.metadata or {}).get("source", "Unknown") for d in docs})

                yield f"data: {json.dumps({'status': 'complete', 'answer': answer, 'sources': sources})}\n\n"

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"

        return StreamingHttpResponse(event_stream(), content_type="text/event-stream")

    except json.JSONDecodeError:
        logger.error("Invalid JSON in stream request")
        return JsonResponse(
            {"error": "Invalid JSON in request body", "success": False}, status=400
        )
    except Exception as e:
        logger.error(f"Unexpected error in stream: {e}")
        return JsonResponse(
            {"error": f"Server error: {str(e)}", "success": False}, status=500
        )


@require_http_methods(["GET"])
def health_check(request):
    """Health check endpoint."""
    return JsonResponse(
        {"status": "healthy", "service": "AcademeRAG API", "version": "1.0"}
    )


@require_http_methods(["GET"])
def model_info(request):
    """Get model information."""
    return JsonResponse(
        {
            "model": "AcademeRAG",
            "version": "1.0",
            "description": "Knowledge-Grounded Academic Assistant",
            "capabilities": [
                "Question Answering",
                "Document Retrieval",
                "Streaming Responses",
                "Multi-source Context",
            ],
        }
    )
