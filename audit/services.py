import logging
from typing import Optional, Any, Dict
from django.http import HttpRequest
from .models import AuditLog, AuditAction, AuditStatus

logger = logging.getLogger('dopa.audit')


def get_client_ip(request: Optional[HttpRequest]) -> Optional[str]:
    """Extract real client IP address from request headers."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_event(
    action: str,
    actor: Optional[Any] = None,
    entity_type: str = '',
    entity_id: str = '',
    case_id: Optional[Any] = None,
    ip_address: Optional[str] = None,
    request: Optional[HttpRequest] = None,
    status: str = AuditStatus.ALLOWED,
    details: Optional[Dict[str, Any]] = None
) -> AuditLog:
    """
    Append an immutable event to the centralized audit trail.
    """
    if request and not ip_address:
        ip_address = get_client_ip(request)
    if request and not actor and hasattr(request, 'user') and request.user.is_authenticated:
        actor = request.user

    log_entry = AuditLog.objects.create(
        action=action,
        actor=actor,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else '',
        case_id=case_id,
        ip_address=ip_address,
        status=status,
        details=details or {}
    )
    
    logger.info(f"AUDIT: {action} by {actor} [status={status}, ip={ip_address}]")
    return log_entry
