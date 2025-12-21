import logging
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseNotFound, HttpResponse, Http404
from django.conf import settings
from .models import Tenant
from .context import set_current_tenant, clear_current_tenant
from .roles import roles

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):

    def process_request(self, request):
        clear_current_tenant()

        # Extract hostname without port
        hostname = request.get_host().split(':')[0].lower()

        logger.debug(f"Processing request for hostname: {hostname}")
        logger.debug(f"Full host header: {request.get_host()}")
        logger.debug(f"Request path: {request.path}")

        # Allow super admin access without tenant resolution
        # This is crucial for:
        # 1. Initial setup when no tenants exist yet
        # 2. Creating the first tenant
        # 3. System-wide administration
        if settings.TENANCY_BOOTSTRAP:
            skip_tenant_paths = getattr(settings, 'TENANCY_SKIP_TENANT_PATHS', ['/admin/'])

            for skip_path in skip_tenant_paths:
                if request.path.startswith(skip_path):
                    logger.info(f"Path '{request.path}' matches skip pattern '{skip_path}', skipping tenant resolution")
                    # Don't set a tenant, but allow the request to proceed
                    # The admin site's has_permission() will still check authentication
                    return None

        # For all other paths, tenant resolution is required
        try:
            tenant = Tenant.objects.get(domain=hostname, is_active=True)
            set_current_tenant(tenant)
            request.tenant = tenant
            logger.info(f"Tenant '{tenant.name}' (domain: {hostname}) set for request")

            # SECURITY CHECK: If accessing /manage/, verify user has permission for THIS tenant
            if request.path.startswith('/manage/') and request.user.is_authenticated:
                user_info = f"{request.user.username} (tenant: {getattr(request.user, 'tenant', 'N/A')})"
                logger.info(f"Tenant admin access attempt - User: {user_info}, Request Tenant: {tenant.name}")

                # Tenant admins can access any tenant's /manage/
                if roles.is_tenant_admin(request.user):
                    logger.info(f"Tenant admin {request.user.username} accessing {tenant.name} /manage/ - allowed")
                    return None  # Allow through

                # Tenant managers can only access their assigned tenant's /manage/
                elif roles.is_tenant_manager(request.user, tenant):
                    logger.info(
                        f"Tenant manager {request.user.username} accessing their tenant {tenant.name} /manage/ - allowed")
                    return None  # Allow through

                # If user has tenant manager role but for a DIFFERENT tenant, return 404
                elif self._has_any_tenant_manager_role(request.user):
                    logger.warning(
                        f"Tenant manager {request.user.username} attempted to access {tenant.name} /manage/ "
                        f"but they don't have permission for this tenant - returning 404"
                    )
                    # Return 404 instead of 403 to avoid revealing tenant existence
                    raise Http404("Page not found")

                # User is authenticated but has no tenant roles at all
                else:
                    logger.warning(
                        f"User {request.user.username} attempted to access {tenant.name} /manage/ "
                        f"but has no tenant roles - blocking access"
                    )
                    # Let the admin site's has_permission handle this (will show login or 403)
                    # Don't raise 404 here as they might not even be a tenant manager
                    pass

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
                    f"<h3>Setting Up Your First Tenant:</h3>"
                    f"<ul>"
                    f"<li>Access the super admin at: <a href='/admin/'>/admin/</a> (works without tenant)</li>"
                    f"<li>Login with your superuser account</li>"
                    f"<li>Create your first tenant using the 'Create Tenant' button</li>"
                    f"<li>Then access the tenant admin at the domain you configured</li>"
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

    def _has_any_tenant_manager_role(self, user):
        """
        Check if user has tenant manager role for ANY tenant (not necessarily this one).
        Used to determine if we should show 404 vs 403.
        """
        from .roles import TenancyRole
        return TenancyRole.objects.filter(
            user=user,
            role=TenancyRole.TENANT_MANAGER
        ).exists()

    def process_response(self, request, response):
        clear_current_tenant()
        return response

    def process_exception(self, request, exception):
        clear_current_tenant()
        logger.exception(f"Exception in request processing: {exception}")
        return None