"""
Management command to debug tenancy permissions for a specific user.

Usage:
    python manage.py debug_tenancy_permissions <username>
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from tenancy.models import Tenant
from tenancy.roles import roles, TenancyRole

User = get_user_model()


class Command(BaseCommand):
    help = 'Debug tenancy permissions for a specific user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to check')

    def handle(self, *args, **options):
        username = options['username']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User "{username}" not found'))
            return

        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS(f'TENANCY PERMISSIONS DEBUG: {username}'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')

        # Basic user info
        self.stdout.write(self.style.SUCCESS('User Information:'))
        self.stdout.write(f'  Username: {user.username}')
        self.stdout.write(f'  Email: {user.email}')
        self.stdout.write(f'  Active: {user.is_active}')
        self.stdout.write(f'  Authenticated: {user.is_authenticated}')

        # Check if user has tenant field
        if hasattr(user, 'tenant'):
            self.stdout.write(f'  Assigned Tenant: {user.tenant if user.tenant else "None"}')
        else:
            self.stdout.write(f'  Assigned Tenant: N/A (User model has no tenant field)')

        self.stdout.write('')

        # Check tenancy roles
        self.stdout.write(self.style.SUCCESS('Tenancy Roles:'))

        user_roles = TenancyRole.objects.filter(user=user)
        if not user_roles.exists():
            self.stdout.write(self.style.WARNING('  No tenancy roles assigned'))
        else:
            for role in user_roles:
                self.stdout.write(f'  ✓ {role.get_role_display()}')
                if role.tenant:
                    self.stdout.write(f'    Tenant: {role.tenant.name} ({role.tenant.domain})')
                else:
                    self.stdout.write(f'    Scope: System-wide')
                self.stdout.write(f'    Assigned: {role.assigned_at}')
                if role.assigned_by:
                    self.stdout.write(f'    Assigned by: {role.assigned_by.username}')

        self.stdout.write('')

        # Check tenant admin status
        self.stdout.write(self.style.SUCCESS('Tenant Admin Status:'))
        is_tenant_admin = roles.is_tenant_admin(user)
        if is_tenant_admin:
            self.stdout.write(self.style.SUCCESS('  ✓ User IS a tenant admin'))
            self.stdout.write('    Can access: /admin/')
            self.stdout.write('    Can access: All /manage/ sites for all tenants')
            self.stdout.write('    Can create: New tenants')
        else:
            self.stdout.write(self.style.ERROR('  ✗ User is NOT a tenant admin'))
            self.stdout.write('    Cannot access: /admin/')

        self.stdout.write('')

        # Check tenant manager status
        self.stdout.write(self.style.SUCCESS('Tenant Manager Status:'))

        # Get all managed tenants
        managed_tenants = roles.get_managed_tenants(user)

        if is_tenant_admin:
            self.stdout.write(self.style.SUCCESS('  ✓ User is tenant admin - can manage ALL tenants'))
            self.stdout.write(f'    Total tenants: {Tenant.objects.count()}')
        elif managed_tenants.exists():
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ User is tenant manager for {managed_tenants.count()} tenant(s):'))
            for tenant in managed_tenants:
                self.stdout.write(f'    - {tenant.name} ({tenant.domain})')
                self.stdout.write(f'      Can access: http://{tenant.domain}/manage/')
        else:
            self.stdout.write(self.style.ERROR('  ✗ User is NOT a tenant manager'))
            self.stdout.write('    Cannot access: Any /manage/ sites')

        self.stdout.write('')

        # Test access to each tenant
        all_tenants = Tenant.objects.all()
        if all_tenants.exists():
            self.stdout.write(self.style.SUCCESS('Access Check by Tenant:'))
            for tenant in all_tenants:
                can_access = roles.is_tenant_admin(user) or roles.is_tenant_manager(user, tenant)

                if can_access:
                    access_type = "tenant admin" if roles.is_tenant_admin(user) else "tenant manager"
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✓ {tenant.name} ({tenant.domain})')
                    )
                    self.stdout.write(f'    Access: YES (as {access_type})')
                    self.stdout.write(f'    URL: http://{tenant.domain}/manage/')
                else:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ {tenant.name} ({tenant.domain})')
                    )
                    self.stdout.write(f'    Access: NO')
                    self.stdout.write(f'    Expected: 404 Not Found')
        else:
            self.stdout.write(self.style.WARNING('No tenants exist in the system'))

        self.stdout.write('')

        # Summary
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 70))

        if is_tenant_admin:
            self.stdout.write(self.style.SUCCESS('This user has FULL SYSTEM ACCESS as a tenant admin'))
        elif managed_tenants.exists():
            self.stdout.write(
                self.style.SUCCESS(
                    f'This user can manage {managed_tenants.count()} tenant(s) as a tenant manager'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING('This user has NO tenancy permissions')
            )
            self.stdout.write('')
            self.stdout.write('To grant permissions:')
            self.stdout.write('  1. For tenant admin (system-wide):')
            self.stdout.write(f'     roles.assign_role(user, TenancyRole.TENANT_ADMIN, None)')
            self.stdout.write('  2. For tenant manager (specific tenant):')
            self.stdout.write(f'     roles.assign_role(user, TenancyRole.TENANT_MANAGER, tenant)')