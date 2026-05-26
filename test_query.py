import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")
django.setup()

import api.views
api.views._load_rag_modules()

try:
    for chunk in api.views._stream_fn("What is the assessment methodology?"):
        print(chunk)
except Exception as e:
    import traceback
    traceback.print_exc()
