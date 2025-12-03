from django.db import models
from django.utils.translation import gettext_lazy as _
#from django.contrib.auth.models import AbstractUser


class Tenant(models.Model):
    """
    Core tenant model representing a single tenant in the system.
    """
    name = models.CharField(
        max_length=255,
        verbose_name=_('Tenant Name'),
        help_text=_('The name of the tenant organization')
    )
    domain = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        verbose_name=_('Domain'),
        help_text=_('Primary domain for this tenant (e.g., acme.example.com)')
    )
    schema_name = models.CharField(
        max_length=63,
        unique=True,
        db_index=True,
        verbose_name=_('Schema Name'),
        help_text=_('Internal identifier for the tenant')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Active'),
        help_text=_('Whether this tenant is currently active')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    class Meta:
        verbose_name = _('Tenant')
        verbose_name_plural = _('Tenants')
        ordering = ['name']
        indexes = [
            models.Index(fields=['domain']),
            models.Index(fields=['schema_name']),
        ]

    def __str__(self):
        return f"{self.name} ({self.domain})"

    def activate(self):
        """
        Activate this tenant in the current thread context.
        """
        from .context import set_current_tenant
        set_current_tenant(self)

    def deactivate(self):
        """
        Deactivate the current tenant context.
        """
        from .context import clear_current_tenant
        clear_current_tenant()


# class TenantUser(AbstractUser):
#     tenant = models.ForeignKey(
#         Tenant,
#         null=True,
#         blank=True,
#         on_delete=models.PROTECT,
#         related_name="users"
#     )