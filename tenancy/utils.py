"""
Utility functions and decorators for tenant management.
"""
from functools import wraps
from .context import get_current_tenant, set_current_tenant


def tenant_context(tenant):
    """
    Context manager for temporarily setting a tenant context.

    Usage:
        with tenant_context(my_tenant):
            # All queries here will be scoped to my_tenant
            MyModel.objects.all()
    """

    class TenantContext:
        def __init__(self, tenant):
            self.tenant = tenant
            self.previous_tenant = None

        def __enter__(self):
            self.previous_tenant = get_current_tenant()
            set_current_tenant(self.tenant)
            return self.tenant

        def __exit__(self, exc_type, exc_val, exc_tb):
            set_current_tenant(self.previous_tenant)

    return TenantContext(tenant)


def require_tenant(view_func):
    """
    Decorator to ensure a tenant is set before executing a view.

    Usage:
        @require_tenant
        def my_view(request):
            # tenant is guaranteed to be set here
            pass
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, 'tenant') or request.tenant is None:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('No tenant context available')
        return view_func(request, *args, **kwargs)

    return wrapper