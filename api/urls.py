from django.urls import path
from . import views

urlpatterns = [
    # Standard endpoint (non-streaming)
    path('ask/', views.ask_question, name='ask_question'),
    
    # Streaming endpoint
    path('ask/stream/', views.ask_question, name='ask_question_stream'),
    
    # Health check — support both URL patterns used by different frontends
    path('health/', views.health_check, name='health_check'),
    path('health_check/', views.health_check, name='health_check_alt'),
]