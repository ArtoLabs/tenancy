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
from .mixins import TenantAdminMixin

User = get_user_model()


# ========================================================
# Tenant Admin Site (/manage/) - Tenant-scoped admin
# ========================================================
class TenantAdminSite(AdminSite):
    site_header = "Tenant Administration"
    site_title = "Tenant Admin"
    index_title = "Welcome to your admin panel"

    def has_permission(self, request):
        """Allow staff users who belong to the current tenant"""
        if not request.user.is_active:
            return False
        if request.user.is_superuser:
            return True
        if not request.user.is_staff:
            return False

        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return False

        if hasattr(request.user, 'tenant'):
            return request.user.tenant == tenant

        return True

    def get_app_list(self, request):
        """Remove Tenant model from tenant admin view"""
        app_list = super().get_app_list(request)
        for app in app_list:
            app['models'] = [m for m in app['models'] if m.get('object_name') != 'Tenant']
        return app_list


tenant_admin_site = TenantAdminSite(name='tenant_admin')


# Tenant User admin (tenant-scoped)
@admin.register(User, site=tenant_admin_site)
class TenantUserAdmin(BaseUserAdmin, TenantAdminMixin):
    """
    Shows only users belonging to the current tenant.
    """
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = getattr(request, 'tenant', None)
        if tenant and hasattr(User, 'tenant'):
            return qs.filter(tenant=tenant)
        return qs

    def save_model(self, request, obj, form, change):
        if hasattr(obj, 'tenant') and not change and not getattr(obj, 'tenant_id', None):
            obj.tenant = getattr(request, 'tenant', None)
        super().save_model(request, obj, form, change)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Hide tenant field
        if hasattr(User, 'tenant'):
            fieldsets = [
                (name, {**data, 'fields': tuple(f for f in data.get('fields', ()) if f != 'tenant')})
                for name, data in fieldsets
            ]
        return fieldsets


# ========================================================
# Super Admin Site (/admin/) - Full system admin
# ========================================================
class SuperAdminSite(AdminSite):
    site_header = "Super Administration"
    site_title = "Super Admin"
    index_title = "System Management"
    index_template = "admin/tenancy/super_index.html"

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('create-tenant/', self.admin_view(self.create_tenant_view), name='create-tenant'),
        ]
        return custom_urls + urls

    def create_tenant_view(self, request):
        """Form to create a new tenant"""
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
                    messages.error(request, f"Unexpected error: {exc}")
                else:
                    messages.success(
                        request,
                        _('Tenant "%(tenant)s" created and admin user "%(user)s" provisioned. '
                          'Tenant admin login: http://%(domain)s/manage/') %
                        {'tenant': tenant.name, 'user': user.username, 'domain': tenant.domain}
                    )
                    return redirect('admin:index')
        else:
            form = TenantCreationForm()

        context = {**self.each_context(request), 'title': 'Create Tenant', 'form': form}
        return render(request, 'admin/tenancy/create_tenant.html', context)


super_admin_site = SuperAdminSite(name='super_admin')


# Tenant model admin for super admin
@admin.register(Tenant, site=super_admin_site)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'domain', 'is_active', 'created_at', 'view_tenant_admin']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'domain']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {'fields': ('name', 'domain')}),
        ('Status', {'fields': ('is_active',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def view_tenant_admin(self, obj):
        return format_html('<a href="http://{}/manage/" target="_blank">Open Tenant Admin</a>', obj.domain)

    view_tenant_admin.short_description = 'Tenant Admin'


# Superuser User admin for super admin
@admin.register(User, site=super_admin_site)
class SuperUserUserAdmin(BaseUserAdmin):
    """
    Shows all users for superuser with tenant display.
    """
    def tenant_display(self, obj):
        if hasattr(obj, "tenant") and obj.tenant:
            return f"{obj.tenant.id} – {obj.tenant.name}"
        return "-"
    tenant_display.short_description = "Tenant"

    def get_list_display(self, request):
        base = list(super().get_list_display(request))
        if hasattr(User, "tenant") and "tenant_display" not in base:
            base.append("tenant_display")
        return base

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if hasattr(User, "tenant") and "tenant" not in readonly:
            readonly.append("tenant")
        return readonly

