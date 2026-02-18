"""
URL configuration for rag_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def root_index(_request):
    return JsonResponse(
        {
            "service": "AcademeRAG API",
            "status": "ok",
            "routes": {
                "admin": "/admin/",
                "api": "/api/",
                "health_live": "/api/health/live/",
                "health_ready": "/api/health/ready/",
            },
            "note": "Frontend dev server usually runs on http://127.0.0.1:5173/",
        }
    )

urlpatterns = [
    path("", root_index, name="root_index"),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),  # Routes /api/ requests to your api app
]
