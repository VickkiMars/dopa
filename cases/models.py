from decimal import Decimal
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
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

    # Structured Physiological Vitals (FR2c, FAULT-01)
    temperature_c = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Body temperature in Celsius (°C)"
    )
    heart_rate_bpm = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Heart rate in beats per minute (bpm)"
    )
    bp_systolic = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Systolic blood pressure (mmHg)"
    )
    bp_diastolic = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Diastolic blood pressure (mmHg)"
    )
    respiratory_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Respiratory rate in breaths per minute (/min)"
    )
    oxygen_saturation = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Blood oxygen saturation percentage SpO2 (%)"
    )

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

    @property
    def has_vitals(self):
        return any([
            self.temperature_c is not None,
            self.heart_rate_bpm is not None,
            self.bp_systolic is not None,
            self.bp_diastolic is not None,
            self.respiratory_rate is not None,
            self.oxygen_saturation is not None,
        ])

    @property
    def vitals_list(self):
        """
        Returns structured list of recorded vitals with status indicators for template rendering.
        """
        vitals = []
        if self.temperature_c is not None:
            t = float(self.temperature_c)
            flag = "normal"
            tag = "Normal"
            if t >= 39.5:
                flag = "critical"
                tag = "High Fever"
            elif t >= 38.0:
                flag = "warning"
                tag = "Fever"
            elif t < 35.5:
                flag = "warning"
                tag = "Hypothermia"
            vitals.append({
                'name': 'Temp',
                'value': f"{self.temperature_c} °C",
                'tag': tag,
                'flag': flag,
                'citation': f"Temp: {self.temperature_c} °C ({tag})",
            })

        if self.heart_rate_bpm is not None:
            hr = self.heart_rate_bpm
            flag = "normal"
            tag = "Normal"
            if hr > 130:
                flag = "critical"
                tag = "Severe Tachycardia"
            elif hr > 100:
                flag = "warning"
                tag = "Tachycardia"
            elif hr < 50:
                flag = "warning"
                tag = "Bradycardia"
            vitals.append({
                'name': 'Heart Rate',
                'value': f"{hr} bpm",
                'tag': tag,
                'flag': flag,
                'citation': f"HR: {hr} bpm ({tag})",
            })

        if self.bp_systolic is not None and self.bp_diastolic is not None:
            sys_val = self.bp_systolic
            dia_val = self.bp_diastolic
            flag = "normal"
            tag = "Normal"
            if sys_val >= 160 or dia_val >= 100:
                flag = "critical"
                tag = "Stage 2 HTN"
            elif sys_val >= 140 or dia_val >= 90:
                flag = "warning"
                tag = "Hypertension"
            elif sys_val < 90 or dia_val < 60:
                flag = "warning"
                tag = "Hypotension"
            vitals.append({
                'name': 'Blood Pressure',
                'value': f"{sys_val}/{dia_val} mmHg",
                'tag': tag,
                'flag': flag,
                'citation': f"BP: {sys_val}/{dia_val} mmHg ({tag})",
            })

        if self.respiratory_rate is not None:
            rr = self.respiratory_rate
            flag = "normal"
            tag = "Normal"
            if rr > 24:
                flag = "critical"
                tag = "Severe Tachypnea"
            elif rr > 20:
                flag = "warning"
                tag = "Tachypnea"
            elif rr < 12:
                flag = "warning"
                tag = "Bradypnea"
            vitals.append({
                'name': 'Resp. Rate',
                'value': f"{rr} /min",
                'tag': tag,
                'flag': flag,
                'citation': f"RR: {rr} /min ({tag})",
            })

        if self.oxygen_saturation is not None:
            spo2 = self.oxygen_saturation
            flag = "normal"
            tag = "Normal"
            if spo2 < 90:
                flag = "critical"
                tag = "Severe Hypoxia"
            elif spo2 < 95:
                flag = "warning"
                tag = "Hypoxia"
            vitals.append({
                'name': 'SpO2',
                'value': f"{spo2}%",
                'tag': tag,
                'flag': flag,
                'citation': f"SpO2: {spo2}% ({tag})",
            })

        return vitals

    def clean(self):
        super().clean()
        errors = {}
        if hasattr(self, 'owner') and not self.owner.is_primary_physician:
            errors['owner'] = 'Only users with the Primary Physician role can own cases.'

        if self.temperature_c is not None:
            if not (Decimal('25.0') <= self.temperature_c <= Decimal('45.0')):
                errors['temperature_c'] = 'Temperature must be within plausible physiological range (25.0°C - 45.0°C).'

        if self.heart_rate_bpm is not None:
            if not (20 <= self.heart_rate_bpm <= 300):
                errors['heart_rate_bpm'] = 'Heart rate must be between 20 and 300 bpm.'

        if self.bp_systolic is not None and not (40 <= self.bp_systolic <= 300):
            errors['bp_systolic'] = 'Systolic BP must be between 40 and 300 mmHg.'

        if self.bp_diastolic is not None and not (20 <= self.bp_diastolic <= 200):
            errors['bp_diastolic'] = 'Diastolic BP must be between 20 and 200 mmHg.'

        if self.bp_systolic is not None and self.bp_diastolic is not None:
            if self.bp_systolic <= self.bp_diastolic:
                errors['bp_systolic'] = 'Systolic BP must be strictly greater than Diastolic BP.'

        if self.respiratory_rate is not None:
            if not (4 <= self.respiratory_rate <= 80):
                errors['respiratory_rate'] = 'Respiratory rate must be between 4 and 80 breaths/min.'

        if self.oxygen_saturation is not None:
            if not (50 <= self.oxygen_saturation <= 100):
                errors['oxygen_saturation'] = 'Oxygen saturation must be between 50% and 100%.'

        if errors:
            raise ValidationError(errors)

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
    In-app asynchronous notification for team admission and clinical updates (GAP-05, FAULT-07, FR-NOTIFY-01).
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
    title = models.CharField(max_length=150, default='', blank=True)
    message = models.CharField(max_length=255)
    action_url = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.full_name}: {self.verb}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    @classmethod
    def unread_count_for_user(cls, user):
        if not user or not user.is_authenticated:
            return 0
        return cls.objects.filter(recipient=user, is_read=False).count()


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


class LabFlag(models.TextChoices):
    NORMAL = 'NORMAL', 'Normal'
    HIGH = 'HIGH', 'High'
    LOW = 'LOW', 'Low'
    CRITICAL = 'CRITICAL', 'Critical'
    ABNORMAL = 'ABNORMAL', 'Abnormal'


class CaseLabResult(models.Model):
    """
    Structured quantitative laboratory or diagnostic test panel (FR2c, FAULT-01).
    Enables discrete citation of verified objective values in specialist hypotheses.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='lab_results'
    )
    test_name = models.CharField(
        max_length=120,
        help_text="Diagnostic test or panel name (e.g. Serum Ferritin, WBC, Hemoglobin)"
    )
    value = models.CharField(
        max_length=60,
        help_text="Quantitative result or finding (e.g. 4200, 18.5, Positive)"
    )
    unit = models.CharField(
        max_length=40,
        blank=True,
        help_text="Measurement unit (e.g. ng/mL, x10^9/L, g/dL)"
    )
    reference_range = models.CharField(
        max_length=80,
        blank=True,
        help_text="Standard physiological reference interval (e.g. 15-200 ng/mL)"
    )
    flag = models.CharField(
        max_length=20,
        choices=LabFlag.choices,
        default=LabFlag.NORMAL,
        help_text="Clinical abnormality classification"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cases_labresult'
        ordering = ['created_at']

    def __str__(self):
        unit_str = f" {self.unit}" if self.unit else ""
        return f"{self.test_name}: {self.value}{unit_str} [{self.get_flag_display()}]"

    @property
    def citation_text(self):
        unit_str = f" {self.unit}" if self.unit else ""
        ref_str = f" (Ref: {self.reference_range})" if self.reference_range else ""
        flag_str = f" [{self.get_flag_display().upper()}]" if self.flag != LabFlag.NORMAL else ""
        return f"{self.test_name}: {self.value}{unit_str}{ref_str}{flag_str}"

