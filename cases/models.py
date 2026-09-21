import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class CaseStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
    DECIDED = 'DECIDED', 'Decided'
    CLOSED = 'CLOSED', 'Closed'


class Case(models.Model):
    """
    Primary clinical case record owned by a Primary Physician (FR2, C-13).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='owned_cases'
    )
    title = models.CharField(max_length=200)
    clinical_summary = models.TextField(help_text="Chief complaint and presenting clinical overview.")
    history = models.TextField(help_text="Past medical, surgical, family, and social history.")
    findings = models.TextField(help_text="Vital signs, physical exam, lab values, and diagnostic findings.")
    status = models.CharField(
        max_length=20,
        choices=CaseStatus.choices,
        default=CaseStatus.OPEN,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Clinical Case'
        verbose_name_plural = 'Clinical Cases'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} [{self.get_status_display()}] (Owner: {self.owner.full_name})"

    @property
    def is_open(self):
        return self.status == CaseStatus.OPEN

    @property
    def is_under_review(self):
        return self.status == CaseStatus.UNDER_REVIEW

    @property
    def is_decided(self):
        return self.status == CaseStatus.DECIDED

    @property
    def is_closed(self):
        return self.status == CaseStatus.CLOSED

    def clean(self):
        super().clean()
        if hasattr(self, 'owner') and not self.owner.is_primary_physician:
            raise ValidationError({'owner': 'Only users with the Primary Physician role can own cases.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CaseTeam(models.Model):
    """
    Junction entity representing Specialist admission to a case (FR2, C-14, FAULT-02).
    """
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='team_memberships'
    )
    specialist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admitted_cases'
    )
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='admissions_granted'
    )
    admitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Case Team Member'
        verbose_name_plural = 'Case Team Members'
        unique_together = ('case', 'specialist')
        ordering = ['admitted_at']

    def __str__(self):
        return f"{self.specialist.full_name} on Case: {self.case.title}"

    def clean(self):
        super().clean()
        if hasattr(self, 'specialist') and not self.specialist.is_specialist:
            raise ValidationError({'specialist': 'Only clinicians with the Specialist role can be admitted to a case team.'})


class Notification(models.Model):
    """
    In-app asynchronous notification for team admission and clinical updates (GAP-05).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    verb = models.CharField(max_length=50)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.full_name}: {self.verb}"
