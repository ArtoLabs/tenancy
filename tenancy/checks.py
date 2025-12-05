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

        print(f"\n--- Checking model: {model.__name__} ---")
        for field in model._meta.get_fields():
            # Show all relevant info about the field
            print(
                f"Field name: {field.name}, "
                f"type: {type(field)}, "
                f"unique: {getattr(field, 'unique', None)}, "
                f"auto_created: {getattr(field, 'auto_created', None)}, "
                f"concrete: {getattr(field, 'concrete', None)}, "
                f"editable: {getattr(field, 'editable', None)}, "
                f"primary_key: {getattr(field, 'primary_key', None)}"
            )

        # Then also show the filtered list
        EXCLUDE_UNIQUE_FIELDS = ('id', 'tenant')
        unique_fields = [
            field.name
            for field in model._meta.get_fields()
            if isinstance(field, models.Field)
               and getattr(field, 'unique', False)
               and field.name not in EXCLUDE_UNIQUE_FIELDS
        ]

        print(f"Filtered unique fields (after exclusions): {unique_fields}")

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
