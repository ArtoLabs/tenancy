from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps
from tenancy.models import Tenant
from tenancy.admin import TenantAdminMixin
import getpass

User = get_user_model()


class Command(BaseCommand):
    help = 'Bootstrap the first tenant and assign all existing objects using TenantAdminMixin to it.'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, help="Tenant name")
        parser.add_argument('--domain', type=str, help="Tenant domain")
        parser.add_argument('--schema', type=str, help="Tenant schema_name")
        parser.add_argument('--admin_username', type=str, help="Tenant admin username")
        parser.add_argument('--admin_email', type=str, help="Tenant admin email")
        parser.add_argument('--admin_password', type=str, help="Tenant admin password (will prompt if not provided)")

    @transaction.atomic
    def handle(self, *args, **options):
        if Tenant.objects.exists():
            self.stdout.write(self.style.ERROR('Tenants already exist. Aborting bootstrap.'))
            return

        # --- Interactive prompts for missing options ---
        name = options['name'] or input("Enter tenant name: ")
        domain = options['domain'] or input("Enter tenant domain (e.g. tenant1.localhost): ")
        schema = options['schema'] or input("Enter tenant schema_name (e.g. default): ")
        admin_username = options['admin_username'] or input("Enter tenant admin username: ")
        admin_email = options['admin_email'] or input("Enter tenant admin email: ")

        # Password prompt (hidden input)
        admin_password = options['admin_password']
        while not admin_password:
            password1 = getpass.getpass("Enter tenant admin password: ")
            password2 = getpass.getpass("Confirm password: ")
            if password1 != password2:
                self.stdout.write(self.style.ERROR("Passwords do not match. Please try again."))
            else:
                admin_password = password1

        # --- Step 1: Create the first tenant ---
        tenant = Tenant.objects.create(
            name=name,
            domain=domain,
            schema_name=schema,
            is_active=True
        )
        self.stdout.write(self.style.SUCCESS(f'Created tenant "{tenant.name}"'))

        # --- Step 2: Create tenant admin user ---
        admin_user = User.objects.create_user(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            is_staff=True,
            is_superuser=False
        )
        self.stdout.write(self.style.SUCCESS(f'Created tenant admin user "{admin_user.username}"'))

        # --- Step 3: Detect all models that use TenantAdminMixin ---
        tenanted_models = []
        for model in apps.get_models():
            if any(issubclass(base, TenantAdminMixin) for base in model.__mro__):
                tenanted_models.append(model)

        # --- Step 4: Assign tenant to all objects in these models where tenant is null ---
        for model in tenanted_models:
            updated_count = model.objects.filter(tenant__isnull=True).update(tenant=tenant)
            self.stdout.write(self.style.SUCCESS(
                f'Assigned {updated_count} objects in {model._meta.label} to tenant "{tenant.name}"'
            ))

        self.stdout.write(self.style.SUCCESS('Bootstrap completed successfully!'))
