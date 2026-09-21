from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views import View
from django.contrib.auth import login, logout
from django.contrib import messages
from django.contrib.auth.views import (
    PasswordResetView as BasePasswordResetView,
    PasswordResetDoneView as BasePasswordResetDoneView,
    PasswordResetConfirmView as BasePasswordResetConfirmView,
    PasswordResetCompleteView as BasePasswordResetCompleteView,
)

from audit.services import log_event, get_client_ip
from audit.models import AuditAction, AuditStatus
from .forms import RegistrationForm, LoginForm
from .rate_limit import is_ip_rate_limited, record_failed_attempt, clear_failed_attempts


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
            
            # Log registration & initial login
            log_event(
                action=AuditAction.LOGIN_SUCCESS,
                actor=user,
                entity_type='accounts_user',
                entity_id=str(user.id),
                ip_address=ip,
                status=AuditStatus.ALLOWED,
                details={'event': 'user_registered', 'role': user.role}
            )
            
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
            login(request, user)
            
            log_event(
                action=AuditAction.LOGIN_SUCCESS,
                actor=user,
                entity_type='accounts_user',
                entity_id=str(user.id),
                ip_address=ip,
                status=AuditStatus.ALLOWED,
                details={'role': user.role}
            )
            
            next_url = request.GET.get('next') or request.POST.get('next')
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
        # Support safe GET redirect if accessed directly
        return self.post(request)


class PasswordResetView(BasePasswordResetView):
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.html'
    success_url = reverse_lazy('accounts:password_reset_done')


class PasswordResetDoneView(BasePasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class PasswordResetConfirmView(BasePasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')


class PasswordResetCompleteView(BasePasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'
