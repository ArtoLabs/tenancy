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
        new_instances = []
        for template in cls.get_template_queryset():
            new_instances.append(template.clone_for_tenant(new_tenant_id))
        return new_instances

