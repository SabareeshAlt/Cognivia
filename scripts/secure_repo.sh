#!/bin/bash
echo "Removing sensitive files from git tracking..."
git rm --cached .env db.sqlite3 milvus_local.db bm25_index.pkl 2>/dev/null || true
echo "Done."
