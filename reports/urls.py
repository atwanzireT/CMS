from django.urls import path
from .views import general_reports, create_report
from .views import ReportDetailView

app_name = 'reports'

urlpatterns = [
    path("", general_reports, name="general_reports"),
    path("new/", create_report, name="report_create"),
    path("reports/<int:pk>/", ReportDetailView.as_view(), name="report_detail"),
]
