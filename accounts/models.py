import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.exceptions import ValidationError


class Role(models.TextChoices):
    PRIMARY_PHYSICIAN = 'PRIMARY_PHYSICIAN', 'Primary Physician'
    SPECIALIST = 'SPECIALIST', 'Specialist'


class UserManager(BaseUserManager):
    def create_user(self, email, full_name, role, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        if not full_name:
            raise ValueError('Full name is required')
        if role not in Role.values:
            raise ValueError(f'Invalid role: {role}. Must be PRIMARY_PHYSICIAN or SPECIALIST')
        
        email = self.normalize_email(email)
        user = self.model(email=email, full_name=full_name, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', Role.PRIMARY_PHYSICIAN)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
            
        return self.create_user(email, full_name, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    DOPA Custom User model with immutable role assignment.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True, max_length=254)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name', 'role']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    @property
    def is_primary_physician(self):
        return self.role == Role.PRIMARY_PHYSICIAN

    @property
    def is_specialist(self):
        return self.role == Role.SPECIALIST

    @property
    def has_mfa_enabled(self):
        return hasattr(self, 'mfa_device') and self.mfa_device.is_confirmed

    @property
    def requires_mfa(self):
        return self.role == Role.PRIMARY_PHYSICIAN

    def clean(self):
        super().clean()
        if self.pk:
            # Enforce Role Immutability (FR1, C-01)
            original = User.objects.filter(pk=self.pk).values('role').first()
            if original and original['role'] != self.role:
                raise ValidationError({'role': 'Role assignment is immutable and cannot be modified post-registration.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MFADevice(models.Model):
    """
    Time-Based One-Time Password (TOTP) Authenticator device (RFC 6238).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mfa_device'
    )
    secret_key = models.CharField(max_length=64)
    is_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'MFA Device'
        verbose_name_plural = 'MFA Devices'

    def __str__(self):
        status = "Active" if self.is_confirmed else "Pending Confirmation"
        return f"MFA Device for {self.user.email} ({status})"


class MFARecoveryCode(models.Model):
    """
    Single-use scratch recovery code. Stored as a salted PBKDF2 hash.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(
        MFADevice,
        on_delete=models.CASCADE,
        related_name='recovery_codes'
    )
    code_hash = models.CharField(max_length=255)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'MFA Recovery Code'
        verbose_name_plural = 'MFA Recovery Codes'
        ordering = ['created_at']

    def __str__(self):
        status = "Consumed" if self.is_used else "Available"
        return f"Recovery Code ({status}) for {self.device.user.email}"
