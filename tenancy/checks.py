# tenancy/checks.py
from django.core.checks import Error, register
from django.contrib.auth import get_user_model
from django.db.migrations.executor import MigrationExecutor
from django.db import connections

@register()
def check_user_model_tenant_field(app_configs, **kwargs):
    """
    System check to ensure the default Django user has a 'tenant' field.
    """

    User = get_user_model()

    # Only run this check if the project is still using the default auth.User
    if User._meta.label != "auth.User":
        return []

    # Skip the check if migrations are still pending
    try:
        connection = connections['default']
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            return []
    except Exception:
        # Safe fallback: skip the check if we cannot determine migration state
        return []

    # Check if the tenant field exists
    if not any(f.name == "tenant" for f in User._meta.get_fields()):
        return [
            Error(
                "Default Django user model detected but no 'tenant' field found. "
                "Please either:\n"
                "1) Create a custom user model with TenantUserMixin and run migrations, or\n"
                "2) Set AUTH_USER_MODEL = 'tenancy.TenantUser' in settings before running migrations.",
                id="tenancy.E001",
            )
        ]

    return []
