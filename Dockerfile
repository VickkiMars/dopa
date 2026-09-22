# ==============================================================================
# DOPA Clinical Platform - Production Dockerfile
# Base: Python 3.12 Slim Linux Container
# Runtime: Gunicorn WSGI Server + WhiteNoise Static Pipeline
# ==============================================================================

FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DJANGO_SETTINGS_MODULE=dopa_project.settings

# Install system dependencies (curl for container healthcheck probe, libpq5 for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user for clinical security
RUN groupadd -r dopa && useradd -r -g dopa -u 1000 -d /app dopa

WORKDIR /app

# Copy dependency specification and install via pip
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy entrypoint script and make executable
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy application source tree
COPY . /app/

# Create persistent storage directories and assign ownership to dopa user
RUN mkdir -p /app/staticfiles /app/media /app/case_attachments && \
    chown -R dopa:dopa /app

# Pre-compile compressed and hashed static files via WhiteNoise
RUN python manage.py collectstatic --noinput

# Switch to non-root clinical service user
USER dopa

EXPOSE 8000

# Automated container healthcheck probing the /health/ endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]

# Production Gunicorn worker execution
CMD ["gunicorn", "dopa_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "120"]
