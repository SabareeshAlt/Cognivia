from django.urls import path
from . import views

urlpatterns = [
    # Ask question endpoint (supports both streaming and non-streaming)
    path('ask/', views.ask_question, name='ask_question'),
    
    # Dedicated streaming endpoint
    path('ask/stream/', views.ask_question_stream, name='ask_question_stream'),
    
    # Health check
    path('health/', views.health_check, name='health_check'),
    
    # Cache management (new)
    path('cache/info/', views.cache_info, name='cache_info'),
    path('cache/clear/', views.clear_cache, name='clear_cache'),
]