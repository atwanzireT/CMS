from django.urls import path
from .views import general_reports, create_report

urlpatterns = [
    path("", general_reports, name="general_reports"),
    path("new/", create_report, name="report_create"),
]
