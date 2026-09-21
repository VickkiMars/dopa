from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.cache import cache

from accounts.models import User, Role
from audit.models import AuditLog, AuditAction, AuditStatus


class Sprint1AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        cache.clear()

    def test_ft01_register_primary_physician_and_role_immutability(self):
        """
        FT01: Register with role = PRIMARY_PHYSICIAN.
        Account created; role bound immutably; password hashed via PBKDF2.
        """
        register_url = reverse('accounts:register')
        payload = {
            'full_name': 'Dr. Chukwuemeka Eze',
            'email': 'dr.eze@hospital.org',
            'role': Role.PRIMARY_PHYSICIAN,
            'password': 'SecureClinicalPass123!',
            'password_confirm': 'SecureClinicalPass123!'
        }
        
        response = self.client.post(register_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('cases:dashboard'))

        # Verify user persisted in database
        user = User.objects.filter(email='dr.eze@hospital.org').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.full_name, 'Dr. Chukwuemeka Eze')
        self.assertEqual(user.role, Role.PRIMARY_PHYSICIAN)
        self.assertTrue(user.is_primary_physician)
        self.assertFalse(user.is_specialist)

        # Verify PBKDF2 password hashing (no plaintext)
        self.assertTrue(user.check_password('SecureClinicalPass123!'))
        self.assertTrue(user.password.startswith('pbkdf2_'))

        # Verify Role Immutability (C-01, G-07): attempting to change role raises ValidationError
        user.role = Role.SPECIALIST
        with self.assertRaises(ValidationError):
            user.save()

    def test_ft02_login_with_valid_credentials_and_audit(self):
        """
        FT02: Login with valid credentials.
        Session established; role-based dashboard shown; audit record logged.
        """
        user = User.objects.create_user(
            email='specialist.adams@clinic.org',
            full_name='Dr. Sarah Adams',
            role=Role.SPECIALIST,
            password='SpecialistPassword2026!'
        )

        login_url = reverse('accounts:login')
        payload = {
            'email': 'specialist.adams@clinic.org',
            'password': 'SpecialistPassword2026!'
        }

        response = self.client.post(login_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('cases:dashboard'))

        # Verify session is established
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(str(user.id), self.client.session['_auth_user_id'])

        # Verify audit log entry created (LOGIN_SUCCESS)
        audit_entry = AuditLog.objects.filter(
            actor=user,
            action=AuditAction.LOGIN_SUCCESS,
            status=AuditStatus.ALLOWED
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.entity_type, 'accounts_user')
        self.assertEqual(audit_entry.entity_id, str(user.id))

    def test_ft03_access_dashboard_without_authentication(self):
        """
        FT03: Access dashboard without authentication.
        Redirects to login; zero confidential clinical data exposed.
        """
        dashboard_url = reverse('cases:dashboard')
        response = self.client.get(dashboard_url)
        
        # Expected redirect to login with ?next=/dashboard/
        self.assertEqual(response.status_code, 302)
        expected_redirect = f"{reverse('accounts:login')}?next={dashboard_url}"
        self.assertRedirects(response, expected_redirect)

    def test_failed_login_audit_and_rate_limiting(self):
        """
        Verify that failed logins produce LOGIN_FAILED audit entries
        and that exceeding 5 failed attempts locks out the IP address (C-04).
        """
        login_url = reverse('accounts:login')
        payload = {
            'email': 'unknown.attacker@threat.net',
            'password': 'WrongPassword123'
        }

        # First 4 failed attempts should return form error (200 with re-rendered form)
        for i in range(4):
            response = self.client.post(login_url, payload)
            self.assertEqual(response.status_code, 200)

        # 5th attempt
        self.client.post(login_url, payload)

        # 6th attempt should be blocked by rate-limiting (HTTP 429)
        response = self.client.post(login_url, payload)
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many failed login attempts", status_code=429)

        # Check that LOGIN_FAILED audit entries were created
        failed_audits = AuditLog.objects.filter(
            action=AuditAction.LOGIN_FAILED,
            status=AuditStatus.DENIED
        )
        self.assertGreaterEqual(failed_audits.count(), 5)

    def test_audit_log_append_only_immutability(self):
        """
        Verify that AuditLog records are strictly append-only (NFR8, C-26).
        Updating or deleting existing audit logs must raise ValidationError.
        """
        entry = AuditLog.objects.create(
            action=AuditAction.LOGIN_SUCCESS,
            ip_address='127.0.0.1',
            status=AuditStatus.ALLOWED,
            details={'test': True}
        )
        self.assertIsNotNone(entry.id)

        # Attempting to modify fields must fail
        entry.action = AuditAction.ACCESS_DENIED
        with self.assertRaises(ValidationError):
            entry.save()

        # Attempting to delete must fail
        with self.assertRaises(ValidationError):
            entry.delete()
