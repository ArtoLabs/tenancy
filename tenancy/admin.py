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


class TenantAdminSite(AdminSite):
    """
    Admin site used by tenants (shown at tenant domain, e.g. tenant.example.com/manage/).
    This site should NEVER expose the Tenant model.
    """
    site_header = "Tenant Administration"
    site_title = "Tenant Admin"
    index_title = "Welcome to your admin panel"

    def has_permission(self, request):
        """
        Allow staff users who belong to the current tenant.

        Permission hierarchy:
        1. User must be active
        2. Superusers always have access (for debugging/support)
        3. Staff users must belong to the current tenant
        """
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

        SECURITY: Tenant managers should never see or manipulate the Tenant model itself.
        They should only manage their own tenant's data, not the tenant structure.
        """
        app_list = super().get_app_list(request)
        for app in app_list:
            # Filter out Tenant model from the returned models
            app['models'] = [m for m in app['models'] if m.get('object_name') != 'Tenant']
        return app_list


class SuperAdminSite(AdminSite):
    """
    Site for managing system-wide objects such as Tenant model and creating tenants.

    This admin site is for system administrators only and provides:
    - Tenant creation and management
    - Cross-tenant user management
    - System-wide configuration
    """
    index_template = "admin/tenancy/super_index.html"
    site_header = "Super Administration"
    site_title = "Super Admin"
    index_title = "System Management"

    def has_permission(self, request):
        """Only superusers can access super admin"""
        return request.user.is_active and request.user.is_superuser

    def get_urls(self):
        """
        Add custom URL for tenant creation workflow.
        This provides a user-friendly form for provisioning new tenants.
        """
        urls = super().get_urls()
        custom_urls = [
            path('create-tenant/', self.admin_view(self.create_tenant_view), name='create-tenant'),
        ]
        return custom_urls + urls

    def create_tenant_view(self, request):
        """
        Admin view that displays TenantCreationForm and provisions the tenant using TenantProvisioner.

        This view handles:
        1. Display of tenant creation form
        2. Validation of tenant data
        3. Creation of tenant via TenantProvisioner service
        4. Creation of initial admin user for the tenant
        5. Error handling and user feedback
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
# These are the two admin sites that will be used throughout the application:
# - super_admin_site: For system administrators at /admin
# - tenant_admin_site: For tenant managers at /manage
def get_tenant_admin_site_class():
    """
    Get the TenantAdminSite class to use.

    Checks settings.TENANCY_TENANT_ADMIN_SITE_CLASS for a custom class.
    Falls back to the default TenantAdminSite.
    """
    custom_class = getattr(settings, 'TENANCY_TENANT_ADMIN_SITE_CLASS', None)
    if custom_class:
        return import_string(custom_class)
    return TenantAdminSite


def get_super_admin_site_class():
    """
    Get the SuperAdminSite class to use.

    Checks settings.TENANCY_SUPER_ADMIN_SITE_CLASS for a custom class.
    Falls back to the default SuperAdminSite.
    """
    custom_class = getattr(settings, 'TENANCY_SUPER_ADMIN_SITE_CLASS', None)
    if custom_class:
        return import_string(custom_class)
    return SuperAdminSite

TenantAdminSiteClass = get_tenant_admin_site_class()
SuperAdminSiteClass = get_super_admin_site_class()

tenant_admin_site = TenantAdminSiteClass(name='tenant_admin')
super_admin_site = SuperAdminSiteClass(name='super_admin')


# tenant_admin_site = TenantAdminSite(name='tenant_admin')
# super_admin_site = SuperAdminSite(name='super_admin')


# Admin for the Tenant model included in this package
@admin.register(Tenant, site=super_admin_site)
class TenantAdmin(admin.ModelAdmin):
    """
    Simple Tenant ModelAdmin for the super admin (no provisioning logic here).

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


# =============================================================================
# DYNAMIC USER ADMIN GENERATOR
# =============================================================================
#
# This section implements the core feature of the tenancy package: automatic
# detection and registration of user admin classes.
#
# WHY THIS IS NECESSARY:
# - Each Django project defines its own custom User model with different fields
# - We can't hardcode a UserAdmin because we don't know what fields exist
# - Projects shouldn't have to write their own UserAdmin (plug-and-play goal)
# - We need TWO different UserAdmin classes (one for each admin site)
#
# HOW IT WORKS:
# 1. Inspect the project's User model using get_user_model()
# 2. Detect which fields exist (username, email, tenant, etc.)
# 3. Dynamically build admin configuration (list_display, fieldsets, etc.)
# 4. Create TWO admin classes with different behaviors
# 5. Auto-register both classes when this module loads
#
# =============================================================================

def create_dynamic_user_admin():
    """
    Dynamically creates a UserAdmin class based on the project's custom user model.

    This is the BASE admin class that both TenantScopedUserAdmin and SuperUserAdmin
    will inherit from. It contains all the field detection logic.

    STRATEGY:
    1. Get the project's User model (we don't know what it is at package design time)
    2. Inspect its fields using Django's meta API
    3. Detect common Django user fields (username, email, first_name, etc.)
    4. Build appropriate admin configuration based on what fields exist
    5. Return a class (not an instance) that can be subclassed

    WHY USE UNDERSCORED VARIABLES (_list_display, etc.):
    Python class definitions create their own scope. Variables defined in the
    function scope (like list_display) are not accessible inside the class body.
    By using underscored names (_list_display) in the function scope and then
    assigning them to class attributes, we bridge this scope gap.
    """
    User = get_user_model()

    # Detect available fields using Django's meta API
    # We exclude many-to-many and reverse relations as they're handled differently
    user_fields = {f.name for f in User._meta.get_fields() if not f.many_to_many and not f.one_to_many}

    # Detect common Django user model fields
    # These may or may not exist depending on the project's User model
    has_username = 'username' in user_fields
    has_email = 'email' in user_fields
    has_first_name = 'first_name' in user_fields
    has_last_name = 'last_name' in user_fields
    has_tenant = 'tenant' in user_fields  # From TenantUserMixin

    # Build list_display - what columns appear in the user list view
    # Start with an empty list and conditionally add fields that exist
    _list_display = []
    if has_username:
        _list_display.append('username')
    if has_email:
        _list_display.append('email')
    if has_first_name:
        _list_display.append('first_name')
    if has_last_name:
        _list_display.append('last_name')
    # Always show staff and active status - these are critical for admin
    _list_display.extend(['is_staff', 'is_active'])

    # Build search_fields - what fields can be searched in the admin
    # Only add text fields that make sense to search
    _search_fields = []
    if has_username:
        _search_fields.append('username')
    if has_email:
        _search_fields.append('email')
    if has_first_name:
        _search_fields.append('first_name')
    if has_last_name:
        _search_fields.append('last_name')

    # Build list_filter - sidebar filters in the user list view
    # Start with standard permission flags
    _list_filter = ['is_staff', 'is_superuser', 'is_active']
    if has_tenant:
        # Add tenant filter if the user model has a tenant field
        _list_filter.append('tenant')

    # Build fieldsets - how fields are grouped in the user edit form
    # This is the most complex part as we need to intelligently group related fields
    _fieldsets = []

    # Personal info section - basic user identification fields
    personal_fields = []
    if has_username:
        personal_fields.append('username')
    if has_email:
        personal_fields.append('email')
    # Group name fields together if they exist
    if has_first_name or has_last_name:
        if has_first_name:
            personal_fields.append('first_name')
        if has_last_name:
            personal_fields.append('last_name')

    # Add tenant field to personal info if it exists
    # Positioning tenant here (rather than in a separate section) keeps it
    # prominent and near other identifying information
    if has_tenant:
        personal_fields.append('tenant')

    # Only create the personal info fieldset if we have fields for it
    if personal_fields:
        _fieldsets.append((None, {'fields': personal_fields}))

    # Permissions section - controls what the user can do
    permissions_fields = ['is_active', 'is_staff', 'is_superuser']
    if 'groups' in user_fields:
        permissions_fields.append('groups')
    if 'user_permissions' in user_fields:
        permissions_fields.append('user_permissions')

    _fieldsets.append((_('Permissions'), {'fields': permissions_fields}))

    # Important dates section - audit trail fields
    important_dates_fields = []
    if 'last_login' in user_fields:
        important_dates_fields.append('last_login')
    if 'date_joined' in user_fields:
        important_dates_fields.append('date_joined')

    if important_dates_fields:
        _fieldsets.append((_('Important dates'), {'fields': important_dates_fields}))

    # Build add_fieldsets - fields shown when CREATING a new user
    # This is different from regular fieldsets because:
    # 1. We need password1/password2 for password confirmation
    # 2. We need fewer fields (just essentials)
    # 3. Some fields (like last_login) don't make sense for new users
    _add_fieldsets = []
    add_fields = []

    if has_username:
        add_fields.append('username')
    if has_email:
        add_fields.append('email')
    if has_tenant:
        add_fields.append('tenant')

    # Password fields - Django's UserAdmin expects these specific field names
    add_fields.extend(['password1', 'password2'])

    # Use tuple for fields as Django's admin expects it
    _add_fieldsets.append((None, {
        'classes': ('wide',),  # Makes the form wider for better UX
        'fields': tuple(add_fields),
    }))

    # Create the base admin class with all detected configuration
    # This class inherits from Django's UserAdmin which provides password
    # change functionality and other user-specific admin features
    class DynamicUserAdminBase(BaseUserAdmin):
        # Assign all the dynamically built configuration
        list_display = _list_display
        search_fields = _search_fields
        list_filter = _list_filter
        fieldsets = _fieldsets
        add_fieldsets = _add_fieldsets
        ordering = ['id']  # Default ordering for user list

        def get_form(self, request, obj=None, **kwargs):
            """
            Customize the form used in the admin.

            This is primarily to ensure the password field shows appropriate
            help text explaining that raw passwords aren't stored.
            """
            form = super().get_form(request, obj, **kwargs)
            # Ensure password field uses the proper widget and help text
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

    This admin class is used in the TENANT admin site (/manage).

    KEY BEHAVIORS:
    1. Shows ONLY users belonging to the current tenant
    2. Automatically assigns tenant to newly created users
    3. Makes tenant field readonly (can't move users between tenants)
    4. Inherits all dynamic field detection from DynamicUserAdminBase

    WHY INHERIT FROM BOTH TenantAdminMixin AND DynamicUserAdminBase:
    - DynamicUserAdminBase: Provides field detection and basic admin config
    - TenantAdminMixin: Provides tenant filtering and scoping logic

    INHERITANCE ORDER MATTERS:
    TenantAdminMixin comes first so its methods take precedence, but we
    still want to use DynamicUserAdminBase's configuration.
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
            """
            Filter queryset to only show users from the current tenant.

            We call super(DynamicUserAdminBase, self) to skip TenantAdminMixin's
            get_queryset and go straight to the base UserAdmin queryset, then
            apply tenant filtering ourselves. This gives us more control.
            """
            qs = super(DynamicUserAdminBase, self).get_queryset(request)
            if has_tenant and hasattr(request, 'tenant') and request.tenant:
                return qs.filter(tenant=request.tenant)
            return qs

        def save_model(self, request, obj, form, change):
            """
            Automatically set tenant when creating new users.

            When a tenant manager creates a user, we automatically assign
            their tenant to the new user. They shouldn't be able to create
            users for other tenants.
            """
            if has_tenant and not change:  # Only on creation, not updates
                if not getattr(obj, 'tenant_id', None):
                    if hasattr(request, 'tenant') and request.tenant:
                        obj.tenant = request.tenant
            super().save_model(request, obj, form, change)

        def get_exclude(self, request, obj=None):
            """
            Don't exclude tenant field - we want it visible but readonly.

            TenantAdminMixin normally excludes the tenant field, but for
            users we want to show it so managers can see which tenant the
            user belongs to.
            """
            return None

        def get_readonly_fields(self, request, obj=None):
            """
            Make tenant readonly when editing existing users.

            When editing an existing user, the tenant field should be readonly.
            When creating a new user, it can be editable (or auto-set).
            """
            readonly = list(super().get_readonly_fields(request, obj) or [])
            if has_tenant and obj:  # obj exists = editing, not creating
                if 'tenant' not in readonly:
                    readonly.append('tenant')
            return readonly

    return TenantScopedUserAdmin


def create_super_user_admin():
    """
    Creates a super admin user admin that shows all users with tenant display.

    This admin class is used in the SUPER admin site (/admin).

    KEY BEHAVIORS:
    1. Shows ALL users from ALL tenants (no filtering)
    2. Displays tenant information prominently (via SuperUserAdminMixin)
    3. Makes tenant field readonly (superusers can change via direct DB if needed)
    4. Inherits all dynamic field detection from DynamicUserAdminBase

    WHY THIS IS SEPARATE FROM TenantScopedUserAdmin:
    - Different filtering behavior (all users vs. tenant users)
    - Different display (shows tenant column)
    - Different use case (system admin vs. tenant manager)
    """
    DynamicUserAdminBase = create_dynamic_user_admin()
    User = get_user_model()
    has_tenant = hasattr(User, 'tenant')

    class SuperUserAdmin(SuperUserAdminMixin, DynamicUserAdminBase):
        """
        User admin for super admin site - shows all users with tenant information.

        SuperUserAdminMixin adds:
        - tenant_display column in list view (shows "ID - Name")
        - Makes tenant field readonly
        """

        def get_readonly_fields(self, request, obj=None):
            """
            Make tenant field readonly in super admin.

            Even superusers should use the tenant provisioning workflow
            rather than arbitrarily changing user tenants. This prevents
            accidental data leakage or confusion.
            """
            readonly = list(super().get_readonly_fields(request, obj) or [])
            if has_tenant and 'tenant' not in readonly:
                readonly.append('tenant')
            return readonly

    return SuperUserAdmin


# =============================================================================
# AUTO-REGISTRATION
# =============================================================================
#
# This function is called at the end of this module to automatically register
# the dynamically generated user admin classes.
#
# WHY THIS HAPPENS AT MODULE LOAD:
# Django's admin autodiscover runs when the application starts. By calling
# register_user_admins() at module level, we ensure the User model is
# registered before any project code tries to access it.
#
# WHY WE CREATE TWO ADMIN CLASSES:
# We need different behavior for the two admin sites:
# - SuperUserAdmin: Shows all users, adds tenant column
# - TenantScopedUserAdmin: Shows only tenant's users, filters automatically
#
# =============================================================================

def register_user_admins():
    """
    Automatically register the dynamically generated user admin classes
    on both admin sites.

    This function:
    1. Gets the project's User model
    2. Creates two admin classes (super and tenant-scoped)
    3. Registers them on their respective admin sites

    IMPORTANT: This is called at module import time, so it runs when
    Django starts up, before any requests are processed.
    """
    User = get_user_model()

    # Create the dynamic admin classes
    # Each call to create_*_admin() returns a new CLASS (not instance)
    SuperUserAdmin = create_super_user_admin()
    TenantScopedUserAdmin = create_tenant_user_admin()

    # Register on super admin site (accessible at /admin)
    super_admin_site.register(User, SuperUserAdmin)

    # Register on tenant admin site (accessible at /manage)
    tenant_admin_site.register(User, TenantScopedUserAdmin)


# Call registration when this module is imported
# This is the "magic" that makes everything work without requiring
# the project to manually register the User model
register_user_admins()
