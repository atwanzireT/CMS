from django.urls import path
from .views import *

app_name = 'assessment'

urlpatterns = [
    # Quality Assessment URLs
    path('assessments/', assessment_list, name='assessment_list'),
    path('assessments/<int:pk>/create/', assessment_create, name='assessment_create'),
    path('assessments/<int:pk>/', assessment_detail, name='assessment_detail'),
    path('assessments/<int:pk>/pdf/', assessment_pdf, name='assessment_pdf'),
]