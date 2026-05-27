import ast
import os
import re

def get_function_source(filepath, func_names):
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    
    tree = ast.parse(source)
    funcs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in func_names:
            # Extract lines
            lines = source.splitlines()
            func_source = '\n'.join(lines[node.lineno - 1:node.end_lineno])
            funcs[node.name] = func_source
    return funcs

def get_all_functions(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    tree = ast.parse(source)
    funcs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs[node.name] = (node.lineno, node.end_lineno)
    return funcs

def patch_milvus():
    project_root = r"c:\Sabareesh\Visual Studio Code\AcademeRAG\AcademeRAG-Final"
    milvus_path = os.path.join(project_root, "Milvus.py")
    plan_dir = os.path.join(project_root, "Plan")
    
    # Read the original Milvus.py
    with open(milvus_path, 'r', encoding='utf-8') as f:
        milvus_source = f.read()
    milvus_lines = milvus_source.splitlines()
    
    # Extract replacement functions
    replacements = {}
    
    # From chunking.py
    replacements.update(get_function_source(os.path.join(plan_dir, 'chunking.py'), ['_load_and_chunk_files']))
    
    # From schema.py
    replacements.update(get_function_source(os.path.join(plan_dir, 'schema.py'), ['ensure_collection_schema', '_ingest_documents_with_client']))
    
    # From bm25.py
    replacements.update(get_function_source(os.path.join(plan_dir, 'bm25.py'), ['_build_fallback_stats_from_docs', '_fallback_retrieve_docs', '_search_bm25_fallback', '_bm25_score']))
    
    # From fallback.py
    replacements.update(get_function_source(os.path.join(plan_dir, 'fallback.py'), ['_search_cloud_milvus', '_search_local_milvus']))
    
    # From hybrid_search.py
    replacements.update(get_function_source(os.path.join(plan_dir, 'hybrid_search.py'), ['_rrf_fuse', '_get_cross_encoder', '_cross_encoder_rerank', '_expand_neighbor_chunks']))
    
    # From retrieval_architecture.py
    # NOTE: Do NOT take _rrf_fuse from retrieval_architecture.py if hybrid_search.py provides a better one
    replacements.update(get_function_source(os.path.join(plan_dir, 'retrieval_architecture.py'), ['_dense_search_pipeline', '_retrieve_docs']))
    
    # Get current functions in Milvus.py
    milvus_funcs = get_all_functions(milvus_path)
    
    # We will replace backwards to not mess up line numbers
    sorted_funcs = sorted(milvus_funcs.items(), key=lambda x: x[1][0], reverse=True)
    
    for name, (start, end) in sorted_funcs:
        if name in replacements:
            print(f"Replacing {name}...")
            # Replacements
            milvus_lines[start - 1:end] = [replacements[name]]
            del replacements[name]
    
    # If there are remaining functions that weren't in Milvus.py originally (e.g. new helper functions)
    # append them to the end of the file.
    if replacements:
        print(f"Appending new functions: {list(replacements.keys())}")
        milvus_lines.append("")
        for name, source in replacements.items():
            milvus_lines.append(source)
            milvus_lines.append("")
    
    # Find the global state for lazy-loaded CrossEncoder and add it
    cross_encoder_global = """
# Global state for lazy-loaded CrossEncoder
_cross_encoder_model = None
_cross_encoder_lock = threading.Lock()
"""
    if "_cross_encoder_model = None" not in '\n'.join(milvus_lines):
        # insert after imports
        for i, line in enumerate(milvus_lines):
            if line.startswith("logger = logging.getLogger(__name__)"):
                milvus_lines.insert(i + 1, cross_encoder_global)
                break
                
    with open(milvus_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(milvus_lines))

if __name__ == '__main__':
    patch_milvus()
