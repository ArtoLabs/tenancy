# tenancy/checks.py
from django.core.checks import Warning, register
from django.apps import apps
from tenancy.mixins import CloneForTenantMixin
from django.db import models


@register()
def check_clone_for_tenant_unique_fields(app_configs, **kwargs):
    """
    Warn about fields with `unique=True` in models that inherit from CloneForTenantMixin.
    These unique fields need to be converted to tenant-scoped constraints to avoid
    issues when cloning templates for new tenants.

    Only user-defined unique fields are checked. Primary key (id) and tenant FK are
    inherently unique and are not included in this check.
    """
    warnings = []

    for model in apps.get_models():
        if not issubclass(model, CloneForTenantMixin):
            continue

        # Collect all user-defined fields that are unique
        unique_fields = [
            field.name
            for field in model._meta.get_fields()
            if isinstance(field, models.Field)
               and field.unique
               and field.concrete
               and not field.auto_created
               and field.name not in ('id', 'tenant')
        ]

        if unique_fields:
            # Construct a single UniqueConstraint example for all unique fields
            fields_list = "', '".join(unique_fields)
            constraint_name = f'unique_tenant_{"_".join(unique_fields)}'
            code_snippet = f"""
class {model.__name__}({', '.join([base.__name__ for base in model.__bases__])}):
    # your fields here

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', '{fields_list}'], name='{constraint_name}')
        ]
"""
            warnings.append(
                Warning(
                    f"Model '{model._meta.label}' has user-defined fields with `unique=True` "
                    "which are not tenant-scoped. Cloning template objects may raise IntegrityErrors.",
                    hint=f"Convert these unique fields to a tenant-aware constraint.\n"
                         f"Example:\n{code_snippet}",
                    obj=model,
                    id="tenancy.W001",
                )
            )

    return warnings
