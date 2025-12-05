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
    System check to warn about fields with `unique=True` in models that
    inherit from CloneForTenantMixin. These unique fields need to be
    converted to tenant-scoped constraints to avoid issues when cloning
    templates for new tenants.
    """
    warnings = []

    # Iterate over all models in the project
    for model in apps.get_models():
        # Only check models using CloneForTenantMixin
        if not issubclass(model, CloneForTenantMixin):
            continue

        # Collect all fields that are unique
        unique_fields = [
            field.name
            for field in model._meta.get_fields()
            if getattr(field, 'unique', False) and isinstance(field, models.Field)
        ]

        if unique_fields:
            # Construct a single UniqueConstraint example
            constraint_name = f'unique_tenant_{"_".join(unique_fields)}'
            fields_list = "', '".join(['tenant'] + unique_fields)
            code_snippet = f"""
class {model.__name__}({', '.join([base.__name__ for base in model.__bases__])}):
    # your fields here
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['{fields_list}'], name='{constraint_name}')
        ]
"""
            warnings.append(
                Warning(
                    f"Model '{model._meta.label}' has fields with `unique=True` which are not tenant-scoped. "
                    "This may cause errors when cloning template objects for new tenants.",
                    hint=f"Consider converting unique fields to a tenant-aware constraint.\n"
                         f"Example:\n{code_snippet}",
                    obj=model,
                    id="tenancy.W001",
                )
            )

    return warnings
