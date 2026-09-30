from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import Role
from audit.models import AuditLog, AuditAction, AuditStatus

User = get_user_model()


class DemoAccountLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.demo_login_url = reverse('accounts:demo_login')
        self.login_page_url = reverse('accounts:login')
        self.register_page_url = reverse('accounts:register')

        # Seed pre-existing physician and specialist
        self.physician = User.objects.create_user(
            email='dr.adeyemi@clinic.org',
            full_name='Dr. M. Adeyemi',
            role=Role.PRIMARY_PHYSICIAN,
            password='TestPassword123!'
        )
        self.specialist = User.objects.create_user(
            email='dr.ibrahim@clinic.org',
            full_name='Dr. K. Ibrahim',
            role=Role.SPECIALIST,
            password='TestPassword123!'
        )

    def test_signin_page_renders_demo_account_access_elements(self):
        """The login page must display one-click demo access with clear action buttons."""
        response = self.client.get(self.login_page_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Instant Evaluation Access')
        self.assertContains(response, 'Bypass All Registration')
        self.assertContains(response, 'btn-demo-primary')
        self.assertContains(response, 'btn-demo-specialist')
        self.assertContains(response, 'Demo Primary Physician')
        self.assertContains(response, 'Demo Specialist')

    def test_registration_page_renders_demo_bypass_callout(self):
        """The registration page must offer an instant demo login bypass link."""
        response = self.client.get(self.register_page_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.demo_login_url)
        self.assertContains(response, 'Instant Demo Login')

    def test_demo_login_as_primary_physician_post(self):
        """Clicking Demo Primary Physician logs in directly to dashboard, bypassing MFA setup."""
        response = self.client.post(self.demo_login_url, {'role': Role.PRIMARY_PHYSICIAN})
        self.assertRedirects(response, reverse('cases:dashboard'))

        # Session authenticated
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['_auth_user_id'], str(self.physician.id))

        # MFA session keys cleared
        self.assertNotIn('mfa_setup_user_id', self.client.session)
        self.assertNotIn('mfa_pending_user_id', self.client.session)

        # Audit event recorded
        audit_entry = AuditLog.objects.filter(
            action=AuditAction.LOGIN_SUCCESS,
            actor=self.physician
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.status, AuditStatus.ALLOWED)
        self.assertTrue(audit_entry.details.get('demo'))
        self.assertTrue(audit_entry.details.get('bypassed_registration'))

    def test_demo_login_as_specialist_post(self):
        """Clicking Demo Specialist logs in directly with Specialist role."""
        response = self.client.post(self.demo_login_url, {'role': Role.SPECIALIST})
        self.assertRedirects(response, reverse('cases:dashboard'))

        # Session authenticated as specialist
        self.assertEqual(self.client.session['_auth_user_id'], str(self.specialist.id))

        # Audit event recorded
        audit_entry = AuditLog.objects.filter(
            action=AuditAction.LOGIN_SUCCESS,
            actor=self.specialist
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.details.get('role'), Role.SPECIALIST)

    def test_demo_login_get_request(self):
        """Direct GET request to demo login defaults to primary physician and authenticates."""
        response = self.client.get(self.demo_login_url)
        self.assertRedirects(response, reverse('cases:dashboard'))
        self.assertEqual(self.client.session['_auth_user_id'], str(self.physician.id))

    def test_demo_login_preserves_safe_next_url(self):
        """Internal relative ?next= parameter is honored upon demo login."""
        response = self.client.post(self.demo_login_url, {'next': '/cases/create/'})
        self.assertRedirects(response, '/cases/create/')

    def test_demo_login_neutralizes_external_next_url(self):
        """External or protocol-relative ?next= parameter redirects safely to dashboard."""
        response = self.client.post(self.demo_login_url, {'next': 'https://evil-site.com/exploit'})
        self.assertRedirects(response, reverse('cases:dashboard'))

    def test_demo_login_auto_provisions_account_when_database_is_empty(self):
        """When no user exists in DB, demo login auto-provisions a valid demo user and succeeds."""
        User.objects.all().delete()
        self.assertEqual(User.objects.count(), 0)

        response = self.client.post(self.demo_login_url, {'role': Role.PRIMARY_PHYSICIAN})
        self.assertRedirects(response, reverse('cases:dashboard'))

        self.assertEqual(User.objects.count(), 1)
        created_user = User.objects.first()
        self.assertEqual(created_user.role, Role.PRIMARY_PHYSICIAN)
        self.assertEqual(self.client.session['_auth_user_id'], str(created_user.id))
