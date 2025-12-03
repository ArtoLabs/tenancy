from django.contrib.auth import get_user_model
from django.core.checks import Error, Warning, register

from .mixins import TenantUserMixin


@register()
def tenancy_user_model_check(app_configs, **kwargs):
    """
    Ensures the user model is compatible with the tenancy system.
    """
    User = get_user_model()

    # Case 1: default user model (auth.User)
    if User._meta.label == "auth.User":
        # The migration 002_add_tenant_to_user *should* add tenant_id
        if not any(f.name == "tenant" for f in User._meta.get_fields()):
            return [
                Error(
                    "Default Django user model detected, but tenant_id field "
                    "was not added. Did you run migrations?",
                    id="tenancy.E001"
                )
            ]
        return []

    # Case 2: custom user model (must include TenantUserMixin)
    if not issubclass(User, TenantUserMixin):
        return [
            Error(
                "Custom user model detected, but it does not inherit TenantUserMixin.",
                hint="Update your custom user model: class MyUser(TenantUserMixin, AbstractUser): ...",
                id="tenancy.E002"
            )
        ]

    # All good
    return []
