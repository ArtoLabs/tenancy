import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.management import call_command
from django.conf import settings
from .models import Tenant

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
            schema_name=tenant_data['schema_name'],
            is_active=tenant_data.get('is_active', True)
        )

        user = User.objects.create_user(
            username=admin_data['username'],
            email=admin_data.get('email', ''),
            password=admin_data['password']
        )
        user.is_staff = True
        user.is_superuser = False
        user.save()

        return tenant, user