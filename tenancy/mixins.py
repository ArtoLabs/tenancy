from django.db import models
from django.forms.models import model_to_dict
from django.contrib import admin
from django.utils.html import format_html
from .managers import TenantManager
from .models import Tenant


class TenantUserMixin(models.Model):
    """
    Mixin for user models that belong to a tenant.
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
    Mixin for any tenant-scoped model.
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

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['tenant']),
        ]

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from .context import get_current_tenant
            current_tenant = get_current_tenant()
            if current_tenant is None:
                raise ValueError(
                    f"Cannot save {self.__class__.__name__} without an active tenant."
                )
            self.tenant = current_tenant
        super().save(*args, **kwargs)

    @classmethod
    def _is_tenant_model(cls):
        return hasattr(cls, 'tenant')


class CloneForTenantMixin:
    CLONE_EXCLUDE_FIELDS = ("id", "pk")

    @classmethod
    def get_template_queryset(cls):
        return cls.objects.filter(tenant__isnull=True)

    def clone_for_tenant(self, new_tenant_id, overrides=None):
        overrides = overrides or {}
        data = model_to_dict(self, exclude=self.CLONE_EXCLUDE_FIELDS)
        data["tenant_id"] = new_tenant_id
        data.update(overrides)
        return self.__class__.objects.create(**data)

    @classmethod
    def clone_defaults_for_new_tenant(cls, new_tenant_id):
        new_instances = []
        for template in cls.get_template_queryset():
            new_instances.append(template.clone_for_tenant(new_tenant_id))
        return new_instances


# ---------------------------
# Admin Mixins
# ---------------------------

class TenantAdminMixin:
    """
    Use for any ModelAdmin that should be tenant-scoped.
    """
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request, 'tenant') and request.tenant and hasattr(qs.model, 'tenant'):
            return qs.filter(tenant=request.tenant)
        return qs

    def save_model(self, request, obj, form, change):
        if hasattr(obj, 'tenant') and not change and not getattr(obj, 'tenant_id', None):
            obj.tenant = getattr(request, 'tenant', None)
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        if not request.user.is_active or not request.user.is_staff:
            return False
        if not hasattr(request, 'tenant') or request.tenant is None:
            return False
        if request.user.is_superuser:
            return True
        return getattr(request.user, 'tenant', None) == getattr(request, 'tenant', None)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request, obj)

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if hasattr(self.model, 'tenant') and 'tenant' not in exclude:
            exclude.append('tenant')
        return exclude

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        model = db_field.remote_field.model
        if hasattr(model, "_is_tenant_model") and model._is_tenant_model():
            tenant = getattr(request, 'tenant', None)
            if tenant:
                kwargs["queryset"] = model.objects.filter(tenant=tenant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TenantUserAdminMixin:
    """
    Use this mixin for the superuser admin to automatically show tenant column.
    """
    def tenant_display(self, obj):
        if hasattr(obj, "tenant") and obj.tenant:
            return f"{obj.tenant.id} – {obj.tenant.name}"
        return "-"
    tenant_display.short_description = "Tenant"

    def get_list_display(self, request):
        base = list(super().get_list_display(request))
        if "tenant_display" not in base:
            base.append("tenant_display")
        return base

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if hasattr(self.model, "tenant") and "tenant" not in readonly:
            readonly.append("tenant")
        return readonly
