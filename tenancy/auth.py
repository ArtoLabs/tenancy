from django.contrib.auth import login as django_login
from django.conf import settings

from .services_auth import can_user_authenticate_on_tenant  # or wherever you put the new authz functions


def tenancy_login(request, user) -> bool:
    """
    Tenant-aware login helper.

    Use this in custom auth flows that call login(request, user) directly
    (magic links, OTP, SSO callbacks, etc.).

    Returns True if login succeeded, False if tenant policy blocks it.
    """
    tenant = getattr(request, "tenant", None)

    # If your app allows non-tenant pages to authenticate, make this configurable.
    deny_without_tenant = getattr(settings, "TENANCY_DENY_AUTH_WITHOUT_TENANT", True)
    if tenant is None:
        return False if deny_without_tenant else _login_and_ok(request, user)

    result = can_user_authenticate_on_tenant(user=user, tenant=tenant)
    if not result.allowed:
        return False

    return _login_and_ok(request, user)


def _login_and_ok(request, user) -> bool:
    django_login(request, user)
    return True
