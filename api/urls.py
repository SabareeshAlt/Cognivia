from django.urls import path
from . import views

urlpatterns = [
    # This maps the URL 'api/ask/' to our 'ask_question' view
    path('ask/', views.ask_question, name='ask_question'),
]