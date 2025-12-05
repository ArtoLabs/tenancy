# tenancy/checks.py
from django.core.checks import Error, Warning, register
from django.contrib.auth import get_user_model
from django.db.migrations.executor import MigrationExecutor
from django.db import connections
from django.apps import apps

from .mixins import CloneForTenantMixin


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
                "You MUST:\n"
                "Create a custom user model with TenantUserMixin and run migrations.",
                id="tenancy.E001",
            )
        ]

    return []


@register()
def check_clone_for_tenant_unique_fields(app_configs, **kwargs):
    """
    Warn if any model that uses CloneForTenantMixin has fields with unique=True.
    These unique fields will conflict when cloning template rows to new tenants.
    Suggests converting them to tenant-scoped UniqueConstraint.
    """
    warnings = []

    for model in apps.get_models():
        if not issubclass(model, CloneForTenantMixin):
            continue

        for field in model._meta.fields:
            if getattr(field, "unique", False):
                warnings.append(
                    Warning(
                        f"Model '{model._meta.label}' has a field '{field.name}' with unique=True. "
                        f"This will prevent cloning templates for new tenants.\n"
                        f"Suggested fix:\n"
                        f"    class Meta:\n"
                        f"        constraints = [\n"
                        f"            models.UniqueConstraint(fields=['tenant', '{field.name}'], name='unique_{field.name}_per_tenant')\n"
                        f"        ]",
                        id="tenancy.W001",
                    )
                )

    return warnings
