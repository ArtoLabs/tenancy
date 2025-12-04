from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps
from tenancy.models import Tenant
from tenancy.mixins import TenantMixin
import getpass

User = get_user_model()


class Command(BaseCommand):
    help = 'Bootstrap the first tenant and assign all existing objects using TenantAdminMixin to it.'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, help="Tenant name")
        parser.add_argument('--domain', type=str, help="Tenant domain (e.g. tenant1.localhost)")
        parser.add_argument('--admin_username', type=str, help="Tenant admin username")
        parser.add_argument('--admin_email', type=str, help="Tenant admin email")
        parser.add_argument('--admin_password', type=str, help="Tenant admin password (will prompt if not provided)")

    @transaction.atomic
    def handle(self, *args, **options):
        if Tenant.objects.exists():
            self.stdout.write(self.style.ERROR('Tenants already exist. Aborting bootstrap.'))
            return

        # --- Step 0: Prompt for missing tenant info ---
        name = options['name'] or input("Enter tenant name: ")
        domain = options['domain'] or input("Enter tenant domain (e.g. tenant1.localhost): ")

        # --- Step 1: Create the first tenant ---
        tenant = Tenant.objects.create(
            name=name,
            domain=domain,
            is_active=True
        )
        self.stdout.write(self.style.SUCCESS(f'Created tenant "{tenant.name}"'))

        # --- Step 2: Prompt for tenant admin info, with collision checks ---
        while True:
            admin_username = options['admin_username'] or input("Enter tenant admin username: ")
            if User.objects.filter(username=admin_username).exists():
                self.stdout.write(self.style.ERROR(f'Username "{admin_username}" already exists. Choose a different one.'))
                options['admin_username'] = None  # force prompt again
                continue
            break

        while True:
            admin_email = options['admin_email'] or input("Enter tenant admin email: ")
            if User.objects.filter(email=admin_email).exists():
                self.stdout.write(self.style.ERROR(f'Email "{admin_email}" already exists. Choose a different one.'))
                options['admin_email'] = None
                continue
            break

        # Password prompt
        admin_password = options['admin_password']
        while not admin_password:
            password1 = getpass.getpass("Enter tenant admin password: ")
            password2 = getpass.getpass("Confirm password: ")
            if password1 != password2:
                self.stdout.write(self.style.ERROR("Passwords do not match. Please try again."))
            else:
                admin_password = password1

        # --- Step 3: Create tenant admin user ---
        admin_user = User.objects.create_user(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            is_staff=True,
            is_superuser=False,
            tenant=tenant
        )
        self.stdout.write(self.style.SUCCESS(f'Created tenant admin user "{admin_user.username}"'))

        # --- Step 4: Detect all models that use TenantAdminMixin ---
        tenanted_models = [
            model for model in apps.get_models()
            if any(issubclass(base, TenantMixin) for base in model.__mro__)
        ]

        # --- Step 5: Assign tenant to all objects in these models where tenant is null ---
        for model in tenanted_models:
            updated_count = model.objects.filter(tenant__isnull=True).update(tenant=tenant)
            self.stdout.write(self.style.SUCCESS(
                f'Assigned {updated_count} objects in {model._meta.label} to tenant "{tenant.name}"'
            ))

        self.stdout.write(self.style.SUCCESS('Bootstrap completed successfully!'))
