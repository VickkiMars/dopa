import json
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from accounts.models import User, Role
from .models import Case, CaseTeam, CaseAttachment, AttachmentCategory, CaseLabResult, LabFlag


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
            'placeholder': 'General appearance, skin lesions, abdominal exam, cardiovascular / respiratory auscultation, and clinical impressions...',
            'class': 'form-input',
            'rows': 5
        }),
        help_text="Physical examination and narrative bedside observations (FAULT-01)."
    )

    # Discrete Physiological Vital Signs (FR2c)
    temperature_c = forms.DecimalField(
        required=False,
        max_digits=4,
        decimal_places=1,
        min_value=Decimal('25.0'),
        max_value=Decimal('45.0'),
        widget=forms.NumberInput(attrs={
            'placeholder': '38.5',
            'class': 'form-input vital-field',
            'step': '0.1',
        }),
        help_text="°C (25.0 - 45.0)"
    )
    heart_rate_bpm = forms.IntegerField(
        required=False,
        min_value=20,
        max_value=300,
        widget=forms.NumberInput(attrs={
            'placeholder': '72',
            'class': 'form-input vital-field',
        }),
        help_text="bpm (20 - 300)"
    )
    bp_systolic = forms.IntegerField(
        required=False,
        min_value=40,
        max_value=300,
        widget=forms.NumberInput(attrs={
            'placeholder': '120',
            'class': 'form-input vital-field',
        }),
        help_text="Systolic (mmHg)"
    )
    bp_diastolic = forms.IntegerField(
        required=False,
        min_value=20,
        max_value=200,
        widget=forms.NumberInput(attrs={
            'placeholder': '80',
            'class': 'form-input vital-field',
        }),
        help_text="Diastolic (mmHg)"
    )
    respiratory_rate = forms.IntegerField(
        required=False,
        min_value=4,
        max_value=80,
        widget=forms.NumberInput(attrs={
            'placeholder': '16',
            'class': 'form-input vital-field',
        }),
        help_text="breaths/min (4 - 80)"
    )
    oxygen_saturation = forms.IntegerField(
        required=False,
        min_value=50,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'placeholder': '98',
            'class': 'form-input vital-field',
        }),
        help_text="% SpO2 (50 - 100)"
    )
    lab_data_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = Case
        fields = [
            'title', 'clinical_summary', 'history', 'findings',
            'temperature_c', 'heart_rate_bpm', 'bp_systolic', 'bp_diastolic',
            'respiratory_rate', 'oxygen_saturation'
        ]

    def clean(self):
        cleaned_data = super().clean()
        sys_val = cleaned_data.get('bp_systolic')
        dia_val = cleaned_data.get('bp_diastolic')
        if sys_val is not None and dia_val is not None and sys_val <= dia_val:
            self.add_error('bp_systolic', 'Systolic BP must be strictly greater than Diastolic BP.')

        lab_data_raw = cleaned_data.get('lab_data_json')
        if lab_data_raw:
            try:
                parsed = json.loads(lab_data_raw)
                if not isinstance(parsed, list):
                    self.add_error('lab_data_json', 'Invalid structured lab data format.')
            except Exception:
                self.add_error('lab_data_json', 'Malformed JSON in lab data payload.')
        return cleaned_data

    def save_lab_results(self, case):
        if getattr(self, '_labs_saved', False):
            return 0
        lab_data_raw = self.cleaned_data.get('lab_data_json')
        created_count = 0
        if lab_data_raw:
            try:
                items = json.loads(lab_data_raw)
                for item in items:
                    t_name = str(item.get('test_name', '')).strip()
                    val = str(item.get('value', '')).strip()
                    if t_name and val:
                        flag_val = item.get('flag', LabFlag.NORMAL)
                        if flag_val not in LabFlag.values:
                            flag_val = LabFlag.NORMAL
                        CaseLabResult.objects.create(
                            case=case,
                            test_name=t_name[:120],
                            value=val[:60],
                            unit=str(item.get('unit', ''))[:40].strip(),
                            reference_range=str(item.get('reference_range', ''))[:80].strip(),
                            flag=flag_val
                        )
                        created_count += 1
            except Exception:
                pass
        self._labs_saved = True
        return created_count

    def save(self, commit=True):
        case = super().save(commit=commit)
        if commit:
            self.save_lab_results(case)
        return case


class CaseFindingsUpdateForm(forms.ModelForm):
    """
    Case Owner update form for revising vitals, exam findings, and appending labs during consultation.
    """
    temperature_c = forms.DecimalField(
        required=False,
        max_digits=4,
        decimal_places=1,
        min_value=Decimal('25.0'),
        max_value=Decimal('45.0'),
        widget=forms.NumberInput(attrs={'class': 'form-input vital-field', 'step': '0.1', 'placeholder': '38.5'}),
        help_text="°C"
    )
    heart_rate_bpm = forms.IntegerField(
        required=False,
        min_value=20,
        max_value=300,
        widget=forms.NumberInput(attrs={'class': 'form-input vital-field', 'placeholder': '72'}),
        help_text="bpm"
    )
    bp_systolic = forms.IntegerField(
        required=False,
        min_value=40,
        max_value=300,
        widget=forms.NumberInput(attrs={'class': 'form-input vital-field', 'placeholder': '120'}),
        help_text="mmHg"
    )
    bp_diastolic = forms.IntegerField(
        required=False,
        min_value=20,
        max_value=200,
        widget=forms.NumberInput(attrs={'class': 'form-input vital-field', 'placeholder': '80'}),
        help_text="mmHg"
    )
    respiratory_rate = forms.IntegerField(
        required=False,
        min_value=4,
        max_value=80,
        widget=forms.NumberInput(attrs={'class': 'form-input vital-field', 'placeholder': '16'}),
        help_text="breaths/min"
    )
    oxygen_saturation = forms.IntegerField(
        required=False,
        min_value=50,
        max_value=100,
        widget=forms.NumberInput(attrs={'class': 'form-input vital-field', 'placeholder': '98'}),
        help_text="% SpO2"
    )
    findings = forms.CharField(
        min_length=20,
        max_length=5000,
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 5}),
        help_text="Physical examination and narrative bedside observations."
    )
    lab_data_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = Case
        fields = [
            'temperature_c', 'heart_rate_bpm', 'bp_systolic', 'bp_diastolic',
            'respiratory_rate', 'oxygen_saturation', 'findings'
        ]

    def clean(self):
        cleaned_data = super().clean()
        sys_val = cleaned_data.get('bp_systolic')
        dia_val = cleaned_data.get('bp_diastolic')
        if sys_val is not None and dia_val is not None and sys_val <= dia_val:
            self.add_error('bp_systolic', 'Systolic BP must be strictly greater than Diastolic BP.')
        return cleaned_data

    def save_lab_results(self, case):
        if getattr(self, '_labs_saved', False):
            return 0
        lab_data_raw = self.cleaned_data.get('lab_data_json')
        created_count = 0
        if lab_data_raw:
            try:
                items = json.loads(lab_data_raw)
                for item in items:
                    t_name = str(item.get('test_name', '')).strip()
                    val = str(item.get('value', '')).strip()
                    if t_name and val:
                        flag_val = item.get('flag', LabFlag.NORMAL)
                        if flag_val not in LabFlag.values:
                            flag_val = LabFlag.NORMAL
                        CaseLabResult.objects.create(
                            case=case,
                            test_name=t_name[:120],
                            value=val[:60],
                            unit=str(item.get('unit', ''))[:40].strip(),
                            reference_range=str(item.get('reference_range', ''))[:80].strip(),
                            flag=flag_val
                        )
                        created_count += 1
            except Exception:
                pass
        self._labs_saved = True
        return created_count

    def save(self, commit=True):
        case = super().save(commit=commit)
        if commit:
            self.save_lab_results(case)
        return case


class CaseLabResultForm(forms.ModelForm):
    class Meta:
        model = CaseLabResult
        fields = ['test_name', 'value', 'unit', 'reference_range', 'flag']
        widgets = {
            'test_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Serum Ferritin'}),
            'value': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 4200'}),
            'unit': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. ng/mL'}),
            'reference_range': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 15 - 200 ng/mL'}),
            'flag': forms.Select(attrs={'class': 'form-input'}),
        }


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


DEFAULT_GOVERNANCE_STATEMENT = (
    "As the designated Primary Physician and case owner, I acknowledge that all specialist diagnostic "
    "hypotheses, findings interpretations, and clinical discussion notes provided through the DOPA platform "
    "are advisory in nature. I confirm that I retain sole diagnostic authority, ethical accountability, and "
    "legal responsibility for the final medical decision and subsequent patient management recorded herein."
)


class RankingReorderForm(forms.Form):
    hypothesis_id = forms.UUIDField(required=True)
    direction = forms.ChoiceField(
        choices=[('UP', 'Up'), ('DOWN', 'Down')],
        required=True
    )


class DecisionRecordForm(forms.ModelForm):
    idempotency_token = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    advisory_acknowledged = forms.BooleanField(
        required=True,
        error_messages={
            'required': "You must acknowledge that specialist advice is advisory and you retain sole clinical responsibility before recording the decision."
        },
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox', 'id': 'id_advisory_acknowledged'}),
        label="I acknowledge that all specialist hypotheses are advisory and I retain sole clinical responsibility for this final medical decision."
    )
    governance_statement = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    class Meta:
        model = Case
        # We define fields on Decision
        fields = []

    final_diagnosis = forms.CharField(
        max_length=250,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Definitive Clinical Diagnosis (e.g. Anti-NMDA Receptor Encephalitis)',
            'required': 'required',
            'id': 'id_final_diagnosis'
        }),
        help_text="Definitive diagnostic conclusion reached for this clinical case."
    )

    def clean_advisory_acknowledged(self):
        ack = self.cleaned_data.get('advisory_acknowledged', False)
        if not ack:
            raise ValidationError(
                "You must acknowledge that specialist advice is advisory and you retain sole clinical responsibility before recording the decision."
            )
        return ack

    def clean_governance_statement(self):
        stmt = self.cleaned_data.get('governance_statement')
        if not stmt or not stmt.strip():
            stmt = DEFAULT_GOVERNANCE_STATEMENT
        return stmt


ALLOWED_MIME_TYPES = {
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/png': ['.png'],
    'image/webp': ['.webp'],
    'application/pdf': ['.pdf']
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class CaseAttachmentUploadForm(forms.ModelForm):
    title = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. 20-Minute Routine EEG Rhythm Strip or Chest CT Slice',
            'required': 'required'
        }),
        help_text="Clinical description of the diagnostic media or study."
    )
    category = forms.ChoiceField(
        choices=AttachmentCategory.choices,
        widget=forms.Select(attrs={
            'class': 'form-input'
        }),
        help_text="Clinical diagnostic category."
    )
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': '.jpg,.jpeg,.png,.webp,.pdf'
        }),
        help_text="Approved formats: JPEG, PNG, WebP, PDF. Max size: 10 MB."
    )

    class Meta:
        model = CaseAttachment
        fields = ['title', 'category', 'file']

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise ValidationError("A diagnostic file is required.")

        # Check size
        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                f"File size exceeds maximum limit of 10 MB ({uploaded_file.size / (1024*1024):.1f} MB uploaded)."
            )

        # Check extension
        import os
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        valid_extensions = [e for exts in ALLOWED_MIME_TYPES.values() for e in exts]
        if ext not in valid_extensions:
            raise ValidationError(
                f"File format '{ext}' is not permitted. Only standard diagnostic formats (.jpg, .jpeg, .png, .webp, .pdf) are allowed."
            )

        # Check content type if provided
        content_type = getattr(uploaded_file, 'content_type', '').lower()
        if content_type and content_type not in ALLOWED_MIME_TYPES:
            raise ValidationError(
                f"MIME type '{content_type}' is not an approved medical document format."
            )

        return uploaded_file

