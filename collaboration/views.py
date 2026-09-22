import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.urls import reverse

from audit.services import log_event
from audit.models import AuditAction, AuditStatus
from cases.models import Case, CaseStatus
from cases.decorators import specialist_team_required, hypothesis_author_required, case_access_required
from cases.services.notification_service import notify_case_team
from .models import Hypothesis, DiscussionNote, HypothesisStatus
from .forms import HypothesisCreateForm, HypothesisWithdrawForm, DiscussionNoteCreateForm


@method_decorator([login_required, specialist_team_required], name='dispatch')
class HypothesisCreateView(View):
    """
    Structured hypothesis submission endpoint (FR3, C-16, FT06).
    Enforces specialist role & CaseTeam admission, mandatory fields (min 20 chars),
    idempotency token handling, and case status transition to UNDER_REVIEW.
    """
    def post(self, request, case_id):
        case = request.case
        form = HypothesisCreateForm(request.POST)

        # Idempotency token check (B18 / NFR5)
        idempotency_token = request.POST.get('idempotency_token', '')
        if idempotency_token:
            cache_key = f"idem_hypo_{idempotency_token}"
            if not cache.add(cache_key, 1, timeout=3600):
                # Duplicate network transmission detected; redirect safely to workspace
                messages.warning(request, "Duplicate submission detected and ignored.")
                return redirect('cases:workspace', case_id=case.id)

        if form.is_valid():
            hypothesis = form.save(commit=False)
            hypothesis.case = case
            hypothesis.specialist = request.user
            hypothesis.save()

            # Transition case status from OPEN to UNDER_REVIEW
            if case.status == CaseStatus.OPEN:
                case.status = CaseStatus.UNDER_REVIEW
                case.save(update_fields=['status', 'updated_at'])

            # Log HYPOTHESIS_SUBMITTED in audit trail
            log_event(
                action=AuditAction.HYPOTHESIS_SUBMITTED,
                actor=request.user,
                case_id=case.id,
                entity_type='collaboration_hypothesis',
                entity_id=str(hypothesis.id),
                request=request,
                status=AuditStatus.ALLOWED,
                details={
                    'proposed_diagnosis': hypothesis.proposed_diagnosis,
                    'case_id': str(case.id)
                }
            )

            # Dispatch In-App & Email Notification (FR-NOTIFY-01)
            notify_case_team(
                case=case,
                verb='HYPOTHESIS_SUBMITTED',
                title="New Diagnostic Hypothesis Submitted",
                message=f"Dr. {request.user.full_name} submitted a new hypothesis on case '{case.title}': '{hypothesis.proposed_diagnosis}'.",
                exclude_user=request.user,
                action_url=reverse('cases:workspace', kwargs={'case_id': case.id}),
                send_email=True
            )

            messages.success(request, f"Hypothesis '{hypothesis.proposed_diagnosis}' submitted successfully.")
            return redirect('cases:workspace', case_id=case.id)

        # Form validation failure - return 400 Bad Request with form error context
        from cases.views import get_workspace_context
        context = get_workspace_context(case, request.user)
        context['hypothesis_form'] = form
        return render(request, 'cases/workspace.html', context, status=400)


@method_decorator([login_required, hypothesis_author_required], name='dispatch')
class HypothesisWithdrawView(View):
    """
    Hypothesis withdrawal endpoint (B16, FAULT-03, FAULT-06).
    Updates status to WITHDRAWN, preserves in workspace with [WITHDRAWN] badge,
    records mandatory withdrawal reason, and dispatches HYPOTHESIS_WITHDRAWN audit entry.
    """
    def post(self, request, case_id, hypo_id):
        case = request.case
        hypothesis = request.hypothesis
        form = HypothesisWithdrawForm(request.POST)

        idempotency_token = request.POST.get('idempotency_token', '')
        if idempotency_token:
            cache_key = f"idem_withdraw_{idempotency_token}"
            if not cache.add(cache_key, 1, timeout=3600):
                return redirect('cases:workspace', case_id=case.id)

        if form.is_valid():
            reason = form.cleaned_data['withdrawal_reason']
            hypothesis.withdraw(reason)

            # Log HYPOTHESIS_WITHDRAWN in audit trail
            log_event(
                action=AuditAction.HYPOTHESIS_WITHDRAWN,
                actor=request.user,
                case_id=case.id,
                entity_type='collaboration_hypothesis',
                entity_id=str(hypothesis.id),
                request=request,
                status=AuditStatus.ALLOWED,
                details={
                    'withdrawal_reason': reason,
                    'case_id': str(case.id)
                }
            )

            messages.info(request, f"Hypothesis '{hypothesis.proposed_diagnosis}' has been marked as withdrawn.")
            return redirect('cases:workspace', case_id=case.id)

        from cases.views import get_workspace_context
        context = get_workspace_context(case, request.user)
        context['withdraw_form'] = form
        context['withdraw_error_hypo_id'] = str(hypothesis.id)
        return render(request, 'cases/workspace.html', context, status=400)


@method_decorator([login_required, case_access_required], name='dispatch')
class DiscussionNoteCreateView(View):
    """
    Chronological discussion note posting endpoint (FR4, C-19, B17).
    Allows both Case Owner and admitted Specialists to post narrative notes.
    """
    def post(self, request, case_id):
        case = request.case
        if case.status in [CaseStatus.DECIDED, CaseStatus.CLOSED]:
            return HttpResponseForbidden("<h1>403 Forbidden</h1><p>Cannot post notes to a closed case.</p>")

        form = DiscussionNoteCreateForm(request.POST)

        idempotency_token = request.POST.get('idempotency_token', '')
        if idempotency_token:
            cache_key = f"idem_note_{idempotency_token}"
            if not cache.add(cache_key, 1, timeout=3600):
                return redirect('cases:workspace', case_id=case.id)

        if form.is_valid():
            note = form.save(commit=False)
            note.case = case
            note.author = request.user
            note.save()

            # Log DISCUSSION_POSTED
            log_event(
                action=AuditAction.DISCUSSION_POSTED,
                actor=request.user,
                case_id=case.id,
                entity_type='collaboration_discussionnote',
                entity_id=str(note.id),
                request=request,
                status=AuditStatus.ALLOWED,
                details={
                    'note_length': len(note.body),
                    'case_id': str(case.id)
                }
            )

            # Dispatch In-App Notification (FR-NOTIFY-01)
            notify_case_team(
                case=case,
                verb='DISCUSSION_POSTED',
                title="New Clinical Discussion Note",
                message=f"Dr. {request.user.full_name} posted a note on case '{case.title}'.",
                exclude_user=request.user,
                action_url=reverse('cases:workspace', kwargs={'case_id': case.id}),
                send_email=False
            )

            messages.success(request, "Discussion note added.")
            return redirect('cases:workspace', case_id=case.id)

        from cases.views import get_workspace_context
        context = get_workspace_context(case, request.user)
        context['note_form'] = form
        return render(request, 'cases/workspace.html', context, status=400)
