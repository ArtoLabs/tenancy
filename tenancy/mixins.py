from django.db import models
from django.forms.models import model_to_dict

from .managers import TenantManager
from .models import Tenant


class TenantUserMixin(models.Model):
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
    Mixin to add tenant support to any Django model.

    Usage:
        class MyModel(TenantMixin):
            name = models.CharField(max_length=100)
            # ... other fields
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_set',
        verbose_name='Tenant',
        db_index=True,
        null=True,  # ← Added: Allows NULL in database
        blank=True,  # ← Added: Allows blank in forms
    )

    objects = TenantManager()

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


class CloneForTenantMixin:
    CLONE_EXCLUDE_FIELDS = ("id", "pk")

    @classmethod
    def get_template_queryset(cls):
        """
        Returns a queryset of template rows.
        Default: all rows with tenant=None
        """
        return cls.objects.filter(tenant__isnull=True)

    def clone_for_tenant(self, new_tenant_id, overrides=None):
        overrides = overrides or {}
        data = model_to_dict(self, exclude=self.CLONE_EXCLUDE_FIELDS)
        data["tenant_id"] = new_tenant_id
        data.update(overrides)
        return self.__class__.objects.create(**data)

    @classmethod
    def clone_defaults_for_new_tenant(cls, new_tenant_id):
        print ("Cloning!")
        new_instances = []
        for template in cls.get_template_queryset():
            print("Creating new instance!")
            new_instances.append(template.clone_for_tenant(new_tenant_id))
        return new_instances


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


    
class TenantSuperUserAdminMixin:
    readonly_fields = ('tenant',)

    def tenant_display(self, obj):
        if hasattr(obj, 'tenant') and obj.tenant:
            return f"{obj.tenant.id} – {obj.tenant.name}"
        return "-"
    tenant_display.short_description = "Tenant"

    def get_list_display(self, request):
        base = list(super().get_list_display(request))
        if 'tenant_display' not in base:
            base.append('tenant_display')
        return base
