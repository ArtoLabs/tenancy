# tenancy/checks.py
from django.core.checks import Warning, register
from django.apps import apps
from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model

from tenancy.mixins import TenantMixin


@register()
def tenant_unique_field_checks(app_configs, **kwargs):
    errors = []
    UserModel = get_user_model()

    for model in apps.get_models():
        if not issubclass(model, TenantMixin):
            continue

        if not hasattr(model, "_meta"):
            continue

        model_name = model._meta.model_name
        app_label = model._meta.app_label
        unique_fields = []

        allowed_global = set(getattr(model, "TENANCY_ALLOW_GLOBAL_UNIQUE_FIELDS", ()))

        for field in model._meta.get_fields():
            if getattr(field, "auto_created", False):
                continue

            if not getattr(field, "unique", False):
                continue

            if field.name in ("id", "tenant"):
                continue

            # Per-model escape hatch
            if field.name in allowed_global:
                continue

            # Common legit case: Profile.user = OneToOneField(AUTH_USER_MODEL)
            if isinstance(field, models.OneToOneField):
                remote = getattr(field.remote_field, "model", None)
                # remote can be the actual model or the swappable label; handle both
                if remote == UserModel or remote == settings.AUTH_USER_MODEL:
                    continue

            unique_fields.append(field.name)

        if unique_fields:
            constraint_name = f"{app_label}_{model_name}_" + "_".join(unique_fields)
            constraint_name = constraint_name.lower()

            fields_list_str = ", ".join([f"'{f}'" for f in ["tenant"] + unique_fields])
            example_code = f"""
class {model.__name__}(TenantMixin):
    # your fields here

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=[{fields_list_str}], name='{constraint_name}')
        ]
"""

            errors.append(
                Warning(
                    f"Model '{app_label}.{model.__name__}' has user-defined fields with `unique=True` "
                    f"which are not tenant-scoped. Cloning template objects may raise IntegrityErrors.",
                    hint=f"Convert these unique fields to a tenant-aware constraint.\nExample:{example_code}",
                    obj=model,
                    id="tenancy.W001",
                )
            )

    return errors
