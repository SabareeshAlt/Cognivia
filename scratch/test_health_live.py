import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")
import django
django.setup()

try:
    from Milvus import _get_milvus_config
    cfg = _get_milvus_config()
    print("cfg loaded:", cfg)
except Exception as e:
    import traceback
    traceback.print_exc()
