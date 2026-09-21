from django import forms
from django.core.exceptions import ValidationError
from accounts.models import User, Role
from .models import Case, CaseTeam


class CaseCreateForm(forms.ModelForm):
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Acute Multi-System Presentation with Fevers and Joint Pain',
            'class': 'form-input',
            'autocomplete': 'off'
        }),
        help_text="Clear clinical presentation title or chief symptom complex."
    )
    clinical_summary = forms.CharField(
        min_length=30,
        max_length=5000,
        widget=forms.Textarea(attrs={
            'placeholder': 'Describe the patient demographics, acute presentation, and reasons for requesting specialist consultation...',
            'class': 'form-input',
            'rows': 4
        }),
        help_text="Minimum 30 characters."
    )
    history = forms.CharField(
        min_length=30,
        max_length=5000,
        widget=forms.Textarea(attrs={
            'placeholder': 'Detailed past medical history, medications, allergies, surgical interventions, and family medical background...',
            'class': 'form-input',
            'rows': 4
        }),
        help_text="Minimum 30 characters."
    )
    findings = forms.CharField(
        min_length=20,
        max_length=5000,
        widget=forms.Textarea(attrs={
            'placeholder': '### Vital Signs:\nTemp: 38.8C, HR: 95, BP: 120/80\n\n### Laboratory Markers:\nWBC: 14.5, CRP: 45, ESR: 60\n\n### Imaging & Pathology:\nChest CT shows...',
            'class': 'form-input',
            'rows': 6
        }),
        help_text="Structured physical examination, vitals, lab markers, and imaging findings (FAULT-01)."
    )

    class Meta:
        model = Case
        fields = ['title', 'clinical_summary', 'history', 'findings']


class TeamAdmitForm(forms.Form):
    specialist_email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'placeholder': 'specialist@hospital.org',
            'class': 'form-input',
            'autocomplete': 'email'
        }),
        help_text="Enter the registered email of the specialist you wish to admit to this consultation."
    )

    def __init__(self, *args, **kwargs):
        self.case = kwargs.pop('case', None)
        super().__init__(*args, **kwargs)

    def clean_specialist_email(self):
        email = self.cleaned_data.get('specialist_email', '').strip().lower()
        target_user = User.objects.filter(email__iexact=email).first()

        if not target_user:
            raise ValidationError("No registered clinician account found with this email address.")

        if not target_user.is_specialist:
            raise ValidationError(
                f"Account '{target_user.full_name}' is registered as a {target_user.get_role_display()}. "
                "Only clinicians with the Specialist role can be admitted to advisory case teams (G-08)."
            )

        if self.case and CaseTeam.objects.filter(case=self.case, specialist=target_user).exists():
            raise ValidationError(f"Dr. {target_user.full_name} is already an admitted member of this case team.")

        self.target_specialist = target_user
        return email
