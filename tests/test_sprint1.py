import uuid
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from accounts.models import User, Role
from accounts.rate_limit import is_ip_rate_limited, record_failed_attempt, clear_failed_attempts
from audit.models import AuditLog, AuditAction, AuditStatus
from audit.services import get_client_ip, log_event


class RegistrationValidationEdgeCaseTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('accounts:register')

    def test_duplicate_email_case_insensitive_rejection(self):
        """Verify that duplicate emails (regardless of case) are strictly rejected."""
        User.objects.create_user(
            email='dr.okafor@hospital.org',
            full_name='Dr. Emeka Okafor',
            role=Role.PRIMARY_PHYSICIAN,
            password='SecurePassword123!'
        )

        payload = {
            'full_name': 'Dr. E. Okafor Impersonator',
            'email': 'DR.OKAFOR@HOSPITAL.ORG',  # Uppercase variant
            'role': Role.SPECIALIST,
            'password': 'DifferentPassword123!',
            'password_confirm': 'DifferentPassword123!'
        }
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'email', 'A user with this email address is already registered.')
        self.assertEqual(User.objects.count(), 1)

    def test_password_too_short_rejected(self):
        """Passwords under 8 characters must fail validation."""
        payload = {
            'full_name': 'Dr. Short Pass',
            'email': 'short@hospital.org',
            'role': Role.SPECIALIST,
            'password': 'short',
            'password_confirm': 'short'
        }
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'password', 'Ensure this value has at least 8 characters (it has 5).')

    def test_password_confirmation_mismatch_rejected(self):
        """Mismatched confirmation password must fail validation."""
        payload = {
            'full_name': 'Dr. Mismatch',
            'email': 'mismatch@hospital.org',
            'role': Role.PRIMARY_PHYSICIAN,
            'password': 'ValidPassword123!',
            'password_confirm': 'DifferentPassword123!'
        }
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'password_confirm', 'Passwords do not match.')

    def test_entirely_numeric_password_rejected(self):
        """Pass validation prevents numeric-only passwords."""
        payload = {
            'full_name': 'Dr. Numeric',
            'email': 'numeric@hospital.org',
            'role': Role.PRIMARY_PHYSICIAN,
            'password': '984719284719',
            'password_confirm': '984719284719'
        }
        response = self.client.post(self.register_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', None, 'This password is entirely numeric.')

    def test_missing_required_fields_rejected(self):
        """All form fields are mandatory."""
        response = self.client.post(self.register_url, {})
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'full_name', 'This field is required.')
        self.assertFormError(response, 'form', 'email', 'This field is required.')
        self.assertFormError(response, 'form', 'role', 'This field is required.')
        self.assertFormError(response, 'form', 'password', 'This field is required.')

    def test_xss_characters_in_full_name_escaped(self):
        """XSS payloads in full_name are stored safely and escaped in templates."""
        payload = {
            'full_name': '<script>alert("xss")</script> Dr. Test',
            'email': 'xss.test@hospital.org',
            'role': Role.PRIMARY_PHYSICIAN,
            'password': 'SafePassword123!',
            'password_confirm': 'SafePassword123!'
        }
        response = self.client.post(self.register_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        # Verify script tag is escaped in HTML
        self.assertContains(response, '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert("xss")</script>')


class AuthenticationAndSessionSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        cache.clear()
        self.login_url = reverse('accounts:login')
        self.user = User.objects.create_user(
            email='dr.bello@hospital.org',
            full_name='Dr. Amina Bello',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )

    def test_case_insensitive_email_login(self):
        """User can log in regardless of email casing."""
        payload = {
            'email': 'DR.BELLO@HOSPITAL.ORG',
            'password': 'ValidPassword123!'
        }
        response = self.client.post(self.login_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(str(self.user.id), self.client.session['_auth_user_id'])

    def test_inactive_user_rejected(self):
        """Inactive accounts cannot authenticate."""
        self.user.is_active = False
        self.user.save()

        payload = {
            'email': 'dr.bello@hospital.org',
            'password': 'ValidPassword123!'
        }
        response = self.client.post(self.login_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This account is currently inactive.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_open_redirect_protection_on_next_param(self):
        """Malicious external URLs in ?next= are neutralized and redirect to safe dashboard."""
        payload = {
            'email': 'dr.bello@hospital.org',
            'password': 'ValidPassword123!',
            'next': 'https://malicious-phishing-site.com/steal'
        }
        response = self.client.post(self.login_url, payload)
        # Should redirect to default internal dashboard, NOT external URL
        self.assertRedirects(response, reverse('cases:dashboard'))

    def test_safe_internal_next_param_preserved(self):
        """Valid internal relative paths in ?next= are respected."""
        payload = {
            'email': 'dr.bello@hospital.org',
            'password': 'ValidPassword123!',
            'next': '/dashboard/'
        }
        response = self.client.post(self.login_url, payload)
        self.assertRedirects(response, '/dashboard/')

    def test_session_cookie_security_flags(self):
        """Verify session cookie attributes meet NFR1, NFR2 (HttpOnly, SameSite, Age)."""
        payload = {
            'email': 'dr.bello@hospital.org',
            'password': 'ValidPassword123!'
        }
        response = self.client.post(self.login_url, payload)
        session_cookie = response.cookies['sessionid']
        self.assertTrue(session_cookie['httponly'])
        self.assertEqual(session_cookie['samesite'], 'Lax')
        self.assertEqual(session_cookie['max-age'], 1800)  # 30-min idle timeout

    def test_logout_flushes_session_and_logs_audit(self):
        """Logging out flushes authentication session and writes LOGOUT audit record."""
        self.client.force_login(self.user)
        self.assertIn('_auth_user_id', self.client.session)

        logout_url = reverse('accounts:logout')
        response = self.client.post(logout_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

        logout_audit = AuditLog.objects.filter(
            actor=self.user,
            action=AuditAction.LOGOUT,
            status=AuditStatus.ALLOWED
        ).first()
        self.assertIsNotNone(logout_audit)


class RateLimitingAndForensicsTests(TestCase):
    def setUp(self):
        self.client = Client()
        cache.clear()
        self.login_url = reverse('accounts:login')

    def test_rate_limiting_exact_threshold(self):
        """Verify exactly 5 failed attempts are tracked and the 6th is blocked with 429."""
        ip = '198.51.100.42'
        payload = {'email': 'nobody@hospital.org', 'password': 'WrongPassword!'}

        for i in range(1, 6):
            response = self.client.post(self.login_url, payload, REMOTE_ADDR=ip)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(cache.get(f'login_failed_ip_{ip}'), i)

        # 6th attempt must be throttled
        response = self.client.post(self.login_url, payload, REMOTE_ADDR=ip)
        self.assertEqual(response.status_code, 429)

    def test_successful_login_clears_failed_attempts(self):
        """Successful login resets the failed attempts counter for that IP."""
        user = User.objects.create_user(
            email='dr.reset@hospital.org',
            full_name='Dr. Reset Tester',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )
        ip = '203.0.113.10'

        # Record 3 failed attempts
        for _ in range(3):
            self.client.post(self.login_url, {'email': user.email, 'password': 'bad'}, REMOTE_ADDR=ip)
        self.assertEqual(cache.get(f'login_failed_ip_{ip}'), 3)

        # Successful login
        self.client.post(self.login_url, {'email': user.email, 'password': 'ValidPassword123!'}, REMOTE_ADDR=ip)
        self.assertIsNone(cache.get(f'login_failed_ip_{ip}'))

    def test_forwarded_for_header_ip_extraction(self):
        """Verify real client IP is properly extracted behind proxy/CDN."""
        class MockRequest:
            META = {'HTTP_X_FORWARDED_FOR': '203.0.113.99, 10.0.0.1', 'REMOTE_ADDR': '10.0.0.1'}

        extracted_ip = get_client_ip(MockRequest())
        self.assertEqual(extracted_ip, '203.0.113.99')

    def test_anonymous_failed_login_audit_record(self):
        """Failed logins with unknown accounts record audit entry with actor=None and attempted_email."""
        self.client.post(self.login_url, {'email': 'hacker@darkweb.org', 'password': 'guess'}, REMOTE_ADDR='192.0.2.1')
        entry = AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).latest('timestamp')
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.ip_address, '192.0.2.1')
        self.assertEqual(entry.status, AuditStatus.DENIED)
        self.assertEqual(entry.details.get('attempted_email'), 'hacker@darkweb.org')


class PasswordResetWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='dr.recover@hospital.org',
            full_name='Dr. Recovery Patient',
            role=Role.SPECIALIST,
            password='OldPassword123!'
        )

    def test_password_reset_end_to_end_flow(self):
        """Complete tokenized password reset workflow."""
        # 1. Request reset
        reset_url = reverse('accounts:password_reset')
        response = self.client.post(reset_url, {'email': 'dr.recover@hospital.org'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('DOPA Clinical Decision Support Platform', mail.outbox[0].subject)

        # 2. Extract token from mail
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        # 3. View confirm form (Django uses an internal redirect for token referer safety)
        response = self.client.get(confirm_url, follow=True)
        self.assertEqual(response.status_code, 200)

        # 4. Submit new password to the active form action URL
        form_action_url = response.request['PATH_INFO']
        post_response = self.client.post(form_action_url, {
            'new_password1': 'NewBrandSecure2026!',
            'new_password2': 'NewBrandSecure2026!'
        }, follow=True)
        self.assertEqual(post_response.status_code, 200)
        self.assertRedirects(post_response, reverse('accounts:password_reset_complete'))

        # 5. Verify database password updated
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewBrandSecure2026!'))
        self.assertFalse(self.user.check_password('OldPassword123!'))

        # 6. Verify login with new password succeeds
        login_response = self.client.post(reverse('accounts:login'), {
            'email': 'dr.recover@hospital.org',
            'password': 'NewBrandSecure2026!'
        }, follow=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn('_auth_user_id', self.client.session)


class UserModelAndManagerTests(TestCase):
    def test_create_user_missing_email_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            User.objects.create_user(email='', full_name='Dr. Blank', role=Role.PRIMARY_PHYSICIAN)
        self.assertIn('Email address is required', str(ctx.exception))

    def test_create_user_missing_full_name_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            User.objects.create_user(email='test@clinic.org', full_name='', role=Role.PRIMARY_PHYSICIAN)
        self.assertIn('Full name is required', str(ctx.exception))

    def test_create_user_invalid_role_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            User.objects.create_user(email='test@clinic.org', full_name='Dr. Test', role='ADMINISTRATOR')
        self.assertIn('Invalid role', str(ctx.exception))

    def test_create_superuser_attributes(self):
        admin = User.objects.create_superuser(
            email='admin@hospital.org',
            full_name='Super Admin',
            password='AdminPassword123!'
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.role, Role.PRIMARY_PHYSICIAN)

    def test_user_string_representation(self):
        user = User.objects.create_user(
            email='dr.dan@hospital.org',
            full_name='Dr. Danjuma',
            role=Role.SPECIALIST,
            password='Pass1234567!'
        )
        self.assertEqual(str(user), 'Dr. Danjuma (Specialist)')

    def test_role_properties(self):
        doc = User.objects.create_user(email='doc@h.org', full_name='Dr. Doc', role=Role.PRIMARY_PHYSICIAN, password='p')
        spec = User.objects.create_user(email='spec@h.org', full_name='Dr. Spec', role=Role.SPECIALIST, password='p')
        self.assertTrue(doc.is_primary_physician)
        self.assertFalse(doc.is_specialist)
        self.assertFalse(spec.is_primary_physician)
        self.assertTrue(spec.is_specialist)


class AuditLogForensicsModelTests(TestCase):
    def test_audit_string_representation(self):
        user = User.objects.create_user(email='aud@h.org', full_name='Dr. Audit', role=Role.PRIMARY_PHYSICIAN, password='p')
        entry = AuditLog.objects.create(
            actor=user,
            action=AuditAction.CASE_CREATED,
            status=AuditStatus.ALLOWED
        )
        self.assertIn('CASE_CREATED by Dr. Audit (ALLOWED)', str(entry))

    def test_audit_string_representation_anonymous(self):
        entry = AuditLog.objects.create(
            actor=None,
            action=AuditAction.LOGIN_FAILED,
            status=AuditStatus.DENIED
        )
        self.assertIn('LOGIN_FAILED by Anonymous (DENIED)', str(entry))
