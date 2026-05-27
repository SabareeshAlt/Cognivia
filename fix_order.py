import re

def fix_initialization_order():
    with open("Milvus.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Remove the existing top-level call
    content = content.replace("\n_schedule_fallback_cache_refresh()\n", "\n")

    # Ensure there's a trailing newline then append the call
    content = content.strip() + "\n\n_schedule_fallback_cache_refresh()\n"

    with open("Milvus.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix_initialization_order()
    print("Initialization order fixed")
