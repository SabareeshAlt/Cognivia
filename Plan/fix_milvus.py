import re

def fix_milvus():
    with open("Milvus.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Find the top-level call to _schedule_fallback_cache_refresh()
    content = content.replace("_schedule_fallback_cache_refresh()\n\ndef _milvus_endpoint_reachable", "def _milvus_endpoint_reachable")
    
    # And we'll just put it at the very bottom, after all defs
    content = content + "\n\n_schedule_fallback_cache_refresh()\n"
    
    with open("Milvus.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix_milvus()
