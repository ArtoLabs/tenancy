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
    """
    Service object responsible for provisioning a new tenant.
    This is where you do schema creation, migrations, seed data, etc.

    NOTE: The actual schema creation/migration code depends on whether you use schema-per-tenant
    (Postgres schemas) or a separate database per tenant. Here we provide a clean place to call
    the management commands or your project's provisioning logic.
    """

    @staticmethod
    @transaction.atomic
    def create_tenant(tenant_data: dict, admin_data: dict, run_migrations: bool = False):
        """
        Creates a Tenant object and the tenant owner user. Keeps DB changes in a transaction.
        :param tenant_data: dict with keys name, domain, schema_name, is_active
        :param admin_data: dict with keys username, email, password
        :param run_migrations: if True, attempt to run migrations for tenant (optional)
        :return: (tenant, user)
        """
        # 1) Create tenant DB record
        tenant = Tenant.objects.create(
            name=tenant_data['name'],
            domain=tenant_data['domain'],
            schema_name=tenant_data['schema_name'],
            is_active=tenant_data.get('is_active', True)
        )

        # 2) IMPORTANT: Provision tenant schema / DB / resources
        try:
            TenantProvisioner._provision_schema(tenant, run_migrations=run_migrations)
        except Exception as exc:
            logger.exception("Failed to provision schema for tenant %s", tenant)
            raise TenantProvisioningError(f"Failed to provision tenant resources: {exc}")

        # 3) Create tenant admin user (system-level user model)
        user = User.objects.create_user(
            username=admin_data['username'],
            email=admin_data.get('email', ''),
            password=admin_data['password']
        )
        user.is_staff = True
        user.is_superuser = False
        user.save()

        # 4) OPTIONAL: Link user to tenant if your User model has that relation
        # if hasattr(user, 'tenant'):
        #     user.tenant = tenant
        #     user.save()

        # 5) Optionally run tenant migrations or seed data
        if run_migrations:
            try:
                TenantProvisioner._run_tenant_migrations(tenant)
            except Exception:
                logger.exception("Tenant migrations failed")
                # Depending on preference, either re-raise to rollback, or log + continue.
                raise

        return tenant, user

    @staticmethod
    def _provision_schema(tenant: Tenant, run_migrations: bool = False):
        """
        Placeholder for schema provisioning. Replace this with your real provisioning logic.
        Examples:
          - For django-tenants: call connection.schema_name = public; then create schema using tenant.create_schema()
          - For separate DBs: provision a DB user/database, update settings, run migrations.
        """
        # Example stubs below — modify for your environment:
        logger.info("Provisioning resources for tenant %s (schema: %s)", tenant, tenant.schema_name)

        # If you're using django-tenants, you might do:
        # tenant.create_schema(sync_schema=True)

        # If you need to run migrations right away:
        if run_migrations:
            TenantProvisioner._run_tenant_migrations(tenant)

    @staticmethod
    def _run_tenant_migrations(tenant: Tenant):
        """
        Example of invoking Django management command to run migrations.
        WARNING: This is project-specific and may need customizing for your multi-tenant strategy.
        """
        logger.info("Running migrations for tenant %s", tenant)
        # Example: if you have a script/management command to migrate a tenant, call it:
        # call_command('migrate_tenant', schema_name=tenant.schema_name)
        # OR run standard migrate with a schema context if using schemas.
        # call_command('migrate', database='default')  # placeholder

        # For now just log:
        logger.debug("Migrations for %s would be run here (no-op)", tenant.schema_name)
