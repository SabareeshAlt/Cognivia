import re
import sys

def remove_function(content, func_name):
    # Match def func_name(...): ... up to the next def or end of file
    pattern = rf'def {func_name}\(.*?\):.*?(?=\n\s*def |\Z)'
    return re.sub(pattern, '', content, flags=re.DOTALL)

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
    content = remove_function(content, "_milvus_endpoint_reachable")
    content += "\ndef _milvus_endpoint_reachable(cfg: dict) -> bool:\n    return True\n"

    # 6. Remove groq and boost functions
    content = remove_function(content, "_generic_retrieval_boost")
    content = remove_function(content, "_groq_endpoint_reachable")
    content = remove_function(content, "_verify_groq_base_url")
    content = remove_function(content, "_get_llm")
    content = remove_function(content, "_get_streaming_llm")

    # Add back the correct ollama-only functions
    content += '''
def _get_llm():
    return ChatOllama(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=LLM_TEMPERATURE,
    )

def _get_streaming_llm():
    return ChatOllama(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=LLM_TEMPERATURE,
    )
'''

    # 7. Remove boost call in get_retriever or similarity_search
    content = re.sub(r'score = lexical_score \+ _generic_retrieval_boost\(question, doc\)', 'score = lexical_score', content)

    # 8. Remove is_general_curriculum hack in get_retriever
    hack_pattern = r'\s*# General department curriculum check.*?logger\.warning\("Failed to inject curriculum pages: %s", cur_exc\)'
    content = re.sub(hack_pattern, '', content, flags=re.DOTALL)
    
    with open("Milvus.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    refactor_milvus()
