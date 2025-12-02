from django.db import models
from .context import get_current_tenant


class TenantQuerySet(models.QuerySet):
    """
    Custom QuerySet that automatically filters by the current tenant.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant_filtering_disabled = False

    def filter_by_tenant(self, tenant=None):
        """
        Explicitly filter by a specific tenant.

        Args:
            tenant: Tenant instance or None to use current tenant
        """
        if tenant is None:
            tenant = get_current_tenant()

        if tenant is None:
            return self.none()

        return self.filter(tenant=tenant)

    def all_tenants(self):
        """
        Disable automatic tenant filtering for this queryset.
        Use with caution - only in admin or system-level operations.
        """
        qs = self._chain()
        qs._tenant_filtering_disabled = True
        return qs

    def _chain(self):
        """
        Override _chain to preserve the filtering state.
        """
        clone = super()._chain()
        clone._tenant_filtering_disabled = self._tenant_filtering_disabled
        return clone

    def _fetch_all(self):
        """
        Apply tenant filtering before fetching results.
        """
        if not self._tenant_filtering_disabled and self.model._is_tenant_model():
            current_tenant = get_current_tenant()

            # Only auto-filter if a tenant is set and not already filtered
            if current_tenant is not None:
                # Check if already filtered by tenant
                if not self._has_tenant_filter():
                    self.query.add_q(models.Q(tenant=current_tenant))

        super()._fetch_all()

    def _has_tenant_filter(self):
        """
        Check if the queryset already has a tenant filter.
        """
        # Simple check to avoid duplicate filtering
        where = self.query.where
        if hasattr(where, 'children'):
            for child in where.children:
                if hasattr(child, 'lhs') and hasattr(child.lhs, 'target'):
                    if child.lhs.target.name == 'tenant':
                        return True
        return False


class TenantManager(models.Manager):
    """
    Custom Manager that uses TenantQuerySet for automatic tenant filtering.
    """

    def get_queryset(self):
        """
        Return a TenantQuerySet instance.
        """
        return TenantQuerySet(self.model, using=self._db)

    def filter_by_tenant(self, tenant=None):
        """
        Filter by a specific tenant.
        """
        return self.get_queryset().filter_by_tenant(tenant)

    def all_tenants(self):
        """
        Return all records across all tenants.
        """
        return self.get_queryset().all_tenants()