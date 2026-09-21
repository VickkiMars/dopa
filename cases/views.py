from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.db.models import Q

from audit.services import log_event
from audit.models import AuditAction, AuditStatus
from accounts.models import Role
from .models import Case, CaseTeam, CaseStatus, Notification
from .forms import CaseCreateForm, TeamAdmitForm
from .decorators import role_required, case_owner_required, case_access_required


class DashboardView(LoginRequiredMixin, View):
    template_name = 'cases/dashboard.html'

    def get(self, request):
        user = request.user
        status_filter = request.GET.get('status', '').strip().upper()
        search_query = request.GET.get('q', '').strip()

        # Query Scoping by Role (US-SY-02, C-15)
        if user.is_primary_physician:
            cases_qs = Case.objects.filter(owner=user).select_related('owner').prefetch_related('team_memberships__specialist')
        else:
            cases_qs = Case.objects.filter(team_memberships__specialist=user).select_related('owner').prefetch_related('team_memberships__specialist')

        # Status Filtering (GAP-07)
        if status_filter in CaseStatus.values:
            cases_qs = cases_qs.filter(status=status_filter)

        # Keyword Search (GAP-07)
        if search_query:
            cases_qs = cases_qs.filter(
                Q(title__icontains=search_query) |
                Q(clinical_summary__icontains=search_query)
            )

        # Compute Metrics
        if user.is_primary_physician:
            base_qs = Case.objects.filter(owner=user)
        else:
            base_qs = Case.objects.filter(team_memberships__specialist=user)

        metrics = {
            'total': base_qs.count(),
            'open': base_qs.filter(status=CaseStatus.OPEN).count(),
            'under_review': base_qs.filter(status=CaseStatus.UNDER_REVIEW).count(),
            'decided_or_closed': base_qs.filter(status__in=[CaseStatus.DECIDED, CaseStatus.CLOSED]).count(),
        }

        # Notifications (GAP-05)
        notifications = Notification.objects.filter(recipient=user, is_read=False)[:5]

        context = {
            'user': user,
            'role_display': user.get_role_display(),
            'is_primary_physician': user.is_primary_physician,
            'is_specialist': user.is_specialist,
            'cases': cases_qs,
            'status_filter': status_filter,
            'search_query': search_query,
            'metrics': metrics,
            'notifications': notifications,
            'status_choices': CaseStatus.choices,
        }
        return render(request, self.template_name, context)


@method_decorator(role_required(Role.PRIMARY_PHYSICIAN), name='dispatch')
class CaseCreateView(LoginRequiredMixin, View):
    """
    Case creation module restricted strictly to Primary Physicians (FR2, C-07, C-13, FT04, FT05).
    """
    template_name = 'cases/case_create.html'

    def get(self, request):
        form = CaseCreateForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = CaseCreateForm(request.POST)
        if form.is_valid():
            case = form.save(commit=False)
            case.owner = request.user
            case.status = CaseStatus.OPEN
            case.save()

            # Record CASE_CREATED in append-only audit trail
            log_event(
                action=AuditAction.CASE_CREATED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_case',
                entity_id=str(case.id),
                request=request,
                status=AuditStatus.ALLOWED,
                details={'title': case.title}
            )

            messages.success(request, f"Clinical case '{case.title}' created. You may now admit advisory specialists to your team.")
            return redirect('cases:team_admit', case_id=case.id)

        return render(request, self.template_name, {'form': form})


@method_decorator(case_owner_required, name='dispatch')
class TeamAdmitView(LoginRequiredMixin, View):
    """
    Team admission module allowing Primary Physicians to admit Specialists by email (FR2, C-14, FAULT-02, FAULT-07).
    """
    template_name = 'cases/team_admit.html'

    def get(self, request, case_id):
        case = request.case
        form = TeamAdmitForm(case=case)
        team_members = case.team_memberships.select_related('specialist').all()
        return render(request, self.template_name, {
            'case': case,
            'form': form,
            'team_members': team_members
        })

    def post(self, request, case_id):
        case = request.case
        form = TeamAdmitForm(request.POST, case=case)
        if form.is_valid():
            specialist = form.target_specialist

            # Create CaseTeam record
            CaseTeam.objects.create(
                case=case,
                specialist=specialist,
                admitted_by=request.user
            )

            # Dispatch In-App Notification (GAP-05, FAULT-07)
            Notification.objects.create(
                recipient=specialist,
                case=case,
                verb='TEAM_ADMISSION',
                message=f"Dr. {request.user.full_name} has admitted you to collaborate on case '{case.title}'."
            )

            # Record SPECIALIST_ADMITTED in audit trail
            log_event(
                action=AuditAction.SPECIALIST_ADMITTED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_caseteam',
                entity_id=str(specialist.id),
                request=request,
                status=AuditStatus.ALLOWED,
                details={
                    'specialist_email': specialist.email,
                    'specialist_name': specialist.full_name
                }
            )

            messages.success(request, f"Dr. {specialist.full_name} ({specialist.email}) successfully admitted to the case team.")
            return redirect('cases:team_admit', case_id=case.id)

        team_members = case.team_memberships.select_related('specialist').all()
        return render(request, self.template_name, {
            'case': case,
            'form': form,
            'team_members': team_members
        })


@method_decorator(case_access_required, name='dispatch')
class CaseDetailView(LoginRequiredMixin, View):
    """
    Read-only presentation of case data and admitted team for authorized members.
    """
    template_name = 'cases/case_detail.html'

    def get(self, request, case_id):
        case = request.case
        team_members = case.team_memberships.select_related('specialist').all()
        return render(request, self.template_name, {
            'case': case,
            'is_case_owner': request.is_case_owner,
            'is_team_member': request.is_team_member,
            'team_members': team_members
        })
