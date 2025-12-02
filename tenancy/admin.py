from django.contrib import admin
from django.contrib.admin import AdminSite
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
        Only allow access if user is staff AND a tenant context exists.
        """
        return request.user.is_active and (request.user.is_staff or request.user.is_superuser) and hasattr(request, 'tenant') and request.tenant is not None


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
        return request.user.is_active and request.user.is_superuser and (not hasattr(request, 'tenant') or request.tenant is None)


# Create the custom admin sites
tenant_admin_site = TenantAdminSite(name='tenant_admin')
super_admin_site = SuperAdminSite(name='super_admin')


@admin.register(Tenant, site=super_admin_site)
class TenantAdmin(admin.ModelAdmin):
    """
    Admin interface for managing tenants - only in super admin.
    """
    list_display = ['name', 'domain', 'schema_name', 'is_active', 'created_at']
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