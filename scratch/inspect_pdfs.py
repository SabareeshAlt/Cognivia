import os
from pypdf import PdfReader

docs_dir = r"c:\Sabareesh\Visual Studio Code\AcademeRAG\AcademeRAG-Final\documents"
for f in os.listdir(docs_dir):
    if f.endswith('.pdf'):
        path = os.path.join(docs_dir, f)
        try:
            reader = PdfReader(path)
            print(f"File: {f}, Pages: {len(reader.pages)}")
            first_page = reader.pages[0].extract_text()
            print("--- First 300 chars ---")
            print(first_page[:300])
            print("-----------------------\n")
        except Exception as e:
            print(f"Error reading {f}: {e}")
