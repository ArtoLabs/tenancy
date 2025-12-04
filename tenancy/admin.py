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

User = get_user_model()


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


class TenantAdminMixin:
    """
    Use this mixin for any ModelAdmin that should be tenant-scoped and appear in TenantAdminSite.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request, 'tenant') and request.tenant:
            if hasattr(qs.model, 'tenant'):
                return qs.filter(tenant=request.tenant)
        return qs

    def save_model(self, request, obj, form, change):
        if hasattr(obj, 'tenant') and not change:
            if not getattr(obj, 'tenant_id', None):
                obj.tenant = request.tenant
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        if not request.user.is_active or not request.user.is_staff:
            return False
        if not hasattr(request, 'tenant') or request.tenant is None:
            return False
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'tenant'):
            return request.user.tenant == request.tenant
        return True

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if hasattr(self.model, 'tenant') and 'tenant' not in exclude:
            exclude.append('tenant')
        return exclude

    # 🔥 The missing piece (THIS FIXES YOUR PROBLEM)
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        model = db_field.remote_field.model

        # Only apply tenant filtering to tenant-aware models
        if hasattr(model, "_is_tenant_model") and model._is_tenant_model():
            tenant = getattr(request, 'tenant', None)
            if tenant:
                kwargs["queryset"] = model.objects.filter(tenant=tenant)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)



@admin.register(User, site=tenant_admin_site)
class TenantUserAdmin(BaseUserAdmin):
    """
    User admin for tenant site - shows only users belonging to current tenant
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request, 'tenant') and request.tenant:
            if hasattr(User, 'tenant'):
                return qs.filter(tenant=request.tenant)
        return qs

    def save_model(self, request, obj, form, change):
        if hasattr(obj, 'tenant') and not change:
            if not getattr(obj, 'tenant_id', None):
                obj.tenant = request.tenant
        super().save_model(request, obj, form, change)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Hide tenant field if it exists
        if hasattr(User, 'tenant'):
            fieldsets = list(fieldsets)
            for name, data in fieldsets:
                if 'fields' in data:
                    fields = list(data['fields'])
                    if 'tenant' in fields:
                        fields.remove('tenant')
                        data['fields'] = tuple(fields)
        return fieldsets


# @admin.register(User, site=super_admin_site)
# class SuperUserUserAdmin(BaseUserAdmin):
#
#     list_display = BaseUserAdmin.list_display + ('tenant_display',)
#
#     def tenant_display(self, obj):
#         if hasattr(obj, "tenant") and obj.tenant:
#             return f"{obj.tenant.id} – {obj.tenant.name}"
#         return "-"
#     tenant_display.short_description = "Tenant"
#
#     def get_readonly_fields(self, request, obj=None):
#         readonly = list(super().get_readonly_fields(request, obj))
#         if hasattr(User, "tenant") and "tenant" not in readonly:
#             readonly.append("tenant")
#         return readonly


# --- DEBUGGING PATCH: drop this in your tenancy/admin.py ---

from django.contrib import admin as django_admin
from django.http import HttpResponse

# Print registrations at import time so we know what's registered
print("=== tenancy.admin import time debug ===")
print("Default admin.site registered models:", sorted([m.__name__ for m in django_admin.site._registry.keys()]))
print("super_admin_site registered models:", sorted([m.__name__ for m in super_admin_site._registry.keys()]))
print("tenant_admin_site registered models:", sorted([m.__name__ for m in tenant_admin_site._registry.keys()]))
print("User model class:", User.__name__, "module:", getattr(User, '__module__', None))
print("Does User have tenant attribute at import:", hasattr(User, 'tenant'))
print("=======================================")


@admin.register(User, site=super_admin_site)
class SuperUserUserAdmin(BaseUserAdmin):
    """
    Debuggable UserAdmin for the super admin site.
    """

    # Keep the tenant column static (BaseUserAdmin usually defines list_display)
    # Note: BaseUserAdmin.list_display is a tuple; we build on it defensively.
    try:
        list_display = tuple(BaseUserAdmin.list_display) + ('tenant_display',)
    except Exception:
        # Fallback in case BaseUserAdmin changes shape in your environment
        list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'tenant_display')

    def __init__(self, *args, **kwargs):
        # This prints when Django constructs the ModelAdmin instance (at admin registration time).
        print(f"[DEBUG] SuperUserUserAdmin.__init__ called for model: {getattr(self, 'model', None)}")
        super().__init__(*args, **kwargs)

    def tenant_display(self, obj):
        # Called for each row when Django renders the column
        val = getattr(obj, 'tenant', None)
        print(f"[DEBUG] tenant_display called for user={getattr(obj, 'username', None)} tenant={val}")
        if val is None:
            return "-"
        # If Tenant has name or id show both if available
        name = getattr(val, 'name', None)
        tid = getattr(val, 'id', None)
        return f"{tid or '-'}{(' – ' + str(name)) if name else ''}"
    tenant_display.short_description = "Tenant"

    def get_queryset(self, request):
        print("[DEBUG] SuperUserUserAdmin.get_queryset called; request.user:", request.user)
        qs = super().get_queryset(request)
        try:
            print("[DEBUG] queryset count (unfiltered):", qs.count())
        except Exception as exc:
            print("[DEBUG] could not count queryset:", exc)
        return qs

    def changelist_view(self, request, extra_context=None):
        """
        This is a guaranteed hook that runs when the changelist is visited.
        Use it to print what Django will render.
        """
        print("=== SuperUserUserAdmin.changelist_view ===")
        print("request.user:", request.user, "is_superuser:", getattr(request.user, 'is_superuser', None))
        print("Admin object (self):", type(self), "model:", getattr(self, 'model', None))
        print("self.list_display:", getattr(self, 'list_display', None))
        # Show which ModelAdmin instance is registered for User on the super_admin_site
        registered = super_admin_site._registry.get(User)
        print("Registered ModelAdmin for User on super_admin_site:", type(registered), registered is self)
        # Also show default admin.site registration (maybe another registration is shadowing)
        registered_default = django_admin.site._registry.get(User)
        print("Registered ModelAdmin for User on default admin.site:", type(registered_default))
        print("===========================================")

        # Call through to normal changelist behaviour
        return super().changelist_view(request, extra_context=extra_context)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if hasattr(User, "tenant") and "tenant" not in readonly:
            readonly.append("tenant")
        print("[DEBUG] get_readonly_fields ->", readonly)
        return readonly

# If you previously also called `super_admin_site.register(User, SuperUserUserAdmin)` elsewhere,
# remove that second call. Having both decorator and register call will cause AlreadyRegistered.
print("[DEBUG] After decorating SuperUserUserAdmin, super_admin_site._registry contains:", super_admin_site._registry.get(User))
