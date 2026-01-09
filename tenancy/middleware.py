import logging

from django.conf import settings
from django.contrib.auth import logout
from django.http import Http404, HttpResponse, HttpResponseNotFound
from django.utils.deprecation import MiddlewareMixin

from .context import clear_current_tenant, set_current_tenant
from .models import Tenant
from .roles import TenancyRole, roles

logger = logging.getLogger(__name__)



class RequestTenancyAccess:
    """
    Tiny convenience API attached to request as `request.tenancy`.
    Keeps consuming projects from importing tenancy internals everywhere.
    """
    def __init__(self, request):
        self.request = request

    @property
    def tenant(self):
        return getattr(self.request, "tenant", None)

    def can_authenticate_user(self, user):
        # Reuse your tenancy rules (role-based)
        if user is None or self.tenant is None:
            return False
        if roles.is_tenant_admin(user):
            return True
        return roles.is_tenant_manager(user, self.tenant)

    def can_authenticate_email(self, email: str):
        # Optional: if you’ve implemented can_identity_authenticate_on_tenant()
        # in tenancy/services_auth.py, you can delegate to it here.
        from django.contrib.auth import get_user_model

        email_norm = (email or "").strip()
        if not email_norm or self.tenant is None:
            return False

        User = get_user_model()
        user = User.objects.filter(email__iexact=email_norm).first()
        return self.can_authenticate_user(user)



class TenantMiddleware(MiddlewareMixin):
    """
    Resolves the tenant based on the hostname and attaches it to the request.

    Also enforces tenant-membership boundaries:
    - Tenant Admin (global) can be authenticated on any tenant domain.
    - Tenant Manager can only be authenticated on tenant domains they manage.
    - If a tenant manager (or anyone with tenancy roles) is authenticated on the wrong tenant,
      we log them out and return 404 to avoid leaking tenant existence.

    Note: Middleware cannot prevent `login(request, user)` inside a view on the SAME request,
    but it WILL enforce membership immediately on the next request (which is typically the redirect
    after completing magic-link + 2FA). This is usually the desired behavior for reusable apps.
    """

    def process_request(self, request):
        clear_current_tenant()

        # Extract hostname without port
        hostname = request.get_host().split(":")[0].lower()

        logger.debug(f"Processing request for hostname: {hostname}")
        logger.debug(f"Full host header: {request.get_host()}")
        logger.debug(f"Request path: {request.path}")

        # Allow super admin access without tenant resolution (bootstrap mode)
        # Crucial for:
        # 1) Initial setup when no tenants exist yet
        # 2) Creating the first tenant
        # 3) System-wide administration
        if getattr(settings, "TENANCY_BOOTSTRAP", False):
            skip_tenant_paths = getattr(settings, "TENANCY_SKIP_TENANT_PATHS", ["/admin/"])

            for skip_path in skip_tenant_paths:
                if request.path.startswith(skip_path):
                    logger.info(
                        f"Path '{request.path}' matches skip pattern '{skip_path}', skipping tenant resolution"
                    )
                    # Don't set a tenant, allow the request to proceed.
                    # Admin site's has_permission() will still check authentication/roles.
                    return None

        # For all other paths, tenant resolution is required
        try:
            tenant = Tenant.objects.get(domain=hostname, is_active=True)
            set_current_tenant(tenant)
            request.tenant = tenant
            request.tenancy = RequestTenancyAccess(request)

            logger.info(f"Tenant '{tenant.name}' (domain: {hostname}) set for request")

            # ------------------------------------------------------------------
            # GLOBAL MEMBERSHIP ENFORCEMENT (prevents "tenant manager logs into other tenant")
            # ------------------------------------------------------------------
            if request.user.is_authenticated and self._should_enforce_membership(request):
                user_info = f"{request.user.username} (tenant: {getattr(request.user, 'tenant', 'N/A')})"
                logger.info(
                    f"Membership enforcement check - User: {user_info}, Request Tenant: {tenant.name}, Path: {request.path}"
                )

                # Tenant admins can be authenticated on any tenant
                if roles.is_tenant_admin(request.user):
                    logger.debug(
                        f"Tenant admin {request.user.username} authenticated on {tenant.name} - allowed"
                    )
                    return None

                # Tenant managers can only be authenticated on their assigned tenant
                if roles.is_tenant_manager(request.user, tenant):
                    logger.debug(
                        f"Tenant manager {request.user.username} authenticated on their tenant {tenant.name} - allowed"
                    )
                    return None

                # If they have ANY tenancy role(s) but not for this tenant, treat them as not-a-member here
                if self._has_any_tenancy_role(request.user):
                    logger.warning(
                        f"Authenticated user {request.user.username} has tenancy roles but not for tenant "
                        f"{tenant.name}. Logging out and returning 404."
                    )
                    logout(request)
                    raise Http404("Page not found")

                # If they are authenticated but have no tenancy roles at all, we do nothing here.
                # This allows projects to have non-tenant users or public auth flows.
                # Specific privileged areas (admin/manage) still guard themselves.
                logger.debug(
                    f"Authenticated user {request.user.username} has no tenancy roles; skipping membership enforcement."
                )

            # ------------------------------------------------------------------
            # PATH-SPECIFIC ENFORCEMENT FOR /manage/ (your existing logic, preserved)
            # ------------------------------------------------------------------
            if request.path.startswith("/manage/") and request.user.is_authenticated:
                user_info = f"{request.user.username} (tenant: {getattr(request.user, 'tenant', 'N/A')})"
                logger.info(
                    f"Tenant admin access attempt - User: {user_info}, Request Tenant: {tenant.name}"
                )

                # Tenant admins can access any tenant's /manage/
                if roles.is_tenant_admin(request.user):
                    logger.info(
                        f"Tenant admin {request.user.username} accessing {tenant.name} /manage/ - allowed"
                    )
                    return None

                # Tenant managers can only access their assigned tenant's /manage/
                if roles.is_tenant_manager(request.user, tenant):
                    logger.info(
                        f"Tenant manager {request.user.username} accessing their tenant {tenant.name} /manage/ - allowed"
                    )
                    return None

                # If user has tenant manager role but for a DIFFERENT tenant, return 404
                if self._has_any_tenant_manager_role(request.user):
                    logger.warning(
                        f"Tenant manager {request.user.username} attempted to access {tenant.name} /manage/ "
                        f"but they don't have permission for this tenant - returning 404"
                    )
                    raise Http404("Page not found")

                # User is authenticated but has no tenant roles at all
                logger.warning(
                    f"User {request.user.username} attempted to access {tenant.name} /manage/ "
                    f"but has no tenant roles - blocking access"
                )
                # Let the manage site's permission handling deal with it (login/403/etc).
                return None

            return None

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

            # Helpful debug output in development
            if settings.DEBUG:
                available_domains = list(Tenant.objects.filter(is_active=True).values_list("domain", flat=True))
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

            return HttpResponseNotFound(
                "<h1>Tenant Not Found</h1>"
                "<p>The requested domain is not configured.</p>"
            )

        except Tenant.MultipleObjectsReturned:
            logger.critical(f"Multiple active tenants found for domain: {hostname}")
            return HttpResponse(
                "<h1>Configuration Error</h1>"
                "<p>Multiple tenants configured for this domain. Please contact support.</p>",
                status=500,
            )

        except Exception as e:
            logger.exception(f"Unexpected error in TenantMiddleware for hostname {hostname}: {e}")
            if settings.DEBUG:
                raise
            return HttpResponse(
                "<h1>Server Error</h1>"
                "<p>An unexpected error occurred while processing your request.</p>",
                status=500,
            )

    def _should_enforce_membership(self, request) -> bool:
        """
        Controls whether global membership enforcement runs for this request.

        Default behavior: enforce everywhere except a few common auth/static paths,
        so magic-link/2FA endpoints can complete and then the *next* request gets enforced.

        Override in the consuming project via:
          - TENANCY_ENFORCE_MEMBERSHIP = True/False
          - TENANCY_MEMBERSHIP_EXEMPT_PATHS = [...]
        """
        if getattr(settings, "TENANCY_ENFORCE_MEMBERSHIP", True) is False:
            return False

        exempt_paths = getattr(
            settings,
            "TENANCY_MEMBERSHIP_EXEMPT_PATHS",
            [
                "/accounts/",   # your magic-link + 2FA endpoints typically live here
                "/auth/",       # common alternative
                "/login/",
                "/logout/",
                "/static/",
                "/media/",
                "/favicon.ico",
                "/health/",
            ],
        )

        # If request path matches an exempt prefix, skip enforcement
        for p in exempt_paths:
            if request.path.startswith(p):
                return False

        return True

    def _has_any_tenant_manager_role(self, user) -> bool:
        """
        Check if user has tenant manager role for ANY tenant (not necessarily this one).
        Used to determine if we should show 404 vs 403.
        """
        return TenancyRole.objects.filter(user=user, role=TenancyRole.TENANT_MANAGER).exists()

    def _has_any_tenancy_role(self, user) -> bool:
        """
        Check if user has ANY tenancy role at all.
        This is used to decide whether an authenticated user should be treated as "not a member"
        when they're on the wrong tenant domain.
        """
        return TenancyRole.objects.filter(user=user).exists()

    def process_response(self, request, response):
        clear_current_tenant()
        return response

    def process_exception(self, request, exception):
        clear_current_tenant()
        logger.exception(f"Exception in request processing: {exception}")
        return None


