from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseNotFound
from .models import Tenant
from .context import set_current_tenant, clear_current_tenant


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware to detect and set the current tenant based on the request domain.

    Add to MIDDLEWARE in settings.py:
        MIDDLEWARE = [
            'tenancy.middleware.TenantMiddleware',
            # ... other middleware
        ]
    """

    def process_request(self, request):
        """
        Extract tenant from the request's HTTP_HOST and set it in thread-local storage.
        """
        # Clear any existing tenant context
        clear_current_tenant()

        # Get the domain from the request
        hostname = request.get_host().split(':')[0].lower()

        try:
            tenant = Tenant.objects.get(domain=hostname, is_active=True)
            set_current_tenant(tenant)
            request.tenant = tenant
        except Tenant.DoesNotExist:
            # Handle missing tenant - you can customize this behavior
            # Option 1: Return 404
            # return HttpResponseNotFound(f'No tenant found for domain: {hostname}')

            # Option 2: Set request.tenant to None and continue
            request.tenant = None

        return None

    def process_response(self, request, response):
        """
        Clear tenant context after request is processed.
        """
        clear_current_tenant()
        return response

    def process_exception(self, request, exception):
        """
        Clear tenant context if an exception occurs.
        """
        clear_current_tenant()
        return None