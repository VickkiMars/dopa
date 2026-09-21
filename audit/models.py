import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class AuditAction(models.TextChoices):
    LOGIN_SUCCESS = 'LOGIN_SUCCESS', 'Login Success'
    LOGIN_FAILED = 'LOGIN_FAILED', 'Login Failed'
    LOGOUT = 'LOGOUT', 'Logout'
    CASE_CREATED = 'CASE_CREATED', 'Case Created'
    SPECIALIST_ADMITTED = 'SPECIALIST_ADMITTED', 'Specialist Admitted'
    HYPOTHESIS_SUBMITTED = 'HYPOTHESIS_SUBMITTED', 'Hypothesis Submitted'
    HYPOTHESIS_WITHDRAWN = 'HYPOTHESIS_WITHDRAWN', 'Hypothesis Withdrawn'
    DISCUSSION_POSTED = 'DISCUSSION_POSTED', 'Discussion Posted'
    RANK_UPDATED = 'RANK_UPDATED', 'Rank Updated'
    DECISION_RECORDED = 'DECISION_RECORDED', 'Decision Recorded'
    ATTACHMENT_UPLOADED = 'ATTACHMENT_UPLOADED', 'Attachment Uploaded'
    ATTACHMENT_ACCESSED = 'ATTACHMENT_ACCESSED', 'Attachment Accessed'
    ACCESS_DENIED = 'ACCESS_DENIED', 'Access Denied'


class AuditStatus(models.TextChoices):
    ALLOWED = 'ALLOWED', 'Allowed'
    DENIED = 'DENIED', 'Denied'


class AuditLog(models.Model):
    """
    Append-only forensic audit trail (FR7, NFR8).
    Ordinary users have zero permission to update or delete rows.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_entries'
    )
    action = models.CharField(max_length=50, choices=AuditAction.choices)
    entity_type = models.CharField(max_length=50, blank=True, default='')
    entity_id = models.CharField(max_length=100, blank=True, default='')
    case_id = models.UUIDField(null=True, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=AuditStatus.choices, default=AuditStatus.ALLOWED)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Audit Log Entry'
        verbose_name_plural = 'Audit Log Entries'
        ordering = ['-timestamp']

    def __str__(self):
        actor_name = self.actor.full_name if self.actor else 'Anonymous'
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}] {self.action} by {actor_name} ({self.status})"

    def clean(self):
        super().clean()
        if self.pk:
            original = AuditLog.objects.filter(pk=self.pk).exists()
            if original:
                raise ValidationError("Audit log records are immutable and append-only.")

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit log records are immutable and append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit log records cannot be deleted.")
