import logging
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseNotFound, HttpResponse
from django.conf import settings
from .models import Tenant
from .context import set_current_tenant, clear_current_tenant

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):

    def process_request(self, request):
        clear_current_tenant()

        # Extract hostname without port
        hostname = request.get_host().split(':')[0].lower()

        logger.debug(f"Processing request for hostname: {hostname}")
        logger.debug(f"Full host header: {request.get_host()}")
        logger.debug(f"Request path: {request.path}")

        try:
            tenant = Tenant.objects.get(domain=hostname, is_active=True)
            set_current_tenant(tenant)
            request.tenant = tenant
            logger.info(f"Tenant '{tenant.name}' (domain: {hostname}) set for request")

            # Debug logging for admin access (only if user is available)
            if request.path.startswith('/manage/') and hasattr(request, 'user'):
                user_info = f"{request.user.username} (tenant: {getattr(request.user, 'tenant', 'N/A')})" if request.user.is_authenticated else 'Anonymous'
                logger.info(f"Admin access attempt - User: {user_info}, Request Tenant: {tenant.name}")

        except Tenant.DoesNotExist:
            logger.error(
                f"No active tenant found for domain: {hostname}. "
                f"Available tenants: {list(Tenant.objects.filter(is_active=True).values_list('domain', flat=True))}"
            )

            # Optional: Check if tenant exists but is inactive
            inactive_tenant = Tenant.objects.filter(domain=hostname, is_active=False).first()
            if inactive_tenant:
                logger.warning(f"Tenant found for {hostname} but is inactive")
                return HttpResponseNotFound(
                    f"<h1>Tenant Inactive</h1>"
                    f"<p>The tenant for domain <strong>{hostname}</strong> is currently inactive.</p>"
                )

            # Check if this is a development environment and provide helpful error
            if settings.DEBUG:
                available_domains = list(Tenant.objects.filter(is_active=True).values_list('domain', flat=True))
                return HttpResponseNotFound(
                    f"<h1>No Tenant Found</h1>"
                    f"<p>No active tenant found for domain: <strong>{hostname}</strong></p>"
                    f"<h2>Debug Information:</h2>"
                    f"<ul>"
                    f"<li>Hostname extracted: {hostname}</li>"
                    f"<li>Full host header: {request.get_host()}</li>"
                    f"<li>Available active tenants: {', '.join(available_domains) if available_domains else 'None'}</li>"
                    f"</ul>"
                    f"<h3>Common Issues:</h3>"
                    f"<ul>"
                    f"<li>Make sure you're accessing the site using the correct domain (e.g., tenant1.localhost:8000)</li>"
                    f"<li>Verify the tenant exists in the database with the correct domain</li>"
                    f"<li>Check that the tenant's is_active field is True</li>"
                    f"<li>If using /etc/hosts, ensure entries are correct and you're using the mapped domain</li>"
                    f"</ul>"
                )
            else:
                return HttpResponseNotFound(
                    f"<h1>Tenant Not Found</h1>"
                    f"<p>The requested domain is not configured.</p>"
                )

        except Tenant.MultipleObjectsReturned:
            logger.critical(f"Multiple active tenants found for domain: {hostname}")
            return HttpResponse(
                "<h1>Configuration Error</h1>"
                "<p>Multiple tenants configured for this domain. Please contact support.</p>",
                status=500
            )

        except Exception as e:
            logger.exception(f"Unexpected error in TenantMiddleware for hostname {hostname}: {e}")
            if settings.DEBUG:
                raise
            return HttpResponse(
                "<h1>Server Error</h1>"
                "<p>An unexpected error occurred while processing your request.</p>",
                status=500
            )

    def process_response(self, request, response):
        clear_current_tenant()
        return response

    def process_exception(self, request, exception):
        clear_current_tenant()
        logger.exception(f"Exception in request processing: {exception}")
        return None