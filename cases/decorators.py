from functools import wraps
from typing import List, Union
from django.http import HttpResponseForbidden, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import PermissionDenied

from audit.services import log_event
from audit.models import AuditAction, AuditStatus
from .models import Case, CaseTeam


def role_required(allowed_roles: Union[str, List[str]]):
    """
    Decorator enforcing that the authenticated user possesses one of the allowed roles.
    Rejects unauthorized access with HTTP 403 and records an ACCESS_DENIED audit log entry.
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('accounts:login')

            if request.user.role not in allowed_roles:
                log_event(
                    action=AuditAction.ACCESS_DENIED,
                    actor=request.user,
                    request=request,
                    status=AuditStatus.DENIED,
                    details={
                        'reason': f'Role {request.user.role} not in allowed roles {allowed_roles}',
                        'path': request.path
                    }
                )
                return HttpResponseForbidden(
                    "<h1>403 Forbidden</h1><p>Access denied: Your clinical role lacks permission for this operation.</p>"
                )
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def case_owner_required(view_func):
    """
    Decorator verifying that the requesting user is the designated owner of the target case.
    Rejects unauthorized access with HTTP 403 and records an ACCESS_DENIED audit log entry.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')

        case_id = kwargs.get('case_id') or kwargs.get('pk')
        case = get_object_or_404(Case, pk=case_id)

        if case.owner != request.user:
            log_event(
                action=AuditAction.ACCESS_DENIED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_case',
                entity_id=str(case.id),
                request=request,
                status=AuditStatus.DENIED,
                details={
                    'reason': 'Actor is not the Primary Physician case owner',
                    'owner_id': str(case.owner.id)
                }
            )
            return HttpResponseForbidden(
                "<h1>403 Forbidden</h1><p>Access denied: Only the case owner (Primary Physician) can perform this action.</p>"
            )

        # Attach case to request to eliminate redundant database lookup in view
        request.case = case
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def case_access_required(view_func):
    """
    Decorator verifying that the requesting user has legitimate clinical access to the case
    (either as the Case Owner or as an admitted Specialist on the Case Team).
    Rejects unauthorized access with HTTP 403 and records an ACCESS_DENIED audit log entry.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')

        case_id = kwargs.get('case_id') or kwargs.get('pk')
        try:
            from .views import get_workspace_case
            case = get_workspace_case(case_id)
            is_owner = (case.owner_id == request.user.id)
            is_team_member = any(m.specialist_id == request.user.id for m in case.team_memberships.all())
        except Exception:
            case = get_object_or_404(Case, pk=case_id)
            is_owner = (case.owner_id == request.user.id)
            is_team_member = CaseTeam.objects.filter(case=case, specialist=request.user).exists()

        if not (is_owner or is_team_member):
            log_event(
                action=AuditAction.ACCESS_DENIED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_case',
                entity_id=str(case.id),
                request=request,
                status=AuditStatus.DENIED,
                details={
                    'reason': 'Actor is neither case owner nor an admitted specialist',
                    'path': request.path
                }
            )
            return HttpResponseForbidden(
                "<h1>403 Forbidden</h1><p>Access denied: You have not been admitted to this clinical consultation team.</p>"
            )

        request.case = case
        request.is_case_owner = is_owner
        request.is_team_member = is_team_member
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def specialist_team_required(view_func):
    """
    Decorator enforcing that:
    1. User is authenticated and possesses the SPECIALIST role.
    2. User is admitted to the CaseTeam for this case.
    3. Case is not in a terminal state (DECIDED or CLOSED).
    Rejects unauthorized access with HTTP 403 and records an ACCESS_DENIED audit log entry.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')

        case_id = kwargs.get('case_id') or kwargs.get('pk')
        case = get_object_or_404(Case, pk=case_id)

        if getattr(request.user, 'role', None) != 'SPECIALIST':
            log_event(
                action=AuditAction.ACCESS_DENIED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_case',
                entity_id=str(case.id),
                request=request,
                status=AuditStatus.DENIED,
                details={
                    'reason': f'Role {getattr(request.user, "role", None)} is not SPECIALIST',
                    'path': request.path
                }
            )
            return HttpResponseForbidden(
                "<h1>403 Forbidden</h1><p>Access denied: Only specialists can submit diagnostic hypotheses.</p>"
            )

        is_admitted = CaseTeam.objects.filter(case=case, specialist=request.user).exists()
        if not is_admitted:
            log_event(
                action=AuditAction.ACCESS_DENIED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_case',
                entity_id=str(case.id),
                request=request,
                status=AuditStatus.DENIED,
                details={
                    'reason': 'Specialist is not an admitted member of this case team',
                    'path': request.path
                }
            )
            return HttpResponseForbidden(
                "<h1>403 Forbidden</h1><p>Access denied: You must be an admitted specialist on this case team.</p>"
            )

        if case.status in ['DECIDED', 'CLOSED']:
            log_event(
                action=AuditAction.ACCESS_DENIED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_case',
                entity_id=str(case.id),
                request=request,
                status=AuditStatus.DENIED,
                details={
                    'reason': f'Cannot modify case in terminal status {case.status}',
                    'path': request.path
                }
            )
            return HttpResponseForbidden(
                "<h1>403 Forbidden</h1><p>Access denied: This clinical case is already decided or closed.</p>"
            )

        request.case = case
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def hypothesis_author_required(view_func):
    """
    Decorator verifying that:
    1. User is authenticated.
    2. User is the author (specialist) of the specified hypothesis.
    3. Case is not in a terminal state (DECIDED or CLOSED).
    Rejects unauthorized access with HTTP 403 and records an ACCESS_DENIED audit log entry.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs):
        from collaboration.models import Hypothesis

        if not request.user.is_authenticated:
            return redirect('accounts:login')

        case_id = kwargs.get('case_id')
        hypo_id = kwargs.get('hypo_id') or kwargs.get('hypothesis_id')
        case = get_object_or_404(Case, pk=case_id)
        hypothesis = get_object_or_404(Hypothesis, pk=hypo_id, case=case)

        if hypothesis.specialist != request.user:
            log_event(
                action=AuditAction.ACCESS_DENIED,
                actor=request.user,
                case_id=case.id,
                entity_type='collaboration_hypothesis',
                entity_id=str(hypothesis.id),
                request=request,
                status=AuditStatus.DENIED,
                details={
                    'reason': 'Actor is not the author of this hypothesis',
                    'path': request.path
                }
            )
            return HttpResponseForbidden(
                "<h1>403 Forbidden</h1><p>Access denied: Only the authoring specialist can withdraw this hypothesis.</p>"
            )

        if case.status in ['DECIDED', 'CLOSED']:
            log_event(
                action=AuditAction.ACCESS_DENIED,
                actor=request.user,
                case_id=case.id,
                entity_type='cases_case',
                entity_id=str(case.id),
                request=request,
                status=AuditStatus.DENIED,
                details={
                    'reason': f'Cannot modify hypothesis on case with terminal status {case.status}',
                    'path': request.path
                }
            )
            return HttpResponseForbidden(
                "<h1>403 Forbidden</h1><p>Access denied: This clinical case is already decided or closed.</p>"
            )

        request.case = case
        request.hypothesis = hypothesis
        return view_func(request, *args, **kwargs)
    return _wrapped_view

