import os
from pypdf import PdfReader

docs_dir = r"c:\Sabareesh\Visual Studio Code\AcademeRAG\AcademeRAG-Final\documents"
keywords = ["late", "machine learning", "textbook", "alphago", "recurrent", "transformer", "dropout", "quicksort", "calculator"]

for f in os.listdir(docs_dir):
    if f.endswith('.pdf'):
        path = os.path.join(docs_dir, f)
        reader = PdfReader(path)
        print(f"=== File: {f} ===")
        for page_idx, page in enumerate(reader.pages):
            text = page.extract_text().lower()
            found = [kw for kw in keywords if kw in text]
            if found:
                print(f"  Page {page_idx + 1}: found {found}")
