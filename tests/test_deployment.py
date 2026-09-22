from django.test import TestCase, Client, override_settings
from django.urls import reverse
from unittest.mock import patch
import os
import dj_database_url


class HealthCheckEndpointTests(TestCase):
    """Automated verification of the /health/ probe for cloud orchestrators."""

    def setUp(self):
        self.client = Client()
        self.health_url = reverse('health_check')

    def test_health_check_returns_200_when_healthy(self):
        """GET /health/ returns HTTP 200 with JSON status payload when DB is connected."""
        response = self.client.get(self.health_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

        data = response.json()
        self.assertEqual(data['status'], 'healthy')
        self.assertEqual(data['database'], 'connected')
        self.assertEqual(data['service'], 'dopa-clinical')
        self.assertEqual(data['version'], '1.0.0')
        self.assertIn('timestamp', data)

    def test_health_check_returns_503_when_database_fails(self):
        """GET /health/ returns HTTP 503 and reports disconnected when database query fails."""
        with patch('django.db.connection.cursor') as mock_cursor:
            mock_cursor.side_effect = Exception("Database connection timeout")
            response = self.client.get(self.health_url)
            self.assertEqual(response.status_code, 503)

            data = response.json()
            self.assertEqual(data['status'], 'unhealthy')
            self.assertIn('disconnected', data['database'])
            self.assertIn('Database connection timeout', data['database'])

    def test_health_check_rejects_post_method(self):
        """POST /health/ returns HTTP 405 Method Not Allowed."""
        response = self.client.post(self.health_url, {})
        self.assertEqual(response.status_code, 405)


class DeploymentSettingsAndWhiteNoiseTests(TestCase):
    """
    Verification of production packaging, WhiteNoise static pipeline, and dual-database configuration.
    """

    def test_whitenoise_middleware_configured(self):
        """WhiteNoise middleware must be present immediately following SecurityMiddleware."""
        from django.conf import settings
        middleware = settings.MIDDLEWARE
        self.assertIn('whitenoise.middleware.WhiteNoiseMiddleware', middleware)
        sec_idx = middleware.index('django.middleware.security.SecurityMiddleware')
        wn_idx = middleware.index('whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertEqual(wn_idx, sec_idx + 1)

    def test_whitenoise_storage_backend(self):
        """Production staticfiles storage must use WhiteNoise's CompressedManifestStaticFilesStorage."""
        from django.conf import settings
        storage_backend = settings.STORAGES['staticfiles']['BACKEND']
        self.assertEqual(storage_backend, 'whitenoise.storage.CompressedManifestStaticFilesStorage')

    def test_secure_proxy_ssl_header_configured(self):
        """SECURE_PROXY_SSL_HEADER must be configured for cloud reverse proxies (Render edge)."""
        from django.conf import settings
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))

    def test_database_url_postgresql_parsing(self):
        """Verify dj_database_url correctly parses Supabase/PostgreSQL connection string."""
        sample_url = "postgres://postgres:secret123@db.supabase.co:5432/dopa_prod"
        db_config = dj_database_url.config(
            default=sample_url,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True
        )

        self.assertEqual(db_config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(db_config['NAME'], 'dopa_prod')
        self.assertEqual(db_config['USER'], 'postgres')
        self.assertEqual(db_config['PASSWORD'], 'secret123')
        self.assertEqual(db_config['HOST'], 'db.supabase.co')
        self.assertEqual(db_config['PORT'], 5432)
        self.assertEqual(db_config['CONN_MAX_AGE'], 600)
        self.assertEqual(db_config['CONN_HEALTH_CHECKS'], True)
        self.assertEqual(db_config['OPTIONS'], {'sslmode': 'require'})

    def test_csrf_trusted_origins_parsing(self):
        """Verify CSRF trusted origins parsing handles comma-separated lists and whitespace."""
        raw_origins = "https://*.onrender.com, https://dopa.clinic "
        parsed = [origin.strip() for origin in raw_origins.split(',') if origin.strip()]
        self.assertEqual(parsed, ['https://*.onrender.com', 'https://dopa.clinic'])
