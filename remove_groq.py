import re

def remove_groq_function():
    with open("Milvus.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Find the function and remove it using regex
    pattern = r"def _groq_endpoint_reachable[\s\S]*?(?=\ndef |\Z)"
    content = re.sub(pattern, "", content)

    with open("Milvus.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    remove_groq_function()
    print("Removed _groq_endpoint_reachable")
