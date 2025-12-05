from django.db import models
from django.forms.models import model_to_dict
from .models import Tenant
from .managers import TenantManager
from django.conf import settings

# ========================================================
# Tenant Mixin for models
# ========================================================
class TenantMixin(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_set',
        null=True,
        blank=True,
    )
    objects = TenantManager()

    class Meta:
        abstract = True

    @classmethod
    def _is_tenant_model(cls):
        return hasattr(cls, 'tenant')

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            from .context import get_current_tenant
            current_tenant = get_current_tenant()
            if current_tenant is None:
                raise ValueError(f"Cannot save {self.__class__.__name__} without an active tenant.")
            self.tenant = current_tenant
        super().save(*args, **kwargs)


# ========================================================
# Tenant mixin for ModelAdmin
# ========================================================
class TenantAdminMixin:
    """Use for any ModelAdmin in tenant_admin_site"""
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tenant = getattr(request, 'tenant', None)
        if tenant and hasattr(qs.model, 'tenant'):
            return qs.filter(tenant=tenant)
        return qs

    def save_model(self, request, obj, form, change):
        if hasattr(obj, 'tenant') and not change and not getattr(obj, 'tenant_id', None):
            obj.tenant = getattr(request, 'tenant', None)
        super().save_model(request, obj, form, change)

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


# ========================================================
# TenantAdminMixin for User (optional)
# ========================================================
class TenantUserAdminMixin(TenantAdminMixin):
    """For tenant-scoped users"""
    pass


# ========================================================
# Clone mixin for tenant template data
# ========================================================
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
