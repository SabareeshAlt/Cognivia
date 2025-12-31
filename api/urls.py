from django.urls import path
from . import views

urlpatterns = [
    # Ask question endpoint (non-streaming)
    path('ask/', views.ask_question, name='ask_question'),
    
    # Health check
    path('health/', views.health_check, name='health_check'),
]