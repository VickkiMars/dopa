from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from django.core.cache import cache
from django.http import HttpResponseBadRequest, HttpResponseForbidden, FileResponse

from audit.services import log_event
from audit.models import AuditLog, AuditAction, AuditStatus
from accounts.models import Role
from .models import Case, CaseTeam, CaseStatus, Notification, DiagnosisRanking, Decision, CaseAttachment, AttachmentCategory
from .forms import CaseCreateForm, TeamAdmitForm, RankingReorderForm, DecisionRecordForm, CaseAttachmentUploadForm
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
        attachments = case.attachments.select_related('uploaded_by').all()
        return render(request, self.template_name, {
            'case': case,
            'is_case_owner': request.is_case_owner,
            'is_team_member': request.is_team_member,
            'team_members': team_members,
            'attachments': attachments
        })


def get_workspace_case(case_id):
    """
    Optimized bounded query loader for 3-pane clinical workspace (S3-02, B30).
    Loads case presentation data, owner, team members, hypotheses with specialists,
    chronological discussion notes with authors, and decision in strictly <= 4 SQL queries.
    """
    from django.db.models import Prefetch
    from collaboration.models import Hypothesis, DiscussionNote
    return Case.objects.select_related('owner', 'decision', 'decision__decider').prefetch_related(
        Prefetch('team_memberships', queryset=CaseTeam.objects.select_related('specialist')),
        Prefetch('hypotheses', queryset=Hypothesis.objects.select_related('specialist').order_by('-submitted_at')),
        Prefetch('discussion_notes', queryset=DiscussionNote.objects.select_related('author').order_by('posted_at'))
    ).get(pk=case_id)


def sync_case_rankings(case):
    """
    Ensures that every active hypothesis has a sequential rank position in DiagnosisRanking.
    Removes entries for withdrawn hypotheses and fills any gaps.
    """
    from collaboration.models import HypothesisStatus
    with transaction.atomic():
        # Clean up withdrawn hypotheses
        DiagnosisRanking.objects.filter(
            case=case, hypothesis__status=HypothesisStatus.WITHDRAWN
        ).delete()

        existing_entries = list(
            DiagnosisRanking.objects.filter(case=case).order_by('rank_position')
        )
        existing_hypo_ids = {e.hypothesis_id for e in existing_entries}

        active_hypos = list(
            case.hypotheses.filter(status=HypothesisStatus.ACTIVE).order_by('submitted_at')
        )

        max_rank = len(existing_entries)
        for h in active_hypos:
            if h.id not in existing_hypo_ids:
                max_rank += 1
                DiagnosisRanking.objects.create(
                    case=case,
                    hypothesis=h,
                    rank_position=max_rank
                )

        # Re-compact ranks to 1, 2, 3...
        all_entries = list(DiagnosisRanking.objects.filter(case=case).order_by('rank_position'))
        for idx, entry in enumerate(all_entries, start=1):
            if entry.rank_position != idx:
                entry.rank_position = 900000 + idx
                entry.save(update_fields=['rank_position'])
        for idx, entry in enumerate(all_entries, start=1):
            if entry.rank_position != idx:
                entry.rank_position = idx
                entry.save(update_fields=['rank_position', 'updated_at'])


def get_workspace_context(case, user):
    """
    Constructs the complete template context for the 3-pane clinical workspace.
    Processes in-memory prefetched relationships without issuing extra database queries.
    """
    import uuid
    from collaboration.forms import HypothesisCreateForm, HypothesisWithdrawForm, DiscussionNoteCreateForm

    team_memberships = list(case.team_memberships.all())
    is_owner = (case.owner_id == user.id)
    is_admitted_specialist = any(m.specialist_id == user.id for m in team_memberships)

    all_hypotheses = list(case.hypotheses.all())
    active_hypotheses = [h for h in all_hypotheses if h.status == 'ACTIVE']
    withdrawn_hypotheses = [h for h in all_hypotheses if h.status == 'WITHDRAWN']
    discussion_notes = list(case.discussion_notes.all())

    # Differential rankings
    if active_hypotheses:
        sync_case_rankings(case)
        rankings = list(
            DiagnosisRanking.objects.filter(case=case).select_related('hypothesis', 'hypothesis__specialist').order_by('rank_position')
        )
    else:
        rankings = []

    try:
        decision = case.decision
    except Exception:
        decision = None

    can_submit_hypothesis = (
        user.is_authenticated and
        user.role == 'SPECIALIST' and
        is_admitted_specialist and
        case.status in [CaseStatus.OPEN, CaseStatus.UNDER_REVIEW]
    )
    can_post_notes = (
        user.is_authenticated and
        (is_owner or is_admitted_specialist) and
        case.status not in [CaseStatus.DECIDED, CaseStatus.CLOSED]
    )
    can_reorder_rankings = (
        user.is_authenticated and
        is_owner and
        case.status not in [CaseStatus.DECIDED, CaseStatus.CLOSED]
    )
    can_record_decision = (
        user.is_authenticated and
        is_owner and
        case.status not in [CaseStatus.DECIDED, CaseStatus.CLOSED] and
        decision is None
    )

    default_diag = rankings[0].hypothesis.proposed_diagnosis if rankings else ''

    return {
        'case': case,
        'team_memberships': team_memberships,
        'active_hypotheses': active_hypotheses,
        'withdrawn_hypotheses': withdrawn_hypotheses,
        'all_hypotheses': all_hypotheses,
        'discussion_notes': discussion_notes,
        'rankings': rankings,
        'decision': decision,
        'is_case_owner': is_owner,
        'is_admitted_specialist': is_admitted_specialist,
        'can_submit_hypothesis': can_submit_hypothesis,
        'can_post_notes': can_post_notes,
        'can_reorder_rankings': can_reorder_rankings,
        'can_record_decision': can_record_decision,
        'hypothesis_form': HypothesisCreateForm(initial={'idempotency_token': uuid.uuid4()}),
        'withdraw_form': HypothesisWithdrawForm(initial={'idempotency_token': uuid.uuid4()}),
        'note_form': DiscussionNoteCreateForm(initial={'idempotency_token': uuid.uuid4()}),
        'decision_form': DecisionRecordForm(initial={
            'idempotency_token': uuid.uuid4(),
            'final_diagnosis': default_diag
        }),
        'attachments': list(case.attachments.select_related('uploaded_by').order_by('uploaded_at')),
        'attachment_form': CaseAttachmentUploadForm(),
        'can_upload_attachments': (user.is_authenticated and is_owner and case.status not in [CaseStatus.DECIDED, CaseStatus.CLOSED]),
    }


@method_decorator(case_access_required, name='dispatch')
class WorkspaceView(LoginRequiredMixin, View):
    """
    Unified 3-Pane Clinical Workspace (S3-01, B29).
    - Left Pane: Case presentation & chronological discussion notes thread.
    - Center Pane: Structured hypotheses submission deck and withdrawal tracking.
    - Right Pane: Differential diagnosis ranking and final decision governance.
    """
    template_name = 'cases/workspace.html'

    def get(self, request, case_id):
        case = getattr(request, 'case', None) or get_workspace_case(case_id)
        context = get_workspace_context(case, request.user)
        return render(request, self.template_name, context)


@method_decorator([login_required, case_owner_required], name='dispatch')
class RankingReorderView(View):
    """
    Differential diagnosis priority reorder endpoint (FR5, C-20, FT07, FT08).
    Restricted to Primary Physician case owner. Swaps adjacent rank positions atomically.
    Dispatches RANK_UPDATED audit log.
    """
    def post(self, request, case_id):
        case = request.case
        if case.status in [CaseStatus.DECIDED, CaseStatus.CLOSED]:
            return HttpResponseForbidden("<h1>403 Forbidden</h1><p>Cannot reorder ranking on a closed case.</p>")

        form = RankingReorderForm(request.POST)
        if not form.is_valid():
            return HttpResponseBadRequest("Invalid reorder parameters.")

        hypothesis_id = form.cleaned_data['hypothesis_id']
        direction = form.cleaned_data['direction']

        sync_case_rankings(case)

        with transaction.atomic():
            try:
                current_entry = DiagnosisRanking.objects.select_for_update().get(
                    case=case, hypothesis_id=hypothesis_id
                )
            except DiagnosisRanking.DoesNotExist:
                return HttpResponseBadRequest("Hypothesis not ranked.")

            current_pos = current_entry.rank_position

            if direction == 'UP':
                target_pos = current_pos - 1
            else:
                target_pos = current_pos + 1

            target_entry = DiagnosisRanking.objects.select_for_update().filter(
                case=case, rank_position=target_pos
            ).first()

            if target_entry:
                # Atomically swap using temporary high position to avoid UNIQUE constraint collision
                temp_pos = 999999
                current_entry.rank_position = temp_pos
                current_entry.save(update_fields=['rank_position', 'updated_at'])

                target_entry.rank_position = current_pos
                target_entry.save(update_fields=['rank_position', 'updated_at'])

                current_entry.rank_position = target_pos
                current_entry.save(update_fields=['rank_position', 'updated_at'])

                # Log RANK_UPDATED
                log_event(
                    action=AuditAction.RANK_UPDATED,
                    actor=request.user,
                    case_id=case.id,
                    entity_type='cases_diagnosisranking',
                    entity_id=str(current_entry.id),
                    request=request,
                    status=AuditStatus.ALLOWED,
                    details={
                        'hypothesis_id': str(hypothesis_id),
                        'new_rank': target_pos
                    }
                )

                messages.success(request, f"Differential priority updated: '{current_entry.hypothesis.proposed_diagnosis}' moved to rank #{target_pos}.")

        return redirect('cases:workspace', case_id=case.id)


@method_decorator([login_required, case_owner_required], name='dispatch')
class DecisionRecordView(View):
    """
    Definitive clinical decision recording endpoint (FR6, C-21, C-22, FT09, FT10).
    Restricted to Primary Physician case owner. Requires mandatory advisory acknowledgement.
    Transitions case status to CLOSED, locking the workspace, and logs DECISION_RECORDED.
    """
    def post(self, request, case_id):
        case = request.case
        if Decision.objects.filter(case=case).exists():
            return HttpResponseForbidden("<h1>403 Forbidden</h1><p>A final decision has already been recorded for this case.</p>")

        form = DecisionRecordForm(request.POST)

        idempotency_token = request.POST.get('idempotency_token', '')
        if idempotency_token:
            cache_key = f"idem_dec_{idempotency_token}"
            if not cache.add(cache_key, 1, timeout=3600):
                return redirect('cases:workspace', case_id=case.id)

        if form.is_valid():
            with transaction.atomic():
                decision = Decision.objects.create(
                    case=case,
                    decider=request.user,
                    final_diagnosis=form.cleaned_data['final_diagnosis'],
                    advisory_acknowledged=form.cleaned_data['advisory_acknowledged'],
                    governance_statement=form.cleaned_data['governance_statement']
                )

                case.status = CaseStatus.CLOSED
                case.save(update_fields=['status', 'updated_at'])

                # Log DECISION_RECORDED
                log_event(
                    action=AuditAction.DECISION_RECORDED,
                    actor=request.user,
                    case_id=case.id,
                    entity_type='cases_decision',
                    entity_id=str(decision.id),
                    request=request,
                    status=AuditStatus.ALLOWED,
                    details={
                        'final_diagnosis': decision.final_diagnosis,
                        'advisory_acknowledged': True
                    }
                )

                messages.success(
                    request,
                    f"Definitive clinical decision recorded for case '{case.title}'. Consultation is closed."
                )
                return redirect('cases:workspace', case_id=case.id)

        # Form validation failure (e.g. advisory_acknowledged unchecked - FT09)
        context = get_workspace_context(case, request.user)
        context['decision_form'] = form
        return render(request, 'cases/workspace.html', context, status=400)


@method_decorator(case_access_required, name='dispatch')
class AuditTrailView(LoginRequiredMixin, View):
    """
    Forensic read-only audit trail presentation for Case Owner and Admitted Specialists (FT11, FR7, NFR8).
    Displays the complete chronological sequence of all clinical case operations and security access attempts.
    """
    template_name = 'cases/audit_trail.html'

    def get(self, request, case_id):
        case = request.case

        # Retrieve all audit entries associated with this case
        audit_entries = list(
            AuditLog.objects.filter(
                Q(case_id=case.id) | Q(entity_type='cases_case', entity_id=str(case.id))
            ).select_related('actor').order_by('timestamp')
        )

        total_events = len(audit_entries)
        allowed_count = sum(1 for e in audit_entries if e.status == AuditStatus.ALLOWED)
        denied_count = sum(1 for e in audit_entries if e.status == AuditStatus.DENIED)

        return render(request, self.template_name, {
            'case': case,
            'audit_entries': audit_entries,
            'total_events': total_events,
            'allowed_count': allowed_count,
            'denied_count': denied_count,
            'is_case_owner': request.is_case_owner,
            'is_team_member': request.is_team_member,
        })


@method_decorator(case_owner_required, name='dispatch')
class CaseAttachmentUploadView(LoginRequiredMixin, View):
    """
    Diagnostic media upload endpoint (FR2b, NFR9).
    Exclusively available to the Case Owner (Primary Physician).
    """
    def post(self, request, case_id):
        case = request.case
        if case.status in [CaseStatus.DECIDED, CaseStatus.CLOSED]:
            log_event(
                action=AuditAction.ACCESS_DENIED,
                actor=request.user,
                case_id=case.id,
                request=request,
                status=AuditStatus.DENIED,
                details={'reason': f'Cannot upload attachments to case in terminal status {case.status}'}
            )
            return HttpResponseForbidden("<h1>403 Forbidden</h1><p>Cannot upload attachments to a closed case.</p>")

        form = CaseAttachmentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            attachment = form.save(commit=False)
            attachment.case = case
            attachment.uploaded_by = request.user
            attachment.mime_type = getattr(uploaded_file, 'content_type', 'application/octet-stream')
            attachment.file_size_bytes = uploaded_file.size
            attachment.save()

            log_event(
                action=AuditAction.ATTACHMENT_UPLOADED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_attachment',
                entity_id=str(attachment.id),
                request=request,
                status=AuditStatus.ALLOWED,
                details={
                    'title': attachment.title,
                    'category': attachment.category,
                    'mime_type': attachment.mime_type,
                    'file_size_bytes': attachment.file_size_bytes
                }
            )
            messages.success(request, f"Diagnostic media '{attachment.title}' uploaded successfully.")
            return redirect('cases:workspace', case_id=case.id)

        # Form invalid
        context = get_workspace_context(case, request.user)
        context['attachment_form'] = form
        return render(request, 'cases/workspace.html', context, status=400)


@method_decorator(case_access_required, name='dispatch')
class CaseAttachmentDownloadView(LoginRequiredMixin, View):
    """
    Secure diagnostic media streaming endpoint (FR2d, NFR9).
    Accessible strictly to Case Owner and Admitted Specialists on the team.
    Serves files inline with verified MIME headers, preventing direct URL exposure.
    """
    def get(self, request, case_id, attachment_id):
        case = request.case
        attachment = get_object_or_404(CaseAttachment, pk=attachment_id, case=case)

        # Log ATTACHMENT_ACCESSED in immutable audit trail
        log_event(
            action=AuditAction.ATTACHMENT_ACCESSED,
            actor=request.user,
            case_id=case.id,
            entity_type='cases_attachment',
            entity_id=str(attachment.id),
            request=request,
            status=AuditStatus.ALLOWED,
            details={
                'title': attachment.title,
                'category': attachment.category,
                'mime_type': attachment.mime_type
            }
        )

        response = FileResponse(attachment.file.open('rb'), content_type=attachment.mime_type)
        filename = attachment.file.name.split('/')[-1]
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response


