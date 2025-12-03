from django.db import models
from .managers import TenantManager



class TenantUserMixin(models.Model):
    tenant = models.ForeignKey(
        "tenancy.Tenant",  # Use string reference
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
        "tenancy.Tenant",  # Use string reference
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