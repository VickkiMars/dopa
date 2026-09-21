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
        case = get_object_or_404(Case, pk=case_id)

        is_owner = (case.owner == request.user)
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
