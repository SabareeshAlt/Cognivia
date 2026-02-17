from django.urls import path
from . import views

urlpatterns = [
    # Standard endpoint
    path('ask/', views.ask_question, name='ask_question'),
    
    # --- FIXED: Added the missing stream endpoint ---
    path('ask/stream/', views.ask_question, name='ask_question_stream'),
    
    path('health_check/', views.health_check, name='health_check'),
]