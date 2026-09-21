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


class DiagnosisRanking(models.Model):
    """
    Differential diagnosis ranking maintained exclusively by the Primary Physician (FR5, C-20, S4-01).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='rankings',
        help_text="Target clinical case"
    )
    hypothesis = models.ForeignKey(
        'collaboration.Hypothesis',
        on_delete=models.CASCADE,
        related_name='ranking_entries',
        help_text="Ranked diagnostic hypothesis"
    )
    rank_position = models.PositiveIntegerField(
        help_text="Relative priority ranking (1 = highest priority)"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cases_diagnosisranking'
        ordering = ['rank_position']
        constraints = [
            models.UniqueConstraint(fields=['case', 'hypothesis'], name='unique_case_hypothesis_rank'),
            models.UniqueConstraint(fields=['case', 'rank_position'], name='unique_case_rank_position'),
            models.CheckConstraint(check=models.Q(rank_position__gt=0), name='rank_position_positive'),
        ]

    def __str__(self):
        return f"Rank {self.rank_position}: {self.hypothesis.proposed_diagnosis} on Case: {self.case.title}"


class Decision(models.Model):
    """
    Final clinical diagnostic decision recorded exclusively by the Primary Physician (FR6, C-21, C-22).
    Requires mandatory advisory legal acknowledgement and enforces database singularity (UNIQUE case_id).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.OneToOneField(
        Case,
        on_delete=models.CASCADE,
        related_name='decision',
        help_text="Target clinical case (Enforces 1 decision per case)"
    )
    decider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='decisions_made',
        help_text="Attending Primary Physician who recorded the decision"
    )
    final_diagnosis = models.CharField(
        max_length=250,
        help_text="Definitive clinical diagnosis"
    )
    advisory_acknowledged = models.BooleanField(
        default=False,
        help_text="Mandatory legal acknowledgment that specialist advice is advisory"
    )
    governance_statement = models.TextField(
        help_text="Rendered text of governance modal statement agreed to"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cases_decision'
        ordering = ['-recorded_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(advisory_acknowledged=True),
                name='decision_must_acknowledge_advisory'
            ),
        ]

    def clean(self):
        super().clean()
        if not self.advisory_acknowledged:
            raise ValidationError({
                'advisory_acknowledged': "You must acknowledge that specialist advice is advisory and you retain sole clinical responsibility before recording the decision."
            })
        if getattr(self, 'decider_id', None) and getattr(self, 'case_id', None):
            if hasattr(self, 'case') and self.case.owner_id != self.decider_id:
                raise ValidationError({
                    'decider': "Only the designated Primary Physician case owner can record the definitive clinical decision."
                })

    def __str__(self):
        return f"Decision: {self.final_diagnosis} on Case: {self.case.title} by Dr. {self.decider.full_name}"


class AttachmentCategory(models.TextChoices):
    CLINICAL_PHOTO = 'CLINICAL_PHOTO', 'Clinical Photo (Dermatology, Wound, Eye)'
    RADIOLOGY = 'RADIOLOGY', 'Imaging (X-Ray, CT, MRI, Ultrasound)'
    WAVEFORM = 'WAVEFORM', 'Electrophysiology (ECG, EEG Tracing)'
    LAB_PDF = 'LAB_PDF', 'Laboratory / Pathology PDF Report'
    OTHER = 'OTHER', 'Other Diagnostic Media'


class CaseAttachment(models.Model):
    """
    Diagnostic media attachment linked to a clinical case (FR2b, NFR9).
    Stores verified clinical images, waveforms, and PDF reports with strict access gating.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='uploaded_attachments'
    )
    category = models.CharField(
        max_length=30,
        choices=AttachmentCategory.choices,
        default=AttachmentCategory.OTHER
    )
    title = models.CharField(
        max_length=200,
        help_text="Clinical description of the diagnostic media or study"
    )
    file = models.FileField(
        upload_to='case_attachments/%Y/%m/',
        help_text="Sanitized diagnostic file (JPEG, PNG, WebP, PDF)"
    )
    mime_type = models.CharField(
        max_length=100,
        help_text="Verified MIME content-type"
    )
    file_size_bytes = models.PositiveIntegerField(
        help_text="File size in bytes"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cases_attachment'
        ordering = ['uploaded_at']

    def __str__(self):
        return f"{self.get_category_display()}: {self.title} ({self.case.title})"

