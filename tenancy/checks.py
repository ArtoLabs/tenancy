# tenancy/checks.py
from django.core.checks import Error, register
from django.contrib.auth import get_user_model
from django.db.migrations.executor import MigrationExecutor
from django.db import connections
from django.conf import settings

@register()
def check_default_user_tenant_field(app_configs, **kwargs):
    User = get_user_model()

    # Only check default user model
    if User._meta.label != "auth.User":
        return []

    # Skip the check if migrations are still pending
    try:
        connection = connections['default']
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:  # migrations pending
            return []
    except Exception:
        # If something fails, skip check (better than blocking migration)
        return []

    # Check if tenant field exists
    if not any(f.name == "tenant" for f in User._meta.get_fields()):
        return [
            Error(
                "Default Django user model detected, but tenant_id field was not added. Did you run migrations?",
                id="tenancy.E001",
            )
        ]

    return []
