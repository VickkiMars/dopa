import time
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from accounts.models import User, Role, MFADevice, MFARecoveryCode
from accounts.totp import (
    generate_secret,
    generate_totp,
    verify_totp,
    generate_recovery_codes,
    build_otpauth_uri,
    generate_qr_svg,
)
from audit.models import AuditLog, AuditAction, AuditStatus


class TOTPCoreEngineTests(TestCase):
    """
    Unit tests for the pure-Python RFC 6238 TOTP calculation and SVG QR generation.
    """

    def setUp(self):
        self.secret = generate_secret()

    def test_generate_secret_format(self):
        """Secret must be a non-empty alphanumeric Base32 string."""
        self.assertTrue(len(self.secret) >= 24)
        # Should be uppercase alphanumeric (Base32 alphabet)
        self.assertTrue(self.secret.isalnum())
        self.assertEqual(self.secret, self.secret.upper())

    def test_generate_totp_rfc6238_vector(self):
        """Calculated TOTP must be a 6-digit numeric string."""
        token = generate_totp(self.secret)
        self.assertEqual(len(token), 6)
        self.assertTrue(token.isdigit())

    def test_verify_totp_current_and_drift_window(self):
        """verify_totp accepts tokens at current timestamp and within +/- 1 step."""
        now = time.time()
        current_token = generate_totp(self.secret, timestamp=now)
        past_token = generate_totp(self.secret, timestamp=now - 30)
        future_token = generate_totp(self.secret, timestamp=now + 30)
        far_past_token = generate_totp(self.secret, timestamp=now - 90)

        # Current token
        self.assertTrue(verify_totp(current_token, self.secret, timestamp=now))
        # Within window
        self.assertTrue(verify_totp(past_token, self.secret, window=1, timestamp=now))
        self.assertTrue(verify_totp(future_token, self.secret, window=1, timestamp=now))
        # Outside window
        self.assertFalse(verify_totp(far_past_token, self.secret, window=1, timestamp=now))

    def test_verify_totp_rejections(self):
        """Rejects non-numeric, wrong length, empty, or mismatched tokens."""
        self.assertFalse(verify_totp('12345', self.secret))
        self.assertFalse(verify_totp('1234567', self.secret))
        self.assertFalse(verify_totp('abcdef', self.secret))
        self.assertFalse(verify_totp('', self.secret))
        self.assertFalse(verify_totp('000000', self.secret))
        self.assertFalse(verify_totp('123456', 'INVALID_KEY'))

    def test_generate_recovery_codes_format(self):
        """8 recovery codes generated, formatted as XXXX-XXXX, without ambiguous characters."""
        codes = generate_recovery_codes(8)
        self.assertEqual(len(codes), 8)
        self.assertEqual(len(set(codes)), 8)  # All distinct
        for code in codes:
            self.assertEqual(len(code), 9)
            self.assertEqual(code[4], '-')
            part1, part2 = code.split('-')
            self.assertEqual(len(part1), 4)
            self.assertEqual(len(part2), 4)
            # Ensure no ambiguous characters
            for char in '0O1Il':
                self.assertNotIn(char, code)

    def test_build_otpauth_uri(self):
        """Generates valid RFC-compliant otpauth URI."""
        uri = build_otpauth_uri('test.doctor@hospital.org', self.secret, issuer="DOPA")
        self.assertTrue(uri.startswith('otpauth://totp/DOPA%3Atest.doctor%40hospital.org?'))
        self.assertIn(f'secret={self.secret}', uri)
        self.assertIn('issuer=DOPA', uri)
        self.assertIn('algorithm=SHA1', uri)
        self.assertIn('digits=6', uri)

    def test_generate_qr_svg(self):
        """Generates valid standalone SVG markup containing XML namespaces and path."""
        uri = build_otpauth_uri('test@hospital.org', self.secret)
        svg = generate_qr_svg(uri)
        self.assertTrue(svg.startswith('<svg'))
        self.assertTrue(svg.endswith('</svg>'))
        self.assertIn('xmlns="http://www.w3.org/2000/svg"', svg)
        self.assertIn('<rect', svg)
        self.assertIn('<path', svg)


class MFAOnboardingAndPolicyTests(TestCase):
    """
    Tests for governance enforcement: Primary Physicians mandatory, Specialists optional.
    """

    def setUp(self):
        self.client = Client()
        cache.clear()
        self.login_url = reverse('accounts:login')
        self.register_url = reverse('accounts:register')

    def test_primary_physician_registration_redirects_to_mfa_setup(self):
        """Newly registered Primary Physician is routed to mandatory MFA setup."""
        payload = {
            'full_name': 'Dr. Marcus Vance',
            'email': 'marcus.vance@hospital.org',
            'role': Role.PRIMARY_PHYSICIAN,
            'password': 'SecurePassword123!',
            'password_confirm': 'SecurePassword123!'
        }
        response = self.client.post(self.register_url, payload)
        self.assertRedirects(response, reverse('accounts:mfa_setup'))
        
        # User created in DB and marked requiring MFA
        user = User.objects.get(email='marcus.vance@hospital.org')
        self.assertTrue(user.requires_mfa)
        self.assertFalse(user.has_mfa_enabled)
        self.assertEqual(self.client.session.get('mfa_setup_user_id'), str(user.id))

    def test_specialist_registration_direct_login(self):
        """Specialist registration completes with direct dashboard login without mandatory MFA."""
        payload = {
            'full_name': 'Dr. Elena Rostova',
            'email': 'elena.rostova@hospital.org',
            'role': Role.SPECIALIST,
            'password': 'SecurePassword123!',
            'password_confirm': 'SecurePassword123!'
        }
        response = self.client.post(self.register_url, payload)
        self.assertRedirects(response, reverse('cases:dashboard'))
        
        user = User.objects.get(email='elena.rostova@hospital.org')
        self.assertFalse(user.requires_mfa)
        self.assertFalse(user.has_mfa_enabled)
        self.assertIn('_auth_user_id', self.client.session)

    def test_unenrolled_primary_physician_login_enforces_setup(self):
        """Existing Primary Physician without MFA is intercepted at login and sent to setup."""
        user = User.objects.create_user(
            email='physician.unenrolled@hospital.org',
            full_name='Dr. Unenrolled',
            role=Role.PRIMARY_PHYSICIAN,
            password='ValidPassword123!'
        )
        response = self.client.post(self.login_url, {
            'email': user.email,
            'password': 'ValidPassword123!'
        })
        self.assertRedirects(response, reverse('accounts:mfa_setup'))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session.get('mfa_setup_user_id'), str(user.id))

    def test_primary_physician_cannot_disable_mfa(self):
        """Primary Physicians are barred by clinical governance from disabling MFA."""
        user = User.objects.create_user(
            email='physician.governance@hospital.org',
            full_name='Dr. Governance',
            role=Role.PRIMARY_PHYSICIAN,
            password='ValidPassword123!'
        )
        device = MFADevice.objects.create(
            user=user,
            secret_key=generate_secret(),
            is_confirmed=True
        )
        self.client.force_login(user)

        response = self.client.post(reverse('accounts:mfa_settings'), {'action': 'disable'})
        # Should return 403 Forbidden due to PermissionDenied
        self.assertEqual(response.status_code, 403)
        self.assertTrue(MFADevice.objects.filter(id=device.id).exists())


class MFASetupAndVerificationFlowTests(TestCase):
    """
    End-to-end tests for MFA setup, 2-step TOTP login, scratch code recovery, and rate limiting.
    """

    def setUp(self):
        self.client = Client()
        cache.clear()
        self.login_url = reverse('accounts:login')
        self.verify_url = reverse('accounts:mfa_verify')
        self.setup_url = reverse('accounts:mfa_setup')

        self.physician = User.objects.create_user(
            email='dr.sarah@hospital.org',
            full_name='Dr. Sarah Chen',
            role=Role.PRIMARY_PHYSICIAN,
            password='ValidPassword123!'
        )

    def test_mfa_setup_flow_with_valid_token(self):
        """Clinician completes setup by submitting secret and valid confirmation token."""
        # Initiate setup session
        s = self.client.session
        s['mfa_setup_user_id'] = str(self.physician.id)
        s.save()

        get_res = self.client.get(self.setup_url)
        self.assertEqual(get_res.status_code, 200)
        self.assertContains(get_res, 'Set Up Two-Factor Authentication')
        self.assertContains(get_res, 'Save Your Scratch Recovery Codes')

        secret = generate_secret()
        valid_token = generate_totp(secret)
        raw_codes = ['ABCD-1234', 'EFGH-5678', 'JKLM-9012']

        payload = {
            'secret_key': secret,
            'token': valid_token,
            'recovery_codes': raw_codes
        }
        post_res = self.client.post(self.setup_url, payload)
        self.assertRedirects(post_res, reverse('cases:dashboard'))

        # Device is confirmed
        self.physician.refresh_from_db()
        self.assertTrue(self.physician.has_mfa_enabled)
        device = self.physician.mfa_device
        self.assertTrue(device.is_confirmed)
        self.assertEqual(device.secret_key, secret)

        # Recovery codes hashed in DB (not plaintext)
        self.assertEqual(device.recovery_codes.count(), 3)
        for rc, raw in zip(device.recovery_codes.all(), raw_codes):
            self.assertNotEqual(rc.code_hash, raw)
            self.assertTrue(check_password(raw, rc.code_hash))

        # Audit log verified
        audit = AuditLog.objects.filter(action=AuditAction.MFA_SETUP, actor=self.physician).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.status, AuditStatus.ALLOWED)

    def test_mfa_setup_with_invalid_token_rejected(self):
        """Submitting an invalid token during setup leaves device unconfirmed."""
        s = self.client.session
        s['mfa_setup_user_id'] = str(self.physician.id)
        s.save()

        secret = generate_secret()
        payload = {
            'secret_key': secret,
            'token': '000000',
            'recovery_codes': ['TEST-1234']
        }
        response = self.client.post(self.setup_url, payload)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Invalid 6-digit confirmation code', status_code=400)
        self.assertFalse(self.physician.has_mfa_enabled)

    def test_mfa_login_two_step_challenge_and_totp_success(self):
        """Password verification triggers MFA challenge, and valid TOTP completes login."""
        secret = generate_secret()
        device = MFADevice.objects.create(
            user=self.physician,
            secret_key=secret,
            is_confirmed=True
        )

        # Step 1: Password entry
        res1 = self.client.post(self.login_url, {
            'email': self.physician.email,
            'password': 'ValidPassword123!'
        })
        self.assertRedirects(res1, self.verify_url)
        # Not yet authenticated
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session.get('mfa_pending_user_id'), str(self.physician.id))

        # Direct access to dashboard before MFA verification must fail
        dash_res = self.client.get(reverse('cases:dashboard'))
        self.assertRedirects(dash_res, f"{reverse('accounts:login')}?next=/dashboard/")

        # Step 2: Valid TOTP token entry
        valid_totp = generate_totp(secret)
        res2 = self.client.post(self.verify_url, {
            'mode': 'totp',
            'totp_code': valid_totp
        })
        self.assertRedirects(res2, reverse('cases:dashboard'))

        # Session fully established
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['_auth_user_id'], str(self.physician.id))
        self.assertNotIn('mfa_pending_user_id', self.client.session)

        # Device last_used_at updated
        device.refresh_from_db()
        self.assertIsNotNone(device.last_used_at)

        # Audit logs recorded
        mfa_audit = AuditLog.objects.filter(action=AuditAction.MFA_VERIFIED, actor=self.physician).first()
        self.assertIsNotNone(mfa_audit)
        login_audit = AuditLog.objects.filter(action=AuditAction.LOGIN_SUCCESS, actor=self.physician).first()
        self.assertIsNotNone(login_audit)
        self.assertEqual(login_audit.details.get('mfa_method'), 'totp')

    def test_mfa_login_invalid_totp_rejected_and_audited(self):
        """Invalid TOTP code is rejected and logged as MFA_FAILED."""
        MFADevice.objects.create(
            user=self.physician,
            secret_key=generate_secret(),
            is_confirmed=True
        )
        s = self.client.session
        s['mfa_pending_user_id'] = str(self.physician.id)
        s.save()

        response = self.client.post(self.verify_url, {
            'mode': 'totp',
            'totp_code': '999999'
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Invalid 6-digit verification code', status_code=400)
        self.assertNotIn('_auth_user_id', self.client.session)

        failed_audit = AuditLog.objects.filter(action=AuditAction.MFA_FAILED, actor=self.physician).first()
        self.assertIsNotNone(failed_audit)
        self.assertEqual(failed_audit.status, AuditStatus.DENIED)

    def test_mfa_login_with_scratch_recovery_code(self):
        """Clinician can authenticate using a single-use scratch recovery code."""
        device = MFADevice.objects.create(
            user=self.physician,
            secret_key=generate_secret(),
            is_confirmed=True
        )
        raw_code = 'RECO-7788'
        rec_code = MFARecoveryCode.objects.create(
            device=device,
            code_hash=make_password(raw_code),
            is_used=False
        )

        s = self.client.session
        s['mfa_pending_user_id'] = str(self.physician.id)
        s.save()

        response = self.client.post(self.verify_url, {
            'mode': 'recovery',
            'recovery_code': raw_code
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertContains(response, 'Signed in using scratch recovery code')

        # Code marked consumed
        rec_code.refresh_from_db()
        self.assertTrue(rec_code.is_used)
        self.assertIsNotNone(rec_code.used_at)

        # Audit recorded
        audit = AuditLog.objects.filter(action=AuditAction.MFA_RECOVERY_USED, actor=self.physician).first()
        self.assertIsNotNone(audit)

    def test_reused_scratch_recovery_code_fails(self):
        """Already-consumed scratch recovery code cannot be reused."""
        device = MFADevice.objects.create(
            user=self.physician,
            secret_key=generate_secret(),
            is_confirmed=True
        )
        raw_code = 'USED-9999'
        MFARecoveryCode.objects.create(
            device=device,
            code_hash=make_password(raw_code),
            is_used=True,
            used_at=timezone.now()
        )

        s = self.client.session
        s['mfa_pending_user_id'] = str(self.physician.id)
        s.save()

        response = self.client.post(self.verify_url, {
            'mode': 'recovery',
            'recovery_code': raw_code
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Invalid or previously used recovery code', status_code=400)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_specialist_can_setup_and_disable_mfa(self):
        """Specialist can optionally enable MFA and later voluntarily disable it."""
        specialist = User.objects.create_user(
            email='dr.specialist.optin@hospital.org',
            full_name='Dr. Optin Specialist',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )
        self.client.force_login(specialist)

        # Specialist sets up device
        secret = generate_secret()
        token = generate_totp(secret)
        setup_res = self.client.post(self.setup_url, {
            'secret_key': secret,
            'token': token,
            'recovery_codes': ['SPEC-1111']
        })
        self.assertRedirects(setup_res, reverse('cases:dashboard'))
        specialist.refresh_from_db()
        self.assertTrue(specialist.has_mfa_enabled)

        # Specialist disables MFA with valid password and TOTP
        disable_token = generate_totp(secret)
        disable_res = self.client.post(reverse('accounts:mfa_settings'), {
            'action': 'disable',
            'password': 'ValidPassword123!',
            'totp_token': disable_token
        })
        self.assertRedirects(disable_res, reverse('accounts:mfa_settings'))
        specialist.refresh_from_db()
        self.assertFalse(specialist.has_mfa_enabled)

        # Audit log written
        disable_audit = AuditLog.objects.filter(action=AuditAction.MFA_DISABLED, actor=specialist).first()
        self.assertIsNotNone(disable_audit)

    def test_mfa_anonymous_access_redirects(self):
        """Anonymous access to MFA endpoints redirects to login."""
        self.client.logout()
        res_setup = self.client.get(self.setup_url)
        self.assertRedirects(res_setup, self.login_url)

        res_verify = self.client.get(self.verify_url)
        self.assertRedirects(res_verify, self.login_url)

        res_settings = self.client.get(reverse('accounts:mfa_settings'))
        self.assertRedirects(res_settings, f"{self.login_url}?next={reverse('accounts:mfa_settings')}")

    def test_mfa_settings_disable_failures(self):
        """Disabling MFA fails with incorrect password or wrong TOTP code."""
        specialist = User.objects.create_user(
            email='dr.fail.disable@hospital.org',
            full_name='Dr. Fail Disable',
            role=Role.SPECIALIST,
            password='ValidPassword123!'
        )
        MFADevice.objects.create(
            user=specialist,
            secret_key=generate_secret(),
            is_confirmed=True
        )
        self.client.force_login(specialist)

        # Wrong password
        res1 = self.client.post(reverse('accounts:mfa_settings'), {
            'action': 'disable',
            'password': 'WrongPassword!',
            'totp_token': '123456'
        }, follow=True)
        self.assertContains(res1, 'Incorrect account password')
        self.assertTrue(specialist.has_mfa_enabled)

        # Wrong TOTP
        res2 = self.client.post(reverse('accounts:mfa_settings'), {
            'action': 'disable',
            'password': 'ValidPassword123!',
            'totp_token': '000000'
        }, follow=True)
        self.assertContains(res2, 'Invalid authenticator code')
        self.assertTrue(specialist.has_mfa_enabled)

        # Unknown action redirects safely
        res3 = self.client.post(reverse('accounts:mfa_settings'), {'action': 'unknown'})
        self.assertRedirects(res3, reverse('accounts:mfa_settings'))

    def test_mfa_models_str_representations(self):
        """String representations of MFADevice and MFARecoveryCode reflect confirmation/consumption."""
        device = MFADevice.objects.create(
            user=self.physician,
            secret_key=generate_secret(),
            is_confirmed=False
        )
        self.assertIn('Pending Confirmation', str(device))
        device.is_confirmed = True
        device.save()
        self.assertIn('Active', str(device))

        rec = MFARecoveryCode.objects.create(
            device=device,
            code_hash=make_password('CODE-1234'),
            is_used=False
        )
        self.assertIn('Available', str(rec))
        rec.is_used = True
        rec.save()
        self.assertIn('Consumed', str(rec))

    def test_mfa_verify_ip_rate_limiting(self):
        """MFA verify view blocks with 429 when IP rate limit is exceeded."""
        MFADevice.objects.create(
            user=self.physician,
            secret_key=generate_secret(),
            is_confirmed=True
        )
        s = self.client.session
        s['mfa_pending_user_id'] = str(self.physician.id)
        s.save()

        ip = '198.51.100.99'
        # Exhaust rate limit (5 attempts)
        for _ in range(5):
            self.client.post(self.verify_url, {
                'mode': 'totp',
                'totp_code': '000000'
            }, REMOTE_ADDR=ip)

        # 6th attempt must be throttled
        response = self.client.post(self.verify_url, {
            'mode': 'totp',
            'totp_code': '000000'
        }, REMOTE_ADDR=ip)
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, 'Too many failed verification attempts', status_code=429)
