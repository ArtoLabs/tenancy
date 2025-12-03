from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseNotFound
from .models import Tenant
from .context import set_current_tenant, clear_current_tenant


class TenantMiddleware(MiddlewareMixin):

    def process_request(self, request):
        clear_current_tenant()

        hostname = request.get_host().split(':')[0].lower()

        try:
            tenant = Tenant.objects.get(domain=hostname, is_active=True)
            set_current_tenant(tenant)
            request.tenant = tenant
        except Tenant.DoesNotExist:
            # Reject requests if tenant not found
            return HttpResponseNotFound(f"No tenant found for domain: {hostname}")

    def process_response(self, request, response):
        clear_current_tenant()
        return response

    def process_exception(self, request, exception):
        clear_current_tenant()
        return None