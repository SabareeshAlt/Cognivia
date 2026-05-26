import re
import sys

def refactor_milvus():
    with open("Milvus.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Remove ChatOpenAI import
    content = re.sub(r'try:\s*from langchain_openai import ChatOpenAI\s*except Exception:.*?ChatOpenAI = None\n', '', content, flags=re.DOTALL)

    # 2. Remove GROQ config vars
    content = re.sub(r'GROQ_[A-Z_]+\s*=\s*_env_[a-z]+\([^)]+\)\n', '', content)

    # 3. Remove _groq_health dict
    content = re.sub(r'_groq_health\s*=\s*\{[^}]+\}\n', '', content)

    # 4. Simplify _get_milvus_config to hardcode local db
    old_config = r'def _get_milvus_config\(\):.*?return \{\s*"uri": milvus_uri,\s*"token": milvus_token,\s*"collection": COLLECTION_NAME,\s*"model": EMBEDDING_MODEL,\s*\}'
    new_config = '''def _get_milvus_config():
    return {
        "uri": "./milvus_local.db",
        "token": "",
        "collection": COLLECTION_NAME,
        "model": EMBEDDING_MODEL,
    }'''
    content = re.sub(old_config, new_config, content, flags=re.DOTALL)

    # 5. Simplify _milvus_endpoint_reachable
    old_reachable = r'def _milvus_endpoint_reachable\(cfg: dict\) -> bool:.*?return False'
    new_reachable = '''def _milvus_endpoint_reachable(cfg: dict) -> bool:
    return True'''
    content = re.sub(old_reachable, new_reachable, content, flags=re.DOTALL)

    # 6. Remove _generic_retrieval_boost function
    content = re.sub(r'def _generic_retrieval_boost\(question: str, doc: Document\) -> float:.*?(?=\n\n\ndef |\Z)', '', content, flags=re.DOTALL)

    # 7. Remove boost call in get_retriever or similarity_search
    content = re.sub(r'score = lexical_score \+ _generic_retrieval_boost\(question, doc\)', 'score = lexical_score', content)

    # 8. Remove is_general_curriculum hack in get_retriever
    hack_pattern = r'\s*# General department curriculum check.*?logger\.warning\("Failed to inject curriculum pages: %s", cur_exc\)'
    content = re.sub(hack_pattern, '', content, flags=re.DOTALL)

    # 9. Remove Groq selection logic
    groq_llm_pattern = r'def _get_llm\(\).*?def '
    
    # We will just rewrite _get_llm
    new_get_llm = '''def _get_llm():
    return ChatOllama(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=LLM_TEMPERATURE,
    )

def '''
    content = re.sub(groq_llm_pattern, new_get_llm, content, flags=re.DOTALL)

    # 10. Streaming LLM Groq selection logic
    groq_stream_pattern = r'def _get_streaming_llm\(\).*?def '
    new_get_streaming_llm = '''def _get_streaming_llm():
    return ChatOllama(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=LLM_TEMPERATURE,
    )

def '''
    content = re.sub(groq_stream_pattern, new_get_streaming_llm, content, flags=re.DOTALL)
    
    with open("Milvus.py", "w", encoding="utf-8") as f:
        f.write(content)


def refactor_views():
    with open("api/views.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    content = re.sub(r'\s*"milvus_cloud": False,', '', content)
    content = re.sub(r'\s*health_status\["milvus_cloud"\] = True', '', content)
    
    with open("api/views.py", "w", encoding="utf-8") as f:
        f.write(content)

def refactor_tests():
    with open("api/tests.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Remove milvus_cloud check
    content = re.sub(r'\s*self\.assertTrue\(payload\["services"\]\["milvus_cloud"\]\)', '', content)

    # Remove groq fallback test entirely
    test_pattern = r'\s*@patch\("api\.views\._load_rag_modules"\)\s*@patch\("api\.views\._vector_store_fn", autospec=False\)\s*@patch\("requests\.get"\)\s*def test_health_ready_groq_falls_back_to_ollama.*?finally:\n.*?os\.environ\["GROQ_API_KEY"\] = old_groq_key'
    content = re.sub(test_pattern, '', content, flags=re.DOTALL)
    
    with open("api/tests.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    refactor_milvus()
    refactor_views()
    refactor_tests()
    import os
    if os.path.exists("Milvus_backup.py"):
        os.remove("Milvus_backup.py")
    print("Done")
