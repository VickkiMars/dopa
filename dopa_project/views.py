import os
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET


@require_GET
def health_check(request):
    """
    Lightweight health check probe for cloud orchestrators (Render, Kubernetes, Docker).
    Verifies system liveness and database query readiness.
    Returns HTTP 200 if database is reachable, HTTP 503 if disconnected.
    """
    db_connected = False
    db_error = None

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                db_connected = True
    except Exception as exc:
        db_error = str(exc)

    is_healthy = db_connected
    status_code = 200 if is_healthy else 503

    payload = {
        "status": "healthy" if is_healthy else "unhealthy",
        "database": "connected" if db_connected else f"disconnected ({db_error})",
        "service": "dopa-clinical",
        "version": "1.0.0",
        "debug": os.getenv("DEBUG", "True") == "True",
        "timestamp": timezone.now().isoformat(),
    }

    return JsonResponse(payload, status=status_code)
