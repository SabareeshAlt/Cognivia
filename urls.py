from django.urls import path
from django.http import HttpResponse
from api.views import ask_question, health_check

def serve_final_html(request):
    with open("Final.html", "r") as f:
        return HttpResponse(f.read())

urlpatterns = [
    path('', serve_final_html),
    path('api/ask/', ask_question),
    path('api/health/', health_check),
]