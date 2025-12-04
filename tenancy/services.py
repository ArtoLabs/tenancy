import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps

from .models import Tenant
from .mixins import CloneForTenantMixin

User = get_user_model()
logger = logging.getLogger(__name__)


class TenantProvisioningError(Exception):
    pass


class TenantProvisioner:
    @staticmethod
    @transaction.atomic
    def create_tenant(tenant_data: dict, admin_data: dict):

        tenant = Tenant.objects.create(
            name=tenant_data['name'],
            domain=tenant_data['domain'],
            is_active=tenant_data.get('is_active', True)
        )

        user = User.objects.create_user(
            username=admin_data['username'],
            email=admin_data.get('email', ''),
            password=admin_data['password'],
            tenant=tenant,
        )
        user.is_staff = True
        user.is_superuser = False
        user.save()

        # After creating tenant and admin user:
        cloneable_models = [
            model for model in apps.get_models()
            if issubclass(model, CloneForTenantMixin)
        ]

        for model in cloneable_models:
            logger.info(f"Cloning defaults for model: {model.__name__}")
            model.clone_defaults_for_new_tenant(tenant.id)

        return tenant, user