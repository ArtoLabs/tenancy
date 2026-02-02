from django.db import models
from .context import get_current_tenant

import warnings


def warn_missing_tenant(model):
    """
    Print a loud, helpful warning when tenant-scoped queries occur without a tenant.
    Does NOT raise; execution continues.
    """
    model_name = model.__name__
    app_label = model._meta.app_label

    warnings.warn(
        (
            "\n"
            "==================== TENANCY WARNING ====================\n"
            f"Tenant is None while querying a tenant-scoped model:\n"
            f"  {app_label}.{model_name}\n"
            "\n"
            "This queryset is being forced to .none() for safety.\n"
            "Most common cause:\n"
            "  A form field (or other module-level code) created a queryset at import time.\n"
            "\n"
            f"Example of the problematic pattern:\n"
            f"  field = forms.ModelChoiceField(queryset={model_name}.objects.all())\n"
            "\n"
            "Canonical Django fix (copy/paste):\n"
            "\n"
            "  # forms.py\n"
            "  class MyForm(forms.Form):\n"
            f"      person = forms.ModelChoiceField(queryset={model_name}.objects.none())\n"
            "\n"
            "      def __init__(self, *args, **kwargs):\n"
            "          super().__init__(*args, **kwargs)\n"
            f"          self.fields['person'].queryset = {model_name}.objects.all()\n"
            "\n"
            "If you need request-specific behavior, pass request into the form:\n"
            "\n"
            "  # view\n"
            "  def get_form_kwargs(self):\n"
            "      kwargs = super().get_form_kwargs()\n"
            "      kwargs['request'] = self.request\n"
            "      return kwargs\n"
            "\n"
            "  # form\n"
            "  def __init__(self, *args, request=None, **kwargs):\n"
            "      super().__init__(*args, **kwargs)\n"
            f"      self.fields['person'].queryset = {model_name}.objects.all()\n"
            "\n"
            "This warning is non-fatal: the program will continue.\n"
            "=========================================================\n"
        ),
        RuntimeWarning,
        stacklevel=3,
    )


class TenantQuerySet(models.QuerySet):
    """
    Custom QuerySet that automatically filters by the current tenant.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tenant_filtering_disabled = False
        self._tenant_filter_applied = False

    def filter_by_tenant(self, tenant=None):
        """
        Explicitly filter by a specific tenant.

        Args:
            tenant: Tenant instance or None to use current tenant
        """
        if tenant is None:
            tenant = get_current_tenant()

        if tenant is None:
            warn_missing_tenant(self.model)
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
        clone._tenant_filter_applied = self._tenant_filter_applied
        return clone

    def _apply_tenant_filter(self):
        """
        Apply tenant filtering if needed.
        Called early in the queryset lifecycle.
        """
        # Don't apply if already applied or if disabled
        if self._tenant_filter_applied or self._tenant_filtering_disabled:
            return self

        # Check if this is a tenant model
        if not hasattr(self.model, '_is_tenant_model') or not self.model._is_tenant_model():
            return self

        # Get current tenant
        current_tenant = get_current_tenant()
        if current_tenant is None:
            # No tenant context - return empty queryset for safety, but warn loudly
            warn_missing_tenant(self.model)
            return self.none()

        # Check if already filtered by tenant
        if self._has_tenant_filter():
            return self

        # Apply the filter
        qs = self.filter(tenant=current_tenant)
        qs._tenant_filter_applied = True
        return qs

    def _has_tenant_filter(self):
        """
        Check if the queryset already has a tenant filter.
        """
        where = self.query.where
        if hasattr(where, 'children'):
            for child in where.children:
                if hasattr(child, 'lhs') and hasattr(child.lhs, 'target'):
                    if child.lhs.target.name == 'tenant':
                        return True
        return False

    # Override key queryset methods to apply tenant filter early

    def iterator(self, chunk_size=None):
        """Override iterator to apply tenant filter."""
        qs = self._apply_tenant_filter()
        return super(TenantQuerySet, qs).iterator(chunk_size=chunk_size)

    def count(self):
        """Override count to apply tenant filter."""
        qs = self._apply_tenant_filter()
        return super(TenantQuerySet, qs).count()

    def exists(self):
        """Override exists to apply tenant filter."""
        qs = self._apply_tenant_filter()
        return super(TenantQuerySet, qs).exists()

    def _fetch_all(self):
        """Override _fetch_all to apply tenant filter."""
        if not self._result_cache:
            qs = self._apply_tenant_filter()
            if qs is not self:
                # Filter was applied, use the filtered queryset
                self.query = qs.query
                self._tenant_filter_applied = True
        super()._fetch_all()


class TenantManager(models.Manager):
    """
    Custom Manager that uses TenantQuerySet for automatic tenant filtering.
    """

    def get_queryset(self):
        """
        Return a TenantQuerySet instance with tenant filtering applied.
        """
        qs = TenantQuerySet(self.model, using=self._db)
        # Apply tenant filter immediately if this is a tenant model
        if hasattr(self.model, '_is_tenant_model') and self.model._is_tenant_model():
            return qs._apply_tenant_filter()
        return qs

    def filter_by_tenant(self, tenant=None):
        """
        Filter by a specific tenant.
        """
        return self.get_queryset().filter_by_tenant(tenant)

    def all_tenants(self):
        """
        Return all records across all tenants.
        """
        return TenantQuerySet(self.model, using=self._db).all_tenants()
