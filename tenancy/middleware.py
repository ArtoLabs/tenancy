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
                # Tenant managers can only access their assigned tenant's /manage/
                elif roles.is_tenant_manager(request.user, tenant):
                    logger.info(
                        f"Tenant manager {request.user.username} accessing their tenant {tenant.name} /manage/ - allowed")
                # If user is a tenant manager but for a DIFFERENT tenant, return 404
                elif roles.is_tenant_manager(request.user, None):  # Has ANY tenant manager role
                    logger.warning(
                        f"Tenant manager {request.user.username} attempted to access {tenant.name} /manage/ "
                        f"but they don't have permission for this tenant - returning 404"
                    )
                    # Return 404 instead of 403 to avoid revealing tenant existence
                    raise Http404("Page