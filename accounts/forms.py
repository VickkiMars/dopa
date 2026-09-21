from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import User, Role


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'class': 'form-input',
            'autocomplete': 'new-password'
        }),
        min_length=8,
        help_text="Minimum 8 characters with letters and numbers."
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'class': 'form-input',
            'autocomplete': 'new-password'
        }),
        label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ['full_name', 'email', 'role']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'placeholder': 'Dr. Firstname Lastname',
                'class': 'form-input',
                'autocomplete': 'name'
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'clinician@hospital.org',
                'class': 'form-input',
                'autocomplete': 'email'
            }),
            'role': forms.RadioSelect(attrs={
                'class': 'role-radio'
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email address is already registered.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm:
            if password != password_confirm:
                self.add_error('password_confirm', "Passwords do not match.")
            else:
                validate_password(password)

        return cleaned_data

    def save(self, commit=True):
        user = User.objects.create_user(
            email=self.cleaned_data['email'],
            full_name=self.cleaned_data['full_name'],
            role=self.cleaned_data['role'],
            password=self.cleaned_data['password']
        )
        return user


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'placeholder': 'clinician@hospital.org',
            'class': 'form-input',
            'autocomplete': 'email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'class': 'form-input',
            'autocomplete': 'current-password'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email', '').strip().lower()
        password = cleaned_data.get('password')

        if email and password:
            user = User.objects.filter(email__iexact=email).first()
            if user and user.check_password(password) and not user.is_active:
                raise ValidationError("This account is currently inactive. Contact your administrator.")

            self.user = authenticate(username=email, password=password)
            if self.user is None:
                raise ValidationError("Invalid email or password. Please verify your credentials.")

        return cleaned_data
