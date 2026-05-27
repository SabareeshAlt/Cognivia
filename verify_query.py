import os
import sys
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")

try:
    import django
    from django.apps import apps
    if not apps.ready:
        django.setup()
except Exception as e:
    print(f"Failed to setup django: {e}")
    sys.exit(1)

from Milvus import stream_optimized_response

def main():
    query = "What is the assessment methodology?"
    print(f"--- Executing Query: '{query}' ---")
    
    try:
        response_generator = stream_optimized_response(query)
        print("Streaming Response:")
        for chunk in response_generator:
            print(chunk, end="", flush=True)
        print("\n\n--- Query Completed Successfully ---")
    except Exception as e:
        print("\n\n--- Query Failed with Exception ---")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
