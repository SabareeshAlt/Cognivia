import re

with open("Milvus_head.py", "r", encoding="utf-16") as f:
    content = f.read()

funcs = ['_create_llm_client', '_preferred_llm_providers', '_validate_groq_base_url', '_groq_endpoint_reachable']
for fn in funcs:
    match = re.search(rf'(def {fn}\b.*?)(?=\ndef [a-zA-Z_])', content, re.DOTALL)
    if match:
        print('='*60)
        print(match.group(1).strip())
        print()

# Also get Groq constants
groq_consts = re.findall(r'^(GROQ_\w+\s*=\s*.+)$', content, re.MULTILINE)
print('='*60)
print("GROQ CONSTANTS:")
for c in groq_consts:
    print(c)

# Also get _groq_health
match = re.search(r'^(_groq_health\s*=\s*\{.*?\})', content, re.MULTILINE | re.DOTALL)
if match:
    print(match.group(1))
