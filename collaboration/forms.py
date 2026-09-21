import uuid
from django import forms
from django.core.exceptions import ValidationError
from .models import Hypothesis, DiscussionNote


class HypothesisCreateForm(forms.ModelForm):
    idempotency_token = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )

    class Meta:
        model = Hypothesis
        fields = ['proposed_diagnosis', 'rationale', 'supporting_evidence']
        widgets = {
            'proposed_diagnosis': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g., Anti-NMDA Receptor Encephalitis',
                'required': 'required'
            }),
            'rationale': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 4,
                'placeholder': 'Explain the clinical reasoning, pathophysiological mechanism, or diagnostic trajectory (min 20 chars)...',
                'required': 'required'
            }),
            'supporting_evidence': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 4,
                'placeholder': 'Cite specific clinical findings, physical exams, vitals, or lab anomalies supporting this hypothesis (min 20 chars)...',
                'required': 'required'
            }),
        }

    def clean_proposed_diagnosis(self):
        diag = self.cleaned_data.get('proposed_diagnosis', '').strip()
        if not diag:
            raise ValidationError("Proposed diagnosis cannot be blank.")
        return diag

    def clean_rationale(self):
        rationale = self.cleaned_data.get('rationale', '').strip()
        if len(rationale) < 20:
            raise ValidationError("Clinical rationale must be at least 20 characters.")
        return rationale

    def clean_supporting_evidence(self):
        evidence = self.cleaned_data.get('supporting_evidence', '').strip()
        if len(evidence) < 20:
            raise ValidationError("Supporting evidence must be at least 20 characters.")
        return evidence


class HypothesisWithdrawForm(forms.Form):
    idempotency_token = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    withdrawal_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input',
            'rows': 3,
            'placeholder': 'State the clinical reason for withdrawing this hypothesis (e.g., Refuted by negative CSF panel, ruled out by new imaging)...',
            'required': 'required'
        }),
        min_length=10,
        max_length=1000,
        required=True,
        help_text="Provide mandatory explanatory reasoning for clinical provenance."
    )

    def clean_withdrawal_reason(self):
        reason = self.cleaned_data.get('withdrawal_reason', '').strip()
        if len(reason) < 10:
            raise ValidationError("Withdrawal rationale must be at least 10 characters.")
        return reason


class DiscussionNoteCreateForm(forms.ModelForm):
    idempotency_token = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )

    class Meta:
        model = DiscussionNote
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 3,
                'placeholder': 'Post a clinical query or deliberation note for the multidisciplinary team...',
                'required': 'required'
            })
        }

    def clean_body(self):
        body = self.cleaned_data.get('body', '').strip()
        if not body:
            raise ValidationError("Discussion note cannot be empty.")
        if len(body) > 2000:
            raise ValidationError("Discussion note cannot exceed 2000 characters.")
        return body
