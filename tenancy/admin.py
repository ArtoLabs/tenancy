from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.conf import settings
from django.utils.module_loading import import_string

from .models import Tenant
from .forms import TenantCreationForm
from .services import TenantProvisioner, TenantProvisioningError
from .mixins import TenantAdminMixin, SuperUserAdminMixin
from .roles import roles, TenancyRole


class TenantAdminSite(AdminSite):
    """
    Admin site used by tenant managers (shown at tenant domain, e.g. tenant.example.com/manage/).

    ACCESS CONTROL: Only users with 'tenantmanager' role can access this site.
    This site should NEVER expose the Tenant model or TenancyRole model.
    """
    site_header = "Tenant Administration"
    site_title = "Tenant Admin"
    index_title = "Welcome to your admin panel"

    def has_permission(self, request):
        """
        Allow users with tenantmanager role who belong to the current tenant,
        OR tenant admins (who have access to all tenants).

        Permission hierarchy:
        1. User must be authenticated and active
        2. Tenant admins have access to ALL tenant admin sites
        3. Tenant managers have access to ONLY their assigned tenant's admin site

        SECURITY: This is a critical permission check. The middleware should have
        already blocked unauthorized access, but we verify again here.
        """
        import logging
        logger = logging.getLogger(__name__)

        if not request.user.is_authenticated or not request.user.is_active:
            logger.debug(f"User {request.user} denied: not authenticated or not active")
            return False

        # Get the tenant from request (set by middleware based on domain)
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            logger.warning(f"User {request.user} denied: no tenant in request")
            return False

        # Tenant admins have access to ALL tenant admin sites
        if roles.is_tenant_admin(request.user):
            logger.debug(f"Tenant admin {request.user} granted access to tenant admin site for {tenant}")
            return True

        # For tenant managers, verify they have role for THIS SPECIFIC tenant
        # This is the critical check that prevents cross-tenant access
        has_access = roles.is_tenant_manager(request.user, tenant)

        if not has_access:
            logger.warning(
                f"User {request.user} denied access to {tenant} /manage/ - "
                f"not a tenant manager for this tenant"
            )
        else:
            logger.debug(
                f"Tenant manager {request.user} granted access to {tenant} /manage/"
            )

        return has_access

    def get_app_list(self, request):
        """
        Remove sensitive models from app list for tenant site to avoid leakage.

        SECURITY: Tenant managers should never see or manipulate:
        - Tenant model (tenant structure)
        - TenancyRole model (permission system)
        """
        app_list = super().get_app_list(request)
        for app in app_list:
            # Filter out sensitive models
            app['models'] = [
                m for m in app['models']
                if m.get('object_name') not in ['Tenant', 'TenancyRole']
            ]
        return app_list


class SuperAdminSite(AdminSite):
    """
    Site for managing system-wide objects such as Tenant model and creating tenants.

    This admin site is for tenant admins only and provides:
    - Tenant creation and management
    - Cross-tenant user management
    - System-wide configuration
    - Role assignment

    ACCESS CONTROL: Only users with 'tenantadmin' role can access this site.
    """
    index_template = "admin/tenancy/super_index.html"
    site_header = "Tenant System Administration"
    site_title = "Tenant Admin"
    index_title = "System Management"

    def has_permission(self, request):
        """
        Only users with tenantadmin role can access super admin.

        CRITICAL: Tenant managers should NEVER access this site.
        """
        if not request.user.is_authenticated or not request.user.is_active:
            return False

        # ONLY tenant admins can access super admin
        # Explicitly deny tenant managers
        return roles.is_tenant_admin(request.user)

    def get_urls(self):
        """
        Add custom URL for tenant creation workflow.
        """
        urls = super().get_urls()
        custom_urls = [
            path('create-tenant/', self.admin_view(self.create_tenant_view), name='create-tenant'),
        ]
        return custom_urls + urls

    def create_tenant_view(self, request):
        """
        Admin view that displays TenantCreationForm and provisions the tenant.

        CHANGED: Now assigns tenantmanager role to newly created admin user.
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

                    # Assign tenantmanager role to the newly created admin user
                    roles.assign_role(
                        user=user,
                        role=TenancyRole.TENANT_MANAGER,
                        tenant=tenant,
                        assigned_by=request.user
                    )

                except TenantProvisioningError as exc:
                    messages.error(request, f"Failed to create tenant: {exc}")
                except Exception as exc:
                    messages.error(request, f"Unexpected error provisioning tenant: {exc}")
                else:
                    messages.success(
                        request,
                        _(
                            'Tenant "%(tenant)s" created and admin user "%(user)s" provisioned with tenant manager role. '
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
def get_tenant_admin_site_class():
    """
    Get the TenantAdminSite class to use.
    """
    custom_class = getattr(settings, 'TENANCY_TENANT_ADMIN_SITE_CLASS', None)
    if custom_class:
        return import_string(custom_class)
    return TenantAdminSite


def get_super_admin_site_class():
    """
    Get the SuperAdminSite class to use.
    """
    custom_class = getattr(settings, 'TENANCY_SUPER_ADMIN_SITE_CLASS', None)
    if custom_class:
        return import_string(custom_class)
    return SuperAdminSite


TenantAdminSiteClass = get_tenant_admin_site_class()
SuperAdminSiteClass = get_super_admin_site_class()

tenant_admin_site = TenantAdminSiteClass(name='tenant_admin')
super_admin_site = SuperAdminSiteClass(name='super_admin')


# Admin for the Tenant model
@admin.register(Tenant, site=super_admin_site)
class TenantAdmin(admin.ModelAdmin):
    """
    Tenant ModelAdmin for the super admin site.

    NOTE: This only registers on super_admin_site. Tenant model should NEVER
    appear in tenant_admin_site for security reasons.
    """
    list_display = ['name', 'domain', 'is_active', 'created_at', 'view_tenant_admin', 'id']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'domain']
    readonly_fields = ['created_at', 'updated_at', 'id']

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
        """Provides a direct link to the tenant's admin interface"""
        return format_html('<a href="http://{}/manage/" target="_blank">Open Tenant Admin</a>', obj.domain)

    view_tenant_admin.short_description = 'Tenant Admin'


# Admin for TenancyRole model
@admin.register(TenancyRole, site=super_admin_site)
class TenancyRoleAdmin(admin.ModelAdmin):
    """
    Admin interface for managing tenancy roles.

    Only accessible in super admin site.
    """
    list_display = ['user', 'role', 'tenant', 'assigned_at', 'assigned_by']
    list_filter = ['role', 'assigned_at']
    search_fields = ['user__username', 'user__email', 'tenant__name', 'tenant__domain']
    readonly_fields = ['assigned_at']

    fieldsets = (
        ('Role Assignment', {
            'fields': ('user', 'role', 'tenant')
        }),
        ('Audit Trail', {
            'fields': ('assigned_by', 'assigned_at'),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """
        Customize form to show helpful text and handle validation.
        """
        form = super().get_form(request, obj, **kwargs)

        # Add help text dynamically
        if 'tenant' in form.base_fields:
            form.base_fields['tenant'].help_text = (
                "Leave blank for tenantadmin role (system-wide access). "
                "Select a tenant for tenantmanager role (tenant-specific access)."
            )

        return form

    def save_model(self, request, obj, form, change):
        """
        Automatically set assigned_by to current user.
        """
        if not change:  # Only on creation
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


# =============================================================================
# DYNAMIC USER ADMIN GENERATOR
# =============================================================================

def create_dynamic_user_admin():
    """
    Dynamically creates a UserAdmin class based on the project's custom user model.
    """
    User = get_user_model()

    # Detect available fields
    user_fields = {f.name for f in User._meta.get_fields() if not f.many_to_many and not f.one_to_many}

    # Detect common Django user model fields
    has_username = 'username' in user_fields
    has_email = 'email' in user_fields
    has_first_name = 'first_name' in user_fields
    has_last_name = 'last_name' in user_fields
    has_tenant = 'tenant' in user_fields

    # Build list_display
    _list_display = []
    if has_username:
        _list_display.append('username')
    if has_email:
        _list_display.append('email')
    if has_first_name:
        _list_display.append('first_name')
    if has_last_name:
        _list_display.append('last_name')
    _list_display.extend(['is_active'])

    # Build search_fields
    _search_fields = []
    if has_username:
        _search_fields.append('username')
    if has_email:
        _search_fields.append('email')
    if has_first_name:
        _search_fields.append('first_name')
    if has_last_name:
        _search_fields.append('last_name')

    # Build list_filter
    _list_filter = ['is_active']
    if has_tenant:
        _list_filter.append('tenant')

    # Build fieldsets
    _fieldsets = []

    # Personal info section
    personal_fields = []
    if has_username:
        personal_fields.append('username')
    if has_email:
        personal_fields.append('email')
    if has_first_name:
        personal_fields.append('first_name')
    if has_last_name:
        personal_fields.append('last_name')
    if has_tenant:
        personal_fields.append('tenant')

    if personal_fields:
        _fieldsets.append((None, {'fields': personal_fields}))

    # Permissions section
    permissions_fields = ['is_active']
    if 'groups' in user_fields:
        permissions_fields.append('groups')
    if 'user_permissions' in user_fields:
        permissions_fields.append('user_permissions')

    _fieldsets.append((_('Permissions'), {'fields': permissions_fields}))

    # Important dates section
    important_dates_fields = []
    if 'last_login' in user_fields:
        important_dates_fields.append('last_login')
    if 'date_joined' in user_fields:
        important_dates_fields.append('date_joined')

    if important_dates_fields:
        _fieldsets.append((_('Important dates'), {'fields': important_dates_fields}))

    # Build add_fieldsets
    _add_fieldsets = []
    add_fields = []

    if has_username:
        add_fields.append('username')
    if has_email:
        add_fields.append('email')
    if has_tenant:
        add_fields.append('tenant')

    add_fields.extend(['password1', 'password2'])

    _add_fieldsets.append((None, {
        'classes': ('wide',),
        'fields': tuple(add_fields),
    }))

    class DynamicUserAdminBase(BaseUserAdmin):
        list_display = _list_display
        search_fields = _search_fields
        list_filter = _list_filter
        fieldsets = _fieldsets
        add_fieldsets = _add_fieldsets
        ordering = ['id']

        def get_form(self, request, obj=None, **kwargs):
            form = super().get_form(request, obj, **kwargs)
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
            return None

        def get_readonly_fields(self, request, obj=None):
            readonly = list(super().get_readonly_fields(request, obj) or [])
            if has_tenant and obj:
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


def register_user_admins():
    """
    Automatically register the dynamically generated user admin classes.
    """
    User = get_user_model()

    SuperUserAdmin = create_super_user_admin()
    TenantScopedUserAdmin = create_tenant_user_admin()

    super_admin_site.register(User, SuperUserAdmin)
    tenant_admin_site.register(User, TenantScopedUserAdmin)


# Call registration when this module is imported
register_user_admins()