from django.urls import path
from . import views
from . import auth_views

urlpatterns = [
    # Auth endpoints
    path("auth/register/", auth_views.register, name="auth_register"),
    path("auth/login/", auth_views.login, name="auth_login"),
    path("auth/refresh/", auth_views.refresh, name="auth_refresh"),
    path("auth/me/", auth_views.me, name="auth_me"),

    # Standard endpoint (non-streaming)
    path('ask/', views.ask_question, name='ask_question'),
    
    # Streaming endpoint
    path('ask/stream/', views.ask_question, name='ask_question_stream'),
    
    # Health check — support both URL patterns used by different frontends
    path('health/', views.health_check, name='health_check'),
    path('health_check/', views.health_check, name='health_check_alt'),
    path('health/live/', views.health_live, name='health_live'),
    path('health/ready/', views.health_ready, name='health_ready'),
    path('metrics/', views.metrics, name='metrics'),
    path('admin/retrieval/diagnostics/', views.retrieval_diagnostics, name='retrieval_diagnostics'),
]
