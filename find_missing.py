import re

with open("Milvus_head.py", "r", encoding="utf-16") as f:
    head_content = f.read()

with open("Milvus.py", "r", encoding="utf-8") as f:
    current_content = f.read()

head_funcs = re.findall(r"^def ([a-zA-Z0-9_]+)\(", head_content, re.MULTILINE)
curr_funcs = re.findall(r"^def ([a-zA-Z0-9_]+)\(", current_content, re.MULTILINE)

missing = [f for f in head_funcs if f not in curr_funcs]
print("Missing functions:", missing)
