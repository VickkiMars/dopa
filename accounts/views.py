from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views import View
from django.utils import timezone
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.views import (
    PasswordResetView as BasePasswordResetView,
    PasswordResetDoneView as BasePasswordResetDoneView,
    PasswordResetConfirmView as BasePasswordResetConfirmView,
    PasswordResetCompleteView as BasePasswordResetCompleteView,
)

from audit.services import log_event, get_client_ip
from audit.models import AuditAction, AuditStatus
from .models import User, Role, MFADevice, MFARecoveryCode
from .forms import RegistrationForm, LoginForm
from .rate_limit import is_ip_rate_limited, record_failed_attempt, clear_failed_attempts
from .totp import (
    generate_secret,
    generate_totp,
    verify_totp,
    generate_recovery_codes,
    build_otpauth_uri,
    generate_qr_svg,
)


class RegisterView(View):
    template_name = 'accounts/register.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('cases:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = RegistrationForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            ip = get_client_ip(request)
            
            # Log registration
            log_event(
                action=AuditAction.LOGIN_SUCCESS,
                actor=user,
                entity_type='accounts_user',
                entity_id=str(user.id),
                ip_address=ip,
                status=AuditStatus.ALLOWED,
                details={'event': 'user_registered', 'role': user.role}
            )
            
            # Primary Physicians are required to complete MFA setup immediately
            if user.role == Role.PRIMARY_PHYSICIAN:
                request.session['mfa_setup_user_id'] = str(user.id)
                messages.info(
                    request,
                    f"Welcome, Dr. {user.full_name}! As a Primary Physician, clinical governance requires configuring Two-Factor Authentication before accessing patient cases."
                )
                return redirect('accounts:mfa_setup')

            # Specialists have optional MFA; log in directly
            login(request, user)
            messages.success(request, f"Welcome, {user.full_name}! Your account has been registered as {user.get_role_display()}.")
            return redirect('cases:dashboard')

        return render(request, self.template_name, {'form': form})


class LoginView(View):
    template_name = 'accounts/login.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('cases:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        form = LoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        ip = get_client_ip(request)
        
        # Check IP Rate Limiting (C-04)
        if is_ip_rate_limited(ip):
            log_event(
                action=AuditAction.LOGIN_FAILED,
                ip_address=ip,
                status=AuditStatus.DENIED,
                details={'reason': 'rate_limit_exceeded', 'ip': ip}
            )
            messages.error(request, "Too many failed login attempts from this network. Please wait 15 minutes before trying again.")
            return render(request, self.template_name, {'form': LoginForm(), 'rate_limited': True}, status=429)

        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.user
            clear_failed_attempts(ip)
            
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url and next_url.startswith('/'):
                request.session['mfa_next_url'] = next_url

            # 1. User has MFA confirmed -> Challenge with MFA
            if user.has_mfa_enabled:
                request.session['mfa_pending_user_id'] = str(user.id)
                return redirect('accounts:mfa_verify')

            # 2. Primary Physician without MFA -> Enforce setup
            if user.requires_mfa and not user.has_mfa_enabled:
                request.session['mfa_setup_user_id'] = str(user.id)
                messages.warning(
                    request,
                    "Primary Physician accounts require Multi-Factor Authentication. Please complete your authenticator setup."
                )
                return redirect('accounts:mfa_setup')

            # 3. Specialist without MFA -> Direct login
            login(request, user)
            log_event(
                action=AuditAction.LOGIN_SUCCESS,
                actor=user,
                entity_type='accounts_user',
                entity_id=str(user.id),
                ip_address=ip,
                status=AuditStatus.ALLOWED,
                details={'role': user.role, 'mfa_enabled': False}
            )
            
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('cases:dashboard')

        # Failed attempt
        attempts = record_failed_attempt(ip)
        attempted_email = request.POST.get('email', '').strip()
        log_event(
            action=AuditAction.LOGIN_FAILED,
            ip_address=ip,
            status=AuditStatus.DENIED,
            details={'attempted_email': attempted_email, 'attempts_count': attempts}
        )
        return render(request, self.template_name, {'form': form})


class MFASetupView(View):
    template_name = 'accounts/mfa_setup.html'

    def get_target_user(self, request):
        if request.user.is_authenticated:
            return request.user
        user_id = request.session.get('mfa_setup_user_id')
        if user_id:
            try:
                return User.objects.get(id=user_id, is_active=True)
            except User.DoesNotExist:
                return None
        return None

    def get(self, request):
        user = self.get_target_user(request)
        if not user:
            return redirect('accounts:login')

        secret_key = generate_secret()
        secret_key_display = ' '.join(secret_key[i:i + 4] for i in range(0, len(secret_key), 4))
        recovery_codes = generate_recovery_codes(8)
        
        otp_uri = build_otpauth_uri(user.email, secret_key, issuer="DOPA")
        qr_svg = generate_qr_svg(otp_uri)

        return render(request, self.template_name, {
            'user': user,
            'secret_key': secret_key,
            'secret_key_display': secret_key_display,
            'recovery_codes': recovery_codes,
            'qr_svg': qr_svg,
            'is_enforced': user.requires_mfa,
        })

    def post(self, request):
        user = self.get_target_user(request)
        if not user:
            return redirect('accounts:login')

        secret_key = request.POST.get('secret_key', '').strip()
        token = request.POST.get('token', '').strip()
        recovery_codes = request.POST.getlist('recovery_codes')

        if not verify_totp(token, secret_key):
            secret_key_display = ' '.join(secret_key[i:i + 4] for i in range(0, len(secret_key), 4))
            otp_uri = build_otpauth_uri(user.email, secret_key, issuer="DOPA")
            qr_svg = generate_qr_svg(otp_uri)

            return render(request, self.template_name, {
                'user': user,
                'secret_key': secret_key,
                'secret_key_display': secret_key_display,
                'recovery_codes': recovery_codes,
                'qr_svg': qr_svg,
                'is_enforced': user.requires_mfa,
                'error_message': 'Invalid 6-digit confirmation code. Please ensure your device clock is synchronized and enter the current code from your authenticator app.',
            }, status=400)

        # Token valid: persist device and hashed recovery codes
        device, _ = MFADevice.objects.update_or_create(
            user=user,
            defaults={
                'secret_key': secret_key,
                'is_confirmed': True,
                'last_used_at': timezone.now()
            }
        )

        # Clear existing recovery codes if re-configuring
        device.recovery_codes.all().delete()
        for raw_code in recovery_codes:
            code_clean = raw_code.strip().upper()
            if code_clean:
                MFARecoveryCode.objects.create(
                    device=device,
                    code_hash=make_password(code_clean)
                )

        ip = get_client_ip(request)
        log_event(
            action=AuditAction.MFA_SETUP,
            actor=user,
            entity_type='accounts_mfadevice',
            entity_id=str(device.id),
            ip_address=ip,
            status=AuditStatus.ALLOWED,
            details={'role': user.role, 'codes_count': len(recovery_codes)}
        )

        # If user completed setup via pending session, log them in
        if not request.user.is_authenticated:
            login(request, user)
            request.session.pop('mfa_setup_user_id', None)

        messages.success(request, "Two-Factor Authentication has been successfully activated for your account.")
        next_url = request.session.pop('mfa_next_url', None)
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('cases:dashboard')


class MFAVerifyView(View):
    template_name = 'accounts/mfa_verify.html'

    def get_pending_user(self, request):
        user_id = request.session.get('mfa_pending_user_id')
        if not user_id:
            return None
        try:
            return User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            return None

    def get(self, request):
        user = self.get_pending_user(request)
        if not user:
            return redirect('accounts:login')
        return render(request, self.template_name, {'user': user, 'initial_mode': 'totp'})

    def post(self, request):
        user = self.get_pending_user(request)
        if not user:
            return redirect('accounts:login')

        ip = get_client_ip(request)
        if is_ip_rate_limited(ip):
            log_event(
                action=AuditAction.MFA_FAILED,
                actor=user,
                ip_address=ip,
                status=AuditStatus.DENIED,
                details={'reason': 'rate_limit_exceeded'}
            )
            return render(request, self.template_name, {
                'user': user,
                'error_message': 'Too many failed verification attempts. Please wait 15 minutes before trying again.'
            }, status=429)

        mode = request.POST.get('mode', 'totp')
        device = getattr(user, 'mfa_device', None)

        if not device or not device.is_confirmed:
            return redirect('accounts:login')

        # Mode A: 6-digit TOTP Token
        if mode == 'totp':
            totp_code = request.POST.get('totp_code', '').strip()
            if verify_totp(totp_code, device.secret_key):
                clear_failed_attempts(ip)
                device.last_used_at = timezone.now()
                device.save(update_fields=['last_used_at'])

                login(request, user)
                request.session.pop('mfa_pending_user_id', None)

                log_event(
                    action=AuditAction.MFA_VERIFIED,
                    actor=user,
                    entity_type='accounts_mfadevice',
                    entity_id=str(device.id),
                    ip_address=ip,
                    status=AuditStatus.ALLOWED,
                    details={'method': 'totp'}
                )
                log_event(
                    action=AuditAction.LOGIN_SUCCESS,
                    actor=user,
                    entity_type='accounts_user',
                    entity_id=str(user.id),
                    ip_address=ip,
                    status=AuditStatus.ALLOWED,
                    details={'role': user.role, 'mfa_method': 'totp'}
                )

                next_url = request.session.pop('mfa_next_url', None)
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)
                return redirect('cases:dashboard')

            # Failed TOTP
            attempts = record_failed_attempt(ip)
            log_event(
                action=AuditAction.MFA_FAILED,
                actor=user,
                entity_type='accounts_mfadevice',
                entity_id=str(device.id),
                ip_address=ip,
                status=AuditStatus.DENIED,
                details={'reason': 'invalid_totp_token', 'attempts_count': attempts}
            )
            return render(request, self.template_name, {
                'user': user,
                'initial_mode': 'totp',
                'error_message': 'Invalid 6-digit verification code. Please check your authenticator app.'
            }, status=400)

        # Mode B: Single-Use Scratch Recovery Code
        elif mode == 'recovery':
            recovery_code = request.POST.get('recovery_code', '').strip().upper()
            matched_code = None
            
            for rc in device.recovery_codes.filter(is_used=False):
                if check_password(recovery_code, rc.code_hash):
                    matched_code = rc
                    break

            if matched_code:
                matched_code.is_used = True
                matched_code.used_at = timezone.now()
                matched_code.save(update_fields=['is_used', 'used_at'])

                clear_failed_attempts(ip)
                device.last_used_at = timezone.now()
                device.save(update_fields=['last_used_at'])

                login(request, user)
                request.session.pop('mfa_pending_user_id', None)

                remaining = device.recovery_codes.filter(is_used=False).count()
                log_event(
                    action=AuditAction.MFA_RECOVERY_USED,
                    actor=user,
                    entity_type='accounts_mfarecoverycode',
                    entity_id=str(matched_code.id),
                    ip_address=ip,
                    status=AuditStatus.ALLOWED,
                    details={'remaining_codes': remaining}
                )
                log_event(
                    action=AuditAction.LOGIN_SUCCESS,
                    actor=user,
                    entity_type='accounts_user',
                    entity_id=str(user.id),
                    ip_address=ip,
                    status=AuditStatus.ALLOWED,
                    details={'role': user.role, 'mfa_method': 'recovery_code'}
                )

                messages.warning(
                    request,
                    f"Signed in using scratch recovery code. You have {remaining} single-use recovery codes remaining."
                )

                next_url = request.session.pop('mfa_next_url', None)
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)
                return redirect('cases:dashboard')

            # Failed Recovery Code
            attempts = record_failed_attempt(ip)
            log_event(
                action=AuditAction.MFA_FAILED,
                actor=user,
                entity_type='accounts_mfadevice',
                entity_id=str(device.id),
                ip_address=ip,
                status=AuditStatus.DENIED,
                details={'reason': 'invalid_or_consumed_recovery_code', 'attempts_count': attempts}
            )
            return render(request, self.template_name, {
                'user': user,
                'initial_mode': 'recovery',
                'error_message': 'Invalid or previously used recovery code. Please enter an unused code.'
            }, status=400)

        return redirect('accounts:login')


class MFASettingsView(View):
    template_name = 'accounts/mfa_settings.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse_lazy('accounts:login')}?next={request.path}")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        user = request.user
        device = getattr(user, 'mfa_device', None)
        total_codes = 0
        available_codes = 0
        if device and device.is_confirmed:
            total_codes = device.recovery_codes.count()
            available_codes = device.recovery_codes.filter(is_used=False).count()

        return render(request, self.template_name, {
            'user': user,
            'total_codes_count': total_codes,
            'available_codes_count': available_codes,
        })

    def post(self, request):
        user = request.user
        action = request.POST.get('action')

        if action == 'disable':
            if not user.is_specialist:
                raise PermissionDenied("Primary Physicians are required by clinical governance to maintain MFA.")

            password = request.POST.get('password', '')
            totp_token = request.POST.get('totp_token', '').strip().upper()

            if not user.check_password(password):
                messages.error(request, "Incorrect account password.")
                return redirect('accounts:mfa_settings')

            device = getattr(user, 'mfa_device', None)
            if not device or not device.is_confirmed:
                messages.error(request, "No active MFA device found.")
                return redirect('accounts:mfa_settings')

            # Verify either current TOTP or a valid recovery code
            valid = verify_totp(totp_token, device.secret_key)
            if not valid:
                for rc in device.recovery_codes.filter(is_used=False):
                    if check_password(totp_token, rc.code_hash):
                        valid = True
                        break

            if not valid:
                messages.error(request, "Invalid authenticator code or recovery code.")
                return redirect('accounts:mfa_settings')

            device.delete()
            log_event(
                action=AuditAction.MFA_DISABLED,
                actor=user,
                entity_type='accounts_user',
                entity_id=str(user.id),
                ip_address=get_client_ip(request),
                status=AuditStatus.ALLOWED,
                details={'role': user.role}
            )
            messages.info(request, "Two-Factor Authentication has been disabled for your account.")
            return redirect('accounts:mfa_settings')

        return redirect('accounts:mfa_settings')


class LogoutView(View):
    def post(self, request):
        if request.user.is_authenticated:
            log_event(
                action=AuditAction.LOGOUT,
                actor=request.user,
                request=request,
                status=AuditStatus.ALLOWED
            )
            logout(request)
        messages.info(request, "You have been securely logged out.")
        return redirect('accounts:login')

    def get(self, request):
        return self.post(request)


class PasswordResetView(BasePasswordResetView):
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')


class PasswordResetDoneView(BasePasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class PasswordResetConfirmView(BasePasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')


class PasswordResetCompleteView(BasePasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'


class DemoLoginView(View):
    """
    Bypasses standard registration and credential entry to immediately log in as a demo clinician.
    Supports both Primary Physician and Specialist roles with pre-seeded clinical cases.
    """
    def get(self, request):
        return self._login_demo(request)

    def post(self, request):
        return self._login_demo(request)

    def _login_demo(self, request):
        role_param = (request.POST.get('role') or request.GET.get('role') or Role.PRIMARY_PHYSICIAN).strip().upper()
        if role_param not in Role.values:
            role_param = Role.PRIMARY_PHYSICIAN

        user = None
        # Preferred demo accounts with pre-seeded cases and collaboration records
        if role_param == Role.PRIMARY_PHYSICIAN:
            preferred_emails = [
                'dr.adeyemi@clinic.org',
                'dr.danjuma@clinic.org',
                'dr.bassey@clinic.org',
                'demo.physician@dopa.clinic'
            ]
        else:
            preferred_emails = [
                'dr.ibrahim@clinic.org',
                'dr.okafor@clinic.org',
                'dr.bello@clinic.org',
                'demo.specialist@dopa.clinic'
            ]

        for email in preferred_emails:
            user = User.objects.filter(email=email, role=role_param, is_active=True).first()
            if user:
                break

        # Fallback to any active user matching the role
        if not user:
            user = User.objects.filter(role=role_param, is_active=True).first()

        # If no user exists at all, auto-provision a demo clinician account
        if not user:
            if role_param == Role.PRIMARY_PHYSICIAN:
                email = 'demo.physician@dopa.clinic'
                full_name = 'Dr. Alex Morgan (Demo Primary Physician)'
            else:
                email = 'demo.specialist@dopa.clinic'
                full_name = 'Dr. Sarah Chen (Demo Specialist)'

            user = User.objects.create_user(
                email=email,
                full_name=full_name,
                role=role_param,
                password='DemoPassword123!'
            )

        # Ensure user is active
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])

        # Auto-seed synthetic clinical scenarios if database has no cases
        from cases.models import Case
        if Case.objects.count() == 0:
            from django.core.management import call_command
            try:
                call_command('seed_clinical_cases')
                re_user = User.objects.filter(email=user.email, role=role_param, is_active=True).first()
                if re_user:
                    user = re_user
            except Exception:
                pass

        # Clear any pending MFA challenges and auth session residue
        request.session.pop('mfa_pending_user_id', None)
        request.session.pop('mfa_setup_user_id', None)
        request.session.pop('mfa_next_url', None)

        # Explicitly bind backend and authenticate session
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        request.session.modified = True
        request.session.save()

        ip = get_client_ip(request)
        log_event(
            action=AuditAction.LOGIN_SUCCESS,
            actor=user,
            entity_type='accounts_user',
            entity_id=str(user.id),
            ip_address=ip,
            status=AuditStatus.ALLOWED,
            details={
                'event': 'demo_login_bypass',
                'role': user.role,
                'demo': True,
                'bypassed_registration': True,
                'bypassed_mfa': True
            }
        )

        messages.success(
            request,
            f"⚡ Demo Mode: Signed in as {user.full_name} ({user.get_role_display()}). Registration and MFA checks bypassed."
        )

        # Sanitize next_url to ensure it never redirects back to login/auth pages
        raw_next = (request.POST.get('next') or request.GET.get('next') or '').strip()
        if (
            raw_next
            and raw_next.startswith('/')
            and not raw_next.startswith('//')
            and not raw_next.startswith('/accounts/')
            and raw_next != '/'
        ):
            return redirect(raw_next)

        return redirect('cases:dashboard')


