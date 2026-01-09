from django.contrib.auth.backends import ModelBackend
from django.conf import settings

from .services import can_user_authenticate_on_tenant


class TenantGuardModelBackend(ModelBackend):
    """
    Wraps normal Django authentication and refuses authentication
    if the user is not allowed on request.tenant.

    This catches username/password, and any flow that calls authenticate().
    """

    def user_can_authenticate(self, user):
        # keep Django's normal checks (is_active, etc.)
        return super().user_can_authenticate(user)

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is None or request is None:
            return user

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            # If tenant isn't resolved, you can either allow or deny.
            # For tenancy-first setups, denying is safer. Make it configurable.
            if getattr(settings, "TENANCY_DENY_AUTH_WITHOUT_TENANT", True):
                return None
            return user

        result = can_user_authenticate_on_tenant(user=user, tenant=tenant)
        return user if result.allowed else None
