from django.db import models
from django.forms.models import model_to_dict
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .managers import TenantManager
from .models import Tenant
from .roles import roles


class TenantUserMixin(models.Model):
    """
    Mixin to add tenant field to custom user models.

    REMOVED: is_superadmin field (was redundant with tenancy roles)
    """
    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='users'
    )

    class Meta:
        abstract = True


class TenantMixin(models.Model):
    """
    Mixin to add tenant support and cloning capabilities to any Django model.
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_set',
        verbose_name='Tenant',
        db_index=True,
        null=True,
        blank=True,
    )

    objects = TenantManager()

    CLONE_EXCLUDE_FIELDS = ("id", "pk")

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['tenant']),
        ]

    def save(self, *args, **kwargs):
        """
        Override save to automatically set tenant from context if not set.
        """
        if not self.tenant_id:
            from .context import get_current_tenant
            current_tenant = get_current_tenant()

            if current_tenant is None:
                if getattr(settings, "TENANCY_BOOTSTRAP", False):
                    from .models import Tenant
                    current_tenant = Tenant.objects.first()
                    if current_tenant is None:
                        raise ValueError(
                            f"No tenants exist in the database to bootstrap {self.__class__.__name__}."
                        )
                else:
                    raise ValueError(
                        f"Cannot save {self.__class__.__name__} without an active tenant. "
                        "Either set the tenant explicitly or ensure middleware is active."
                    )

            self.tenant = current_tenant

        super().save(*args, **kwargs)

    @classmethod
    def _is_tenant_model(cls):
        """
        Helper method to identify if a model uses the tenant mixin.
        """
        return hasattr(cls, 'tenant')

    @classmethod
    def get_template_queryset(cls):
        """
        Returns a queryset of template rows for cloning (tenant=None).
        """
        try:
            template_tenant = Tenant.objects.order_by("id").first()
        except Tenant.DoesNotExist:
            return cls.objects.none()

        if template_tenant is None:
            return cls.objects.none()

        return cls.objects.filter(tenant=template_tenant)

    def clone_for_tenant(self, new_tenant_id, overrides=None):
        """
        Creates a copy of this object for a specific tenant.
        """
        overrides = overrides or {}

        data = model_to_dict(self, exclude=self.CLONE_EXCLUDE_FIELDS)

        tenant_instance = Tenant.objects.get(id=new_tenant_id)
        data["tenant"] = tenant_instance

        data.update(overrides)

        return self.__class__.objects.create(**data)

    @classmethod
    def clone_defaults_for_new_tenant(cls, new_tenant_id):
        """
        Clones all template objects for a new tenant.
        """
        new_instances = []
        for template in cls.get_template_queryset():
            new_instances.append(template.clone_for_tenant(new_tenant_id))
        return new_instances


class TenantAdminMixin:
    """
    Mixin for ModelAdmin classes that should be tenant-scoped in TenantAdminSite.

    CRITICAL: This mixin is ONLY for use with tenant_admin_site (the /manage site).
    It enforces that ONLY tenant managers can access these models.

    CHANGED: All permission methods now explicitly check for tenantmanager role
    and DENY access to tenantadmin role (they should use super_admin_site instead).
    """

    def get_queryset(self, request):
        """
        Filter queryset to current tenant's objects.
        This is the core of tenant isolation - tenant managers can only
        see objects belonging to their tenant, never objects from other tenants.
        """
        qs = super().get_queryset(request)
        if hasattr(request, 'tenant') and request.tenant:
            if hasattr(qs.model, 'tenant'):
                return qs.filter(tenant=request.tenant)
        return qs

    def save_model(self, request, obj, form, change):
        """
        Automatically set tenant on new objects.
        """
        if hasattr(obj, 'tenant') and not change:
            if not getattr(obj, 'tenant_id', None):
                obj.tenant = request.tenant
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        """
        Check if user has permission to access this module.

        CRITICAL CHANGE: This now ONLY allows tenant managers.
        Tenant admins should NOT have access to tenant-scoped admin.
        """
        if not request.user.is_active:
            return False

        if not hasattr(request, 'tenant') or request.tenant is None:
            return False

        # ONLY tenant managers can access tenant admin
        # Tenant admins should use super admin site instead
        return roles.is_tenant_manager(request.user, request.tenant)

    def has_add_permission(self, request):
        """
        Control add permission.

        CHANGED: Only tenant managers can add (if they have module permission).
        Tenant admins should NOT be adding via tenant admin site.
        """
        # Only allow if user has module permission (i.e., is tenant manager)
        if not self.has_module_permission(request):
            return False

        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        """
        Control delete permission.

        CHANGED: Only tenant managers can delete (if they have module permission).
        Tenant admins should NOT be deleting via tenant admin site.
        """
        # Only allow if user has module permission (i.e., is tenant manager)
        if not self.has_module_permission(request):
            return False

        return super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        """
        Control change permission.

        CHANGED: Only tenant managers can change.
        """
        return self.has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        """
        Control view permission.

        CHANGED: Only tenant managers can view.
        """
        return self.has_module_permission(request)

    def get_exclude(self, request, obj=None):
        """
        Exclude tenant field from forms - it's set automatically.
        """
        exclude = list(super().get_exclude(request, obj) or [])
        if hasattr(self.model, 'tenant') and 'tenant' not in exclude:
            exclude.append('tenant')
        return exclude

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Filter foreign key choices to only show objects from current tenant.
        """
        model = db_field.remote_field.model

        if hasattr(model, "_is_tenant_model") and model._is_tenant_model():
            tenant = getattr(request, 'tenant', None)
            if tenant:
                kwargs["queryset"] = model.objects.filter(tenant=tenant)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class SuperUserAdminMixin:
    """
    Mixin for ModelAdmin classes in SuperAdminSite.

    CRITICAL CHANGE: Added full permission checking to enforce that ONLY
    tenant admins can access models in the super admin site.

    This mixin now provides:
    - Tenant admin role verification for all permission checks
    - Cross-tenant visibility for system administrators
    - Tenant field display in list views
    """

    readonly_fields = ('tenant',)

    def has_module_permission(self, request):
        """
        Check if user has permission to access this module in super admin.

        NEW: Only tenant admins can access super admin modules.
        This is the critical permission check that was missing!
        """
        if not request.user.is_active:
            return False

        # ONLY tenant admins can access super admin site
        return roles.is_tenant_admin(request.user)

    def has_add_permission(self, request):
        """
        Control add permission in super admin.

        NEW: Only tenant admins can add objects.
        """
        if not self.has_module_permission(request):
            return False

        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        """
        Control change permission in super admin.

        NEW: Only tenant admins can change objects.
        """
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        """
        Control delete permission in super admin.

        NEW: Only tenant admins can delete objects.
        """
        if not self.has_module_permission(request):
            return False

        return super().has_delete_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        """
        Control view permission in super admin.

        NEW: Only tenant admins can view objects.
        """
        return self.has_module_permission(request)

    def tenant_display(self, obj):
        """
        Display tenant information in list view with ID and domain.
        """
        if hasattr(obj, 'tenant') and obj.tenant:
            return f"{obj.tenant.id} – {obj.tenant.domain}"
        return "-"

    tenant_display.short_description = "Tenant"

    def get_list_display(self, request):
        """
        Add tenant_display to list view.
        """
        base = list(super().get_list_display(request))
        if 'tenant_display' not in base:
            base.append('tenant_display')
        return base