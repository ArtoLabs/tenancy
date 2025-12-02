from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django import forms
from .models import Tenant


class TenantAdminSite(AdminSite):
    """
    Custom admin site that enforces tenant isolation.
    Tenants can only see their own data, not other tenants or the Tenant model.
    """
    site_header = "Tenant Administration"
    site_title = "Tenant Admin"
    index_title = "Welcome to your admin panel"

    def has_permission(self, request):
        """
        Allow access if user is staff AND has a tenant context.
        Superusers can also access any tenant admin.
        """
        if not (request.user.is_active and request.user.is_staff):
            return False

        # Superusers can access any tenant admin
        if request.user.is_superuser:
            return True

        # Regular staff must have a tenant context
        return hasattr(request, 'tenant') and request.tenant is not None


class SuperAdminSite(AdminSite):
    """
    Super admin site for managing all tenants and system-wide settings.
    Only accessible without a tenant context (i.e., on the main domain).
    """
    site_header = "Super Administration"
    site_title = "Super Admin"
    index_title = "System Management"

    def has_permission(self, request):
        """
        Only allow superusers on the main domain (no tenant context).
        """
        return request.user.is_active and request.user.is_superuser and (
                    not hasattr(request, 'tenant') or request.tenant is None)


# Create the custom admin sites
tenant_admin_site = TenantAdminSite(name='tenant_admin')
super_admin_site = SuperAdminSite(name='super_admin')


class TenantCreationForm(forms.ModelForm):
    """
    Form for creating a new tenant with an admin user.
    """
    admin_username = forms.CharField(
        max_length=150,
        required=True,
        help_text="Username for the tenant's admin user"
    )
    admin_email = forms.EmailField(
        required=True,
        help_text="Email for the tenant's admin user"
    )
    admin_password = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        help_text="Password for the tenant's admin user"
    )
    admin_password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label="Confirm password"
    )

    class Meta:
        model = Tenant
        fields = ['name', 'domain', 'schema_name', 'is_active']

    def clean_admin_password_confirm(self):
        password1 = self.cleaned_data.get('admin_password')
        password2 = self.cleaned_data.get('admin_password_confirm')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords don't match")
        return password2

    def clean_admin_username(self):
        username = self.cleaned_data.get('admin_username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists")
        return username


@admin.register(Tenant, site=super_admin_site)
class TenantAdmin(admin.ModelAdmin):
    """
    Admin interface for managing tenants - only in super admin.
    """
    list_display = ['name', 'domain', 'schema_name', 'is_active', 'created_at', 'view_tenant_admin']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'domain', 'schema_name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'domain', 'schema_name')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """
        Use special form for creating new tenants that includes admin user creation.
        """
        if obj is None:  # Creating new tenant
            kwargs['form'] = TenantCreationForm
        return super().get_form(request, obj, **kwargs)

    def save_model(self, request, obj, form, change):
        """
        When creating a new tenant, also create an admin user for them.
        """
        is_new = obj.pk is None
        super().save_model(request, obj, form, change)

        if is_new and isinstance(form, TenantCreationForm):
            # Create the tenant admin user
            user = User.objects.create_user(
                username=form.cleaned_data['admin_username'],
                email=form.cleaned_data['admin_email'],
                password=form.cleaned_data['admin_password'],
            )
            user.is_staff = True
            user.is_superuser = False  # Not a superuser, just staff
            user.save()

            # Add success message
            from django.contrib import messages
            messages.success(
                request,
                f'Tenant "{obj.name}" created successfully! '
                f'Admin user "{user.username}" has been created. '
                f'They can log in at: http://{obj.domain}/manage/'
            )

    def view_tenant_admin(self, obj):
        """
        Provide a link to the tenant's admin panel.
        """
        from django.utils.html import format_html
        return format_html(
            '<a href="http://{}/manage/" target="_blank">Open Tenant Admin</a>',
            obj.domain
        )

    view_tenant_admin.short_description = 'Tenant Admin'


# Register User model to super admin
super_admin_site.register(User, BaseUserAdmin)


# Mixin to automatically register models to tenant admin
class TenantAdminMixin:
    """
    Mixin for ModelAdmin classes that should appear in tenant admin.
    Automatically filters querysets by current tenant.
    """

    def get_queryset(self, request):
        """
        Filter queryset to only show current tenant's data.
        """
        qs = super().get_queryset(request)
        if hasattr(request, 'tenant') and request.tenant:
            if hasattr(qs.model, 'tenant'):
                return qs.filter(tenant=request.tenant)
        return qs

    def save_model(self, request, obj, form, change):
        """
        Automatically set tenant when saving.
        """
        if hasattr(obj, 'tenant') and not obj.tenant_id:
            obj.tenant = request.tenant
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        """
        Only show in tenant admin if tenant context exists.
        """
        return hasattr(request, 'tenant') and request.tenant is not None

    def get_exclude(self, request, obj=None):
        """
        Exclude tenant field from forms - it's set automatically.
        """
        exclude = super().get_exclude(request, obj) or []
        if hasattr(self.model, 'tenant'):
            return list(exclude) + ['tenant']
        return exclude