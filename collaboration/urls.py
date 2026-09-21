from django.urls import path
from . import views

app_name = 'collaboration'

urlpatterns = [
    path('cases/<uuid:case_id>/hypotheses/create/', views.HypothesisCreateView.as_view(), name='hypothesis_create'),
    path('cases/<uuid:case_id>/hypotheses/<uuid:hypo_id>/withdraw/', views.HypothesisWithdrawView.as_view(), name='hypothesis_withdraw'),
    path('cases/<uuid:case_id>/notes/create/', views.DiscussionNoteCreateView.as_view(), name='note_create'),
]
