from django.urls import path
from .views import analysis_view

app_name = 'analysis'

urlpatterns = [
    path('', analysis_view, name='analysis_view'),
]