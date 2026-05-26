import re
import os

def apply_phase6_patch():
    # 1. Dependency Pinning
    with open("requirements_django.txt", "r", encoding="utf-8") as f:
        reqs = f.read()
    reqs = reqs.replace(">=", "==").replace("<=", "==")
    with open("requirements_django.txt", "w", encoding="utf-8") as f:
        f.write(reqs)

    # 2. .env protection & remove tracked DB files from git
    with open(".gitignore", "r", encoding="utf-8") as f:
        gitignore = f.read()
    
    if "milvus_local.db" not in gitignore:
        gitignore += "\nmilvus_local.db\n*.sqlite3\n"
        with open(".gitignore", "w", encoding="utf-8") as f:
            f.write(gitignore)

    # 3. Password Validation in auth_views.py
    with open("api/auth_views.py", "r", encoding="utf-8") as f:
        auth_views = f.read()
    
    strong_pwd_check = r"""    if len(password) < 8:
        return json_error(request, "Password must be at least 8 characters", 400)
    if not any(char.isdigit() for char in password):
        return json_error(request, "Password must contain at least one number", 400)
    if not any(char.isupper() for char in password):
        return json_error(request, "Password must contain at least one uppercase letter", 400)"""
    auth_views = re.sub(r'    if len\(password\) < 8:\n        return json_error\(request, "Password must be at least 8 characters", 400\)', strong_pwd_check, auth_views)
    
    with open("api/auth_views.py", "w", encoding="utf-8") as f:
        f.write(auth_views)

    # 4. Health & Metrics Endpoint Protection & Error Leakage Removal in views.py
    with open("api/views.py", "r", encoding="utf-8") as f:
        views = f.read()

    # Add @jwt_required to metrics and health endpoints (except live)
    views = views.replace("def metrics(request):", "@jwt_required\ndef metrics(request):")
    views = views.replace("def health_ready(request):", "@jwt_required\ndef health_ready(request):")
    views = views.replace("def health_check(request):", "@jwt_required\ndef health_check(request):")

    # Remove internal error leakage
    views = views.replace('"details": str(exc),', '"details": "Internal server configuration error",')

    with open("api/views.py", "w", encoding="utf-8") as f:
        f.write(views)

if __name__ == "__main__":
    apply_phase6_patch()
    os.system("git rm --cached db.sqlite3 2>nul")
    os.system("git rm --cached milvus_local.db 2>nul")
    print("Phase 6 patch applied successfully.")
