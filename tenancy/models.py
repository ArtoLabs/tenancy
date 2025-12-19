from django.db import models
from django.utils.translation import gettext_lazy as _


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
        ]

    def __str__(self):
        if self.name and self.domain:
            return f"{self.name} ({self.domain})"
        else:
            return "Blank"

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


# Import TenancyRole from roles module to make it part of models
# This allows it to be included in migrations
from .roles import TenancyRole

__all__ = ['Tenant', 'TenancyRole']