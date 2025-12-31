"""
URL configuration for rag_project project.
"""
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static
import os

def serve_frontend(request):
    """Serve Final.html as the frontend"""
    html_path = os.path.join(settings.BASE_DIR, 'Final.html')
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return HttpResponse(f.read(), content_type='text/html')
    except FileNotFoundError:
        return HttpResponse("<h1>Frontend not found</h1><p>Final.html is missing</p>", status=404)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('', serve_frontend, name='home'),  # Serve Final.html at root
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
