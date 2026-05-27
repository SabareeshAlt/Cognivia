import ast

def extract_and_append():
    with open("Milvus_head.py", "r", encoding="utf-16") as f:
        head_content = f.read()

    with open("Milvus.py", "r", encoding="utf-8") as f:
        current_content = f.read()

    head_tree = ast.parse(head_content)
    curr_tree = ast.parse(current_content)

    curr_funcs = {node.name for node in curr_tree.body if isinstance(node, ast.FunctionDef)}
    
    missing_funcs_code = []
    
    # We can't easily extract exact source code with comments using AST if we don't have ast.unparse (Python 3.9+)
    # Python 3.12 has ast.unparse
    for node in head_tree.body:
        if isinstance(node, ast.FunctionDef) and node.name not in curr_funcs:
            missing_funcs_code.append(ast.unparse(node))

    if missing_funcs_code:
        with open("Milvus.py", "a", encoding="utf-8") as f:
            f.write("\n\n" + "\n\n".join(missing_funcs_code) + "\n")
            
if __name__ == "__main__":
    extract_and_append()
    print("All missing functions appended!")
