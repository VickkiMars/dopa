from django.urls import path
from . import views

app_name = 'cases'

urlpatterns = [
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('cases/create/', views.CaseCreateView.as_view(), name='case_create'),
    path('cases/<uuid:case_id>/team/admit/', views.TeamAdmitView.as_view(), name='team_admit'),
    path('cases/<uuid:case_id>/workspace/', views.WorkspaceView.as_view(), name='workspace'),
    path('cases/<uuid:case_id>/ranking/reorder/', views.RankingReorderView.as_view(), name='ranking_reorder'),
    path('cases/<uuid:case_id>/decision/record/', views.DecisionRecordView.as_view(), name='decision_record'),
    path('cases/<uuid:case_id>/audit/', views.AuditTrailView.as_view(), name='audit_trail'),
    path('cases/<uuid:case_id>/attachments/upload/', views.CaseAttachmentUploadView.as_view(), name='attachment_upload'),
    path('cases/<uuid:case_id>/attachments/<uuid:attachment_id>/', views.CaseAttachmentDownloadView.as_view(), name='attachment_download'),
    path('cases/<uuid:case_id>/', views.CaseDetailView.as_view(), name='case_detail'),
]
