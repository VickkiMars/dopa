from django.urls import path
from . import views

app_name = 'cases'

urlpatterns = [
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('cases/create/', views.CaseCreateView.as_view(), name='case_create'),
    path('cases/<uuid:case_id>/team/admit/', views.TeamAdmitView.as_view(), name='team_admit'),
    path('cases/<uuid:case_id>/workspace/', views.WorkspaceView.as_view(), name='workspace'),
    path('cases/<uuid:case_id>/', views.CaseDetailView.as_view(), name='case_detail'),
]
