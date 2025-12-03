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
        if not (request.user.is_active and request.user.is_staff):
            return False
        if request.user.is_superuser:
            return True
        return hasattr(request, 'tenant') and request.tenant is not None

    def get_app_list(self, request):
        """
        Remove the Tenant model from app list for tenant site to avoid leakage.
        """
        app_list = super().get_app_list(request)
        for app in app_list:
            # filter out Tenant model from the returned models
            app['models'] = [m for m in app['models'] if m.get('object_name') != 'Tenant']
        return app_list


class SuperAdminSite(AdminSite):
    """
    Site for managing system-wide objects such as Tenant model and creating tenants.
    """
    index_template = "tenancy/admin/super_index.html"
    site_header = "Super Administration"
    site_title = "Super Admin"
    index_title = "System Management"

    def has_permission(self, request):
        # Strict: only superusers on main domain (or without tenant context)
        return request.user.is_active and request.user.is_superuser and (
            not hasattr(request, 'tenant') or request.tenant is None
        )

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
                    'schema_name': form.cleaned_data['schema_name'],
                    'is_active': form.cleaned_data.get('is_active', True),
                }
                admin_data = {
                    'username': form.cleaned_data['admin_username'],
                    'email': form.cleaned_data['admin_email'],
                    'password': form.cleaned_data['admin_password'],
                }
                try:
                    tenant, user = TenantProvisioner.create_tenant(tenant_data, admin_data, run_migrations=False)
                except TenantProvisioningError as exc:
                    messages.error(request, f"Failed to create tenant: {exc}")
                except Exception as exc:
                    messages.exception(request, f"Unexpected error provisioning tenant: {exc}")
                else:
                    messages.success(
                        request,
                        _(
                            'Tenant "%(tenant)s" created and admin user "%(user)s" provisioned. '
                            'Tenant admin login: http://%(domain)s/manage/'
                        ) % {'tenant': tenant.name, 'user': user.username, 'domain': tenant.domain}
                    )
                    # Redirect to tenant change list in super admin
                    return redirect('admin:tenancy_tenant_changelist')
        else:
            form = TenantCreationForm()

        context = {
            **self.each_context(request),
            'title': 'Create Tenant',
            'form': form,
        }
        # Render a simple admin form template (create this template in templates/admin/create_tenant.html)
        return render(request, 'admin/tenancy/create_tenant.html', context)


# instantiate the admin sites
tenant_admin_site = TenantAdminSite(name='tenant_admin')
super_admin_site = SuperAdminSite(name='super_admin')


@admin.register(Tenant, site=super_admin_site)
class TenantAdmin(admin.ModelAdmin):
    """
    Simple Tenant ModelAdmin for the super admin (no provisioning logic here).
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

    def view_tenant_admin(self, obj):
        return format_html('<a href="http://{}/manage/" target="_blank">Open Tenant Admin</a>', obj.domain)

    view_tenant_admin.short_description = 'Tenant Admin'


# Register User on super admin so superusers can manage system users
super_admin_site.register(User, BaseUserAdmin)


# TenantAdminMixin for tenant-scoped models (register your tenant models in tenant_admin_site)
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
        if hasattr(obj, 'tenant') and not getattr(obj, 'tenant_id', None):
            obj.tenant = request.tenant
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return hasattr(request, 'tenant') and request.tenant is not None

    def get_exclude(self, request, obj=None):
        exclude = super().get_exclude(request, obj) or []
        if hasattr(self.model, 'tenant'):
            return list(exclude) + ['tenant']
        return exclude
