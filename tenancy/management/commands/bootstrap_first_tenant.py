from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps
from tenancy.models import Tenant
from tenancy.mixins import TenantMixin
from tenancy.roles import roles, TenancyRole
import getpass

User = get_user_model()


class Command(BaseCommand):
    help = 'Bootstrap the first tenant and create initial tenant admin and system admin users.'

    def add_arguments(self, parser):
        # Tenant information
        parser.add_argument('--name', type=str, help="Tenant name")
        parser.add_argument('--domain', type=str, help="Tenant domain (e.g. tenant1.localhost)")

        # Tenant admin (tenant manager)
        parser.add_argument('--admin_username', type=str, help="Tenant admin username")
        parser.add_argument('--admin_email', type=str, help="Tenant admin email")
        parser.add_argument('--admin_password', type=str, help="Tenant admin password (will prompt if not provided)")

        # System admin (tenant admin) - optional
        parser.add_argument('--create_system_admin', action='store_true',
                            help="Also create a system admin user with tenantadmin role")
        parser.add_argument('--system_admin_username', type=str, help="System admin username")
        parser.add_argument('--system_admin_email', type=str, help="System admin email")
        parser.add_argument('--system_admin_password', type=str, help="System admin password")

    @transaction.atomic
    def handle(self, *args, **options):
        if Tenant.objects.exists():
            self.stdout.write(self.style.ERROR('Tenants already exist. Aborting bootstrap.'))
            self.stdout.write(self.style.WARNING('Use the admin interface to create additional tenants.'))
            return

        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('TENANCY SYSTEM BOOTSTRAP'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')
        self.stdout.write('This command will set up your tenancy system by creating:')
        self.stdout.write('  1. Your first tenant')
        self.stdout.write('  2. A tenant manager user for that tenant')
        self.stdout.write('  3. (Optional) A system admin user who can create more tenants')
        self.stdout.write('')

        # --- Step 1: Collect tenant information ---
        self.stdout.write(self.style.SUCCESS('Step 1: Tenant Information'))
        self.stdout.write('-' * 70)

        name = options['name'] or input("Enter tenant name: ")
        domain = options['domain'] or input("Enter tenant domain (e.g. tenant1.localhost): ")

        # Create the first tenant
        tenant = Tenant.objects.create(
            name=name,
            domain=domain,
            is_active=True
        )
        self.stdout.write(self.style.SUCCESS(f'✓ Created tenant "{tenant.name}" with domain "{tenant.domain}"'))
        self.stdout.write('')

        # --- Step 2: Create tenant manager user ---
        self.stdout.write(self.style.SUCCESS('Step 2: Tenant Manager User'))
        self.stdout.write('-' * 70)
        self.stdout.write('This user will manage the tenant at: http://{}/manage/'.format(domain))
        self.stdout.write('')

        # Prompt for tenant admin username with collision check
        while True:
            admin_username = options['admin_username'] or input("Enter tenant manager username: ")
            if User.objects.filter(username=admin_username).exists():
                self.stdout.write(
                    self.style.ERROR(f'Username "{admin_username}" already exists. Choose a different one.'))
                options['admin_username'] = None  # force prompt again
                continue
            break

        # Prompt for tenant admin email with collision check
        while True:
            admin_email = options['admin_email'] or input("Enter tenant manager email: ")
            if User.objects.filter(email=admin_email).exists():
                self.stdout.write(self.style.ERROR(f'Email "{admin_email}" already exists. Choose a different one.'))
                options['admin_email'] = None
                continue
            break

        # Password prompt
        admin_password = options['admin_password']
        while not admin_password:
            password1 = getpass.getpass("Enter tenant manager password: ")
            password2 = getpass.getpass("Confirm password: ")
            if password1 != password2:
                self.stdout.write(self.style.ERROR("Passwords do not match. Please try again."))
            else:
                admin_password = password1

        # Create tenant manager user
        # CHANGED: Removed is_staff and is_superuser flags - these are no longer used
        tenant_manager = User.objects.create_user(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            tenant=tenant  # Assign to the tenant
        )

        # CHANGED: Assign tenantmanager role instead of setting is_staff=True
        roles.assign_role(
            user=tenant_manager,
            role=TenancyRole.TENANT_MANAGER,
            tenant=tenant,
            assigned_by=None  # No one assigned it, it's bootstrap
        )

        self.stdout.write(self.style.SUCCESS(f'✓ Created tenant manager user "{tenant_manager.username}"'))
        self.stdout.write(self.style.SUCCESS(f'✓ Assigned tenantmanager role for tenant "{tenant.name}"'))
        self.stdout.write('')

        # --- Step 3: Optionally create system admin ---
        create_system_admin = options['create_system_admin']

        if not create_system_admin:
            # Ask if they want to create a system admin
            self.stdout.write(self.style.SUCCESS('Step 3: System Admin (Optional)'))
            self.stdout.write('-' * 70)
            self.stdout.write('A system admin can access /admin/ to create and manage tenants.')
            self.stdout.write('You can create one now or do it later.')
            self.stdout.write('')

            response = input("Create a system admin now? (y/n): ").lower()
            create_system_admin = response in ['y', 'yes']

        if create_system_admin:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Creating System Admin'))
            self.stdout.write('-' * 70)
            self.stdout.write('This user will access the system admin at: /admin/')
            self.stdout.write('')

            # Prompt for system admin username
            while True:
                system_admin_username = options['system_admin_username'] or input("Enter system admin username: ")
                if User.objects.filter(username=system_admin_username).exists():
                    self.stdout.write(
                        self.style.ERROR(f'Username "{system_admin_username}" already exists. Choose a different one.'))
                    options['system_admin_username'] = None
                    continue
                break

            # Prompt for system admin email
            while True:
                system_admin_email = options['system_admin_email'] or input("Enter system admin email: ")
                if User.objects.filter(email=system_admin_email).exists():
                    self.stdout.write(
                        self.style.ERROR(f'Email "{system_admin_email}" already exists. Choose a different one.'))
                    options['system_admin_email'] = None
                    continue
                break

            # Password prompt
            system_admin_password = options['system_admin_password']
            while not system_admin_password:
                password1 = getpass.getpass("Enter system admin password: ")
                password2 = getpass.getpass("Confirm password: ")
                if password1 != password2:
                    self.stdout.write(self.style.ERROR("Passwords do not match. Please try again."))
                else:
                    system_admin_password = password1

            # Create system admin user
            # CHANGED: No is_staff or is_superuser flags, no tenant assignment
            system_admin = User.objects.create_user(
                username=system_admin_username,
                email=system_admin_email,
                password=system_admin_password,
                tenant=None  # System admins are not tied to a specific tenant
            )

            # CHANGED: Assign tenantadmin role instead of setting is_superuser=True
            roles.assign_role(
                user=system_admin,
                role=TenancyRole.TENANT_ADMIN,
                tenant=None,  # Tenant admins have system-wide access
                assigned_by=None
            )

            self.stdout.write(self.style.SUCCESS(f'✓ Created system admin user "{system_admin.username}"'))
            self.stdout.write(self.style.SUCCESS(f'✓ Assigned tenantadmin role (system-wide access)'))
            self.stdout.write('')

        # --- Summary ---
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('BOOTSTRAP COMPLETE!'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Your tenancy system is now set up:'))
        self.stdout.write('')
        self.stdout.write(f'Tenant Manager Access:')
        self.stdout.write(f'  URL:      http://{domain}/manage/')
        self.stdout.write(f'  Username: {tenant_manager.username}')
        self.stdout.write(f'  Role:     tenantmanager for "{tenant.name}"')
        self.stdout.write('')

        if create_system_admin:
            self.stdout.write(f'System Admin Access:')
            self.stdout.write(f'  URL:      /admin/')
            self.stdout.write(f'  Username: {system_admin.username}')
            self.stdout.write(f'  Role:     tenantadmin (system-wide)')
            self.stdout.write('')
        else:
            self.stdout.write(self.style.WARNING('No system admin created.'))
            self.stdout.write('To create one later, run:')
            self.stdout.write('')
            self.stdout.write('  python manage.py shell')
            self.stdout.write('  >>> from django.contrib.auth import get_user_model')
            self.stdout.write('  >>> from tenancy.roles import roles, TenancyRole')
            self.stdout.write('  >>> User = get_user_model()')
            self.stdout.write(
                '  >>> user = User.objects.create_user(username="admin", email="admin@example.com", password="password")')
            self.stdout.write('  >>> roles.assign_role(user, TenancyRole.TENANT_ADMIN, None)')
            self.stdout.write('')

        self.stdout.write(self.style.SUCCESS('Next Steps:'))
        self.stdout.write('  1. Configure your /etc/hosts or DNS to point domain to your server')
        self.stdout.write(f'     Example: 127.0.0.1  {domain}')
        self.stdout.write('  2. Start your development server: python manage.py runserver')
        self.stdout.write(f'  3. Access tenant manager at: http://{domain}:8000/manage/')
        if create_system_admin:
            self.stdout.write('  4. Access system admin at: http://localhost:8000/admin/')
            self.stdout.write('  5. Create additional tenants via system admin')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Happy tenant managing! 🎉'))