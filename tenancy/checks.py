# tenancy/checks.py
from django.core.checks import Warning, register
from django.apps import apps
from tenancy.mixins import TenantMixin
from django.db import models


@register()
def tenant_unique_field_checks(app_configs, **kwargs):
    """
    Checks all models that use CloneForTenantMixin to ensure that
    user-defined unique fields are tenant-scoped. Provides a warning
    with an example UniqueConstraint if not.
    """
    errors = []

    for model in apps.get_models():
        if issubclass(model, TenantMixin):
            # Only check concrete models
            if not hasattr(model, "_meta"):
                continue

            model_name = model._meta.model_name
            app_label = model._meta.app_label
            unique_fields = []

            # Inspect each field
            for field in model._meta.get_fields():
                # Skip auto-created or reverse relations
                if getattr(field, "auto_created", False):
                    continue

                # Only check user-defined unique fields
                if getattr(field, "unique", False) and field.name not in ("id", "tenant"):
                    unique_fields.append(field.name)

            if unique_fields:
                # Generate a safe unique constraint name
                constraint_name = f"{app_label}_{model_name}_" + "_".join(unique_fields)
                constraint_name = constraint_name.lower()

                # Build example code for warning
                fields_list_str = ", ".join([f"'{f}'" for f in ["tenant"] + unique_fields])
                example_code = f"""
class {model.__name__}(TenantMixin):
    # your fields here

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=[{fields_list_str}], name='{constraint_name}')
        ]
"""

                warning = Warning(
                    f"Model '{app_label}.{model.__name__}' has user-defined fields with `unique=True` "
                    f"which are not tenant-scoped. Cloning template objects may raise IntegrityErrors.",
                    hint=f"Convert these unique fields to a tenant-aware constraint.\nExample:{example_code}",
                    obj=model,
                    id='tenancy.W001',
                )
                errors.append(warning)

    return errors
