from django import forms
from django.contrib.auth import get_user_model
from .models import Tenant

User = get_user_model()


class TenantCreationForm(forms.Form):
    """
    Workflow form for creating a tenant + its owner user.
    This is NOT a ModelForm because provisioning is multi-step.
    """
    # Tenant fields
    name = forms.CharField(max_length=255)
    domain = forms.CharField(max_length=255, help_text="Hostname for tenant (e.g. tenant.example.com)")
    is_active = forms.BooleanField(required=False, initial=True)

    # Admin/owner user fields
    admin_username = forms.CharField(max_length=150)
    admin_email = forms.EmailField()
    admin_password = forms.CharField(widget=forms.PasswordInput)
    admin_password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean_admin_password_confirm(self):
        p1 = self.cleaned_data.get('admin_password')
        p2 = self.cleaned_data.get('admin_password_confirm')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords don't match")
        return p2

    def clean_admin_username(self):
        username = self.cleaned_data.get('admin_username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists")
        return username

    def clean_domain(self):
        domain = self.cleaned_data.get('domain')
        if Tenant.objects.filter(domain=domain).exists():
            raise forms.ValidationError("A tenant with this domain already exists")
        return domain
