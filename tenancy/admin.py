from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import gettext as _
from .models import Tenant
from .forms import TenantCreationForm
from .services import TenantProvisioner, TenantProvisioningError
from .mixins import TenantAdminMixin, SuperUserAdminMixin


class TenantAdminSite(AdminSite):
    """
    Admin site used by tenants (shown at tenant domain, e.g. tenant.example.com/manage/).
    This site should NEVER expose the Tenant model.
    """
    site_header = "Tenant Administration"
    site_title = "Tenant Admin"
    index_title = "Welcome to your admin panel"

    def has_permission(self, request):
        """Allow staff users who belong to the current tenant"""
        import logging
        logger = logging.getLogger(__name__)

        if not request.user.is_active:
            logger.debug(f"User {request.user} denied: not active")
            return False

        # Superusers always have access
        if request.user.is_superuser:
            logger.debug(f"Superuser {request.user} granted access")
            return True

        # Staff users need to belong to current tenant
        if not request.user.is_staff:
            logger.debug(f"User {request.user} denied: not staff")
            return False

        # Check if user belongs to current tenant
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            logger.warning(f"Staff user {request.user} denied: no tenant in request")
            return False

        # If User model has tenant field, check it
        if hasattr(request.user, 'tenant'):
            user_tenant = request.user.tenant
            has_access = user_tenant == tenant
            logger.debug(
                f"Staff user {request.user} - User tenant: {user_tenant}, Request tenant: {tenant}, Access: {has_access}")
            return has_access

        # Otherwise allow staff users (for projects without tenant-aware users)
        logger.debug(f"Staff user {request.user} granted access (no tenant field on User model)")
        return True

    def get_app_list(self, request):
        """
        Remove the Tenant model from app list for tenant site to avoid leakage.
        """
        app_list = super().get_app_list(request)
        for app in app_list:
            # Filter out Tenant model from the returned models
            app['models'] = [m for m in app['models'] if m.get('object_name') != 'Tenant']
        return app_list


class SuperAdminSite(AdminSite):
    """
    Site for managing system-wide objects such as Tenant model and creating tenants.
    """
    index_template = "admin/tenancy/super_index.html"
    site_header = "Super Administration"
    site_title = "Super Admin"
    index_title = "System Management"

    def has_permission(self, request):
        """Only superusers can access super admin"""
        return request.user.is_active and request.user.is_superuser

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('create-tenant/', self.admin_view(self.create_tenant_view), name='create-tenant'),
        ]
        return custom_urls + urls

    def create_tenant_view(self, request):
        """
        Admin view that displays TenantCreationForm and provisions the tenant using TenantProvisioner.
        """
        if request.method == 'POST':
            form = TenantCreationForm(request.POST)
            if form.is_valid():
                tenant_data = {
                    'name': form.cleaned_data['name'],
                    'domain': form.cleaned_data['domain'],
                    'is_active': form.cleaned_data.get('is_active', True),
                }
                admin_data = {
                    'username': form.cleaned_data['admin_username'],
                    'email': form.cleaned_data['admin_email'],
                    'password': form.cleaned_data['admin_password'],
                }
                try:
                    tenant, user = TenantProvisioner.create_tenant(tenant_data, admin_data)
                except TenantProvisioningError as exc:
                    messages.error(request, f"Failed to create tenant: {exc}")
                except Exception as exc:
                    messages.error(request, f"Unexpected error provisioning tenant: {exc}")
                else:
                    messages.success(
                        request,
                        _(
                            'Tenant "%(tenant)s" created and admin user "%(user)s" provisioned. '
                            'Tenant admin login: http://%(domain)s/manage/'
                        ) % {'tenant': tenant.name, 'user': user.username, 'domain': tenant.domain}
                    )
                    return redirect('admin:index')
        else:
            form = TenantCreationForm()

        context = {
            **self.each_context(request),
            'title': 'Create Tenant',
            'form': form,
        }
        return render(request, 'admin/tenancy/create_tenant.html', context)


# Instantiate the admin sites
tenant_admin_site = TenantAdminSite(name='tenant_admin')
super_admin_site = SuperAdminSite(name='super_admin')


# Admin for the Tenant model included in this package
@admin.register(Tenant, site=super_admin_site)
class TenantAdmin(admin.ModelAdmin):
    """
    Simple Tenant ModelAdmin for the super admin (no provisioning logic here).
    """
    list_display = ['name', 'domain', 'is_active', 'created_at', 'view_tenant_admin']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'domain']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'domain')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def view_tenant_admin(self, obj):
        return format_html('<a href="http://{}/manage/" target="_blank">Open Tenant Admin</a>', obj.domain)

    view_tenant_admin.short_description = 'Tenant Admin'


# =============================================================================
# DYNAMIC USER ADMIN GENERATOR
# =============================================================================

def create_dynamic_user_admin():
    """
    Dynamically creates a UserAdmin class based on the project's custom user model.
    This function inspects the user model and generates appropriate admin configuration.
    """
    User = get_user_model()

    # Detect available fields
    user_fields = {f.name for f in User._meta.get_fields() if not f.many_to_many and not f.one_to_many}

    # Common field detection
    has_username = 'username' in user_fields
    has_email = 'email' in user_fields
    has_first_name = 'first_name' in user_fields
    has_last_name = 'last_name' in user_fields
    has_tenant = 'tenant' in user_fields

    # Build list_display
    list_display = []
    if has_username:
        list_display.append('username')
    if has_email:
        list_display.append('email')
    if has_first_name:
        list_display.append('first_name')
    if has_last_name:
        list_display.append('last_name')
    list_display.extend(['is_staff', 'is_active'])

    # Build search_fields
    search_fields = []
    if has_username:
        search_fields.append('username')
    if has_email:
        search_fields.append('email')
    if has_first_name:
        search_fields.append('first_name')
    if has_last_name:
        search_fields.append('last_name')

    # Build list_filter
    list_filter = ['is_staff', 'is_superuser', 'is_active']
    if has_tenant:
        list_filter.append('tenant')

    # Build fieldsets dynamically
    fieldsets = []

    # Personal info section
    personal_fields = []
    if has_username:
        personal_fields.append('username')
    if has_email:
        personal_fields.append('email')
    if has_first_name or has_last_name:
        if has_first_name:
            personal_fields.append('first_name')
        if has_last_name:
            personal_fields.append('last_name')

    # Add tenant field to personal info if it exists
    if has_tenant:
        personal_fields.append('tenant')

    if personal_fields:
        fieldsets.append((None, {'fields': personal_fields}))

    # Permissions section
    permissions_fields = ['is_active', 'is_staff', 'is_superuser']
    if 'groups' in user_fields:
        permissions_fields.append('groups')
    if 'user_permissions' in user_fields:
        permissions_fields.append('user_permissions')

    fieldsets.append((_('Permissions'), {'fields': permissions_fields}))

    # Important dates section
    important_dates_fields = []
    if 'last_login' in user_fields:
        important_dates_fields.append('last_login')
    if 'date_joined' in user_fields:
        important_dates_fields.append('date_joined')

    if important_dates_fields:
        fieldsets.append((_('Important dates'), {'fields': important_dates_fields}))

    # Add password fieldset for creation
    add_fieldsets_list = []
    add_fields = []

    if has_username:
        add_fields.append('username')
    if has_email:
        add_fields.append('email')
    if has_tenant:
        add_fields.append('tenant')

    add_fields.extend(['password1', 'password2'])

    add_fieldsets_list.append((None, {
        'classes': ('wide',),
        'fields': add_fields,
    }))

    # Create the base admin class with all detected fields
    class DynamicUserAdminBase(BaseUserAdmin):
        list_display = list_display
        search_fields = search_fields
        list_filter = list_filter
        fieldsets = fieldsets
        add_fieldsets = add_fieldsets_list
        ordering = ['id']

        # For password field in change form
        def get_form(self, request, obj=None, **kwargs):
            form = super().get_form(request, obj, **kwargs)
            # Ensure password field uses the proper widget
            if 'password' in form.base_fields:
                form.base_fields['password'].help_text = (
                    "Raw passwords are not stored, so there is no way to see this "
                    "user's password, but you can change the password using "
                    '<a href="../password/">this form</a>.'
                )
            return form

    return DynamicUserAdminBase


def create_tenant_user_admin():
    """
    Creates a tenant-scoped user admin that filters users by current tenant.
    """
    DynamicUserAdminBase = create_dynamic_user_admin()
    User = get_user_model()
    has_tenant = hasattr(User, 'tenant')

    class TenantScopedUserAdmin(TenantAdminMixin, DynamicUserAdminBase):
        """
        User admin for tenant site - shows only users belonging to current tenant.
        Combines dynamic field detection with tenant scoping.
        """

        def get_queryset(self, request):
            qs = super(DynamicUserAdminBase, self).get_queryset(request)
            if has_tenant and hasattr(request, 'tenant') and request.tenant:
                return qs.filter(tenant=request.tenant)
            return qs

        def save_model(self, request, obj, form, change):
            if has_tenant and not change:
                if not getattr(obj, 'tenant_id', None):
                    if hasattr(request, 'tenant') and request.tenant:
                        obj.tenant = request.tenant
            super().save_model(request, obj, form, change)

        def get_exclude(self, request, obj=None):
            # Don't exclude tenant field in tenant admin - let it be readonly
            return None

        def get_readonly_fields(self, request, obj=None):
            readonly = list(super().get_readonly_fields(request, obj) or [])
            if has_tenant and obj:  # When editing existing user
                if 'tenant' not in readonly:
                    readonly.append('tenant')
            return readonly

    return TenantScopedUserAdmin


def create_super_user_admin():
    """
    Creates a super admin user admin that shows all users with tenant display.
    """
    DynamicUserAdminBase = create_dynamic_user_admin()
    User = get_user_model()
    has_tenant = hasattr(User, 'tenant')

    class SuperUserAdmin(SuperUserAdminMixin, DynamicUserAdminBase):
        """
        User admin for super admin site - shows all users with tenant information.
        """

        def get_readonly_fields(self, request, obj=None):
            readonly = list(super().get_readonly_fields(request, obj) or [])
            if has_tenant and 'tenant' not in readonly:
                readonly.append('tenant')
            return readonly

    return SuperUserAdmin


# =============================================================================
# AUTO-REGISTRATION
# =============================================================================

def register_user_admins():
    """
    Automatically register the dynamically generated user admin classes
    on both admin sites.
    """
    User = get_user_model()

    # Create the dynamic admin classes
    SuperUserAdmin = create_super_user_admin()
    TenantScopedUserAdmin = create_tenant_user_admin()

    # Register on super admin site
    super_admin_site.register(User, SuperUserAdmin)

    # Register on tenant admin site
    tenant_admin_site.register(User, TenantScopedUserAdmin)


# Call registration when this module is imported
register_user_admins()