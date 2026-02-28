from django.urls import path
from django.http import HttpResponse
from api.views import ask_question, health_check

def serve_final_html(request):
    import os
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Final.html")
    with open(html_path, "r") as f:
        return HttpResponse(f.read(), content_type="text/html")

urlpatterns = [
    path('', serve_final_html),
    path('api/ask/', ask_question),
    path('api/ask/stream/', ask_question),
    path('api/health/', health_check),
]