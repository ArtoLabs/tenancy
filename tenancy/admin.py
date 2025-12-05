from django.contrib import admin
from django.contrib.admin import AdminSite
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.utils.translation import gettext as _
from .models import Tenant
from .forms import TenantCreationForm
from .services import TenantProvisioner, TenantProvisioningError


class TenantAdminSite(AdminSite):
    site_header = "Tenant Administration"
    site_title = "Tenant Admin"
    index_title = "Welcome to your admin panel"

    def has_permission(self, request):
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
        app_list = super().get_app_list(request)
        for app in app_list:
            app['models'] = [m for m in app['models'] if m.get('object_name') != 'Tenant']
        return app_list


class SuperAdminSite(AdminSite):
    index_template = "admin/tenancy/super_index.html"
    site_header = "Super Administration"
    site_title = "Super Admin"
    index_title = "System Management"

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('create-tenant/', self.admin_view(self.create_tenant_view), name='create-tenant'),
        ]
        return custom_urls + urls

    def create_tenant_view(self, request):
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

        context = {**self.each_context(request), 'title': 'Create Tenant', 'form': form}
        return render(request, 'admin/tenancy/create_tenant.html', context)


# Instantiate admin sites
tenant_admin_site = TenantAdminSite(name='tenant_admin')
super_admin_site = SuperAdminSite(name='super_admin')


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
