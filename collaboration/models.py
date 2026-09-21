import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from accounts.models import User, Role
from cases.models import Case, CaseTeam


class HypothesisStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn'


class Hypothesis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='hypotheses',
        help_text="Target clinical case"
    )
    specialist = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='hypotheses',
        help_text="Submitting specialist"
    )
    proposed_diagnosis = models.CharField(
        max_length=250,
        help_text="Diagnostic label proposed by specialist"
    )
    rationale = models.TextField(
        help_text="Pathophysiological reasoning (min 20 chars)"
    )
    supporting_evidence = models.TextField(
        help_text="Specific references to clinical findings and labs (min 20 chars)"
    )
    status = models.CharField(
        max_length=20,
        choices=HypothesisStatus.choices,
        default=HypothesisStatus.ACTIVE,
        db_index=True
    )
    withdrawal_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Explanatory clinical rationale when marked withdrawn"
    )
    withdrawn_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="UTC timestamp when hypothesis was withdrawn"
    )
    submitted_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="UTC timestamp when hypothesis was recorded"
    )

    class Meta:
        db_table = 'collaboration_hypothesis'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['case', 'status']),
            models.Index(fields=['specialist']),
        ]

    def clean(self):
        super().clean()
        if getattr(self, 'specialist_id', None):
            try:
                if self.specialist and self.specialist.role != Role.SPECIALIST:
                    raise ValidationError({'specialist': "Only users with the Specialist role can submit clinical hypotheses."})
            except User.DoesNotExist:
                pass
        
            if getattr(self, 'case_id', None):
                is_admitted = CaseTeam.objects.filter(case_id=self.case_id, specialist_id=self.specialist_id).exists()
                if not is_admitted:
                    raise ValidationError({'specialist': "Specialist must be an admitted member of the case team to submit hypotheses."})

        if self.rationale and len(self.rationale.strip()) < 20:
            raise ValidationError({'rationale': "Clinical rationale must be at least 20 characters."})

        if self.supporting_evidence and len(self.supporting_evidence.strip()) < 20:
            raise ValidationError({'supporting_evidence': "Supporting evidence must be at least 20 characters."})

        if self.status == HypothesisStatus.WITHDRAWN and not self.withdrawal_reason:
            raise ValidationError({'withdrawal_reason': "A withdrawal reason is mandatory when withdrawing a hypothesis."})

    def withdraw(self, reason: str):
        """Mark hypothesis as withdrawn with reason and timestamp."""
        if not reason or len(reason.strip()) < 10:
            raise ValidationError("Withdrawal reason must be at least 10 characters.")
        self.status = HypothesisStatus.WITHDRAWN
        self.withdrawal_reason = reason.strip()
        self.withdrawn_at = timezone.now()
        self.save(update_fields=['status', 'withdrawal_reason', 'withdrawn_at'])

    def __str__(self):
        return f"[{self.status}] {self.proposed_diagnosis} by {self.specialist.full_name}"


class DiscussionNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        Case,
        on_delete=models.CASCADE,
        related_name='discussion_notes',
        help_text="Target clinical case"
    )
    author = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='discussion_notes',
        help_text="Physician or specialist posting the note"
    )
    body = models.TextField(
        max_length=2000,
        help_text="Narrative clinical deliberation or query"
    )
    posted_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="UTC posting timestamp"
    )

    class Meta:
        db_table = 'collaboration_discussionnote'
        ordering = ['posted_at']
        indexes = [
            models.Index(fields=['case', 'posted_at']),
        ]

    def clean(self):
        super().clean()
        if not self.body or not self.body.strip():
            raise ValidationError({'body': "Discussion note cannot be blank."})
        
        # Verify author is authorized on the case (either owner or admitted specialist)
        if getattr(self, 'case_id', None) and getattr(self, 'author_id', None):
            is_owner = (self.case.owner_id == self.author_id)
            is_admitted = CaseTeam.objects.filter(case_id=self.case_id, specialist_id=self.author_id).exists()
            if not (is_owner or is_admitted):
                raise ValidationError({'author': "Only the case owner or admitted specialists can participate in the discussion."})

    def __str__(self):
        return f"Note by {self.author.full_name} on {self.case.title} at {self.posted_at}"
