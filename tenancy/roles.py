"""
Tenancy-specific role management system.

This module provides a self-contained permission system for the tenancy package
that is completely independent of Django's is_superuser and is_staff flags.

Roles:
- tenantadmin: Can access super admin site to create/manage tenants
- tenantmanager: Can access tenant admin site to manage tenant-specific content
"""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class TenancyRole(models.Model):
    """
    Stores tenancy-specific roles for users.

    This model creates a many-to-many relationship between users and their
    tenancy roles, completely separate from Django's permission system.
    """

    TENANT_ADMIN = 'tenantadmin'
    TENANT_MANAGER = 'tenantmanager'

    ROLE_CHOICES = [
        (TENANT_ADMIN, 'Tenant Admin - Can create and manage tenants'),
        (TENANT_MANAGER, 'Tenant Manager - Can manage tenant-specific content'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tenancy_roles',
        help_text="User who has this tenancy role"
    )

    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        help_text="Tenancy-specific role"
    )

    # Optional: Link to specific tenant for tenant managers
    tenant = models.ForeignKey(
        'tenancy.Tenant',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='role_assignments',
        help_text="Specific tenant this role applies to (only for tenantmanager role)"
    )

    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tenancy_roles_assigned',
        help_text="User who assigned this role"
    )

    class Meta:
        unique_together = [['user', 'role', 'tenant']]
        indexes = [
            models.Index(fields=['user', 'role']),
            models.Index(fields=['tenant']),
        ]
        verbose_name = 'Tenancy Role'
        verbose_name_plural = 'Tenancy Roles'

    def __str__(self):
        if self.tenant:
            return f"{self.user} - {self.get_role_display()} ({self.tenant})"
        return f"{self.user} - {self.get_role_display()}"

    def clean(self):
        """Validate role assignment rules"""
        super().clean()

        # Tenant admins should not be tied to specific tenants
        if self.role == self.TENANT_ADMIN and self.tenant:
            raise ValidationError({
                'tenant': 'Tenant admin role cannot be assigned to a specific tenant. '
                         'Tenant admins have system-wide access.'
            })

        # Tenant managers should be tied to specific tenants
        if self.role == self.TENANT_MANAGER and not self.tenant:
            raise ValidationError({
                'tenant': 'Tenant manager role must be assigned to a specific tenant.'
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TenancyRoleManager:
    """
    Helper class for checking and managing tenancy roles.

    Usage:
        from tenancy.roles import roles

        if roles.is_tenant_admin(request.user):
            # Allow access to super admin

        if roles.is_tenant_manager(request.user, request.tenant):
            # Allow access to tenant admin
    """

    @staticmethod
    def is_tenant_admin(user):
        """
        Check if user has tenant admin role.

        Tenant admins can:
        - Access the super admin site (/admin)
        - Create new tenants
        - Manage all tenants
        - View cross-tenant data
        """
        if not user or not user.is_authenticated:
            return False

        return TenancyRole.objects.filter(
            user=user,
            role=TenancyRole.TENANT_ADMIN
        ).exists()

    @staticmethod
    def is_tenant_manager(user, tenant=None):
        """
        Check if user has tenant manager role.

        Tenant managers can:
        - Access the tenant admin site (/manage)
        - Manage content within their assigned tenant(s)
        - Create and edit users for their tenant

        Args:
            user: Django user object
            tenant: Optional Tenant object to check specific tenant access
        """
        if not user or not user.is_authenticated:
            return False

        query = TenancyRole.objects.filter(
            user=user,
            role=TenancyRole.TENANT_MANAGER
        )

        # If checking for specific tenant, filter by it
        if tenant:
            query = query.filter(tenant=tenant)

        return query.exists()

    @staticmethod
    def get_managed_tenants(user):
        """
        Get all tenants that a user can manage.
        """
        if not user or not user.is_authenticated:
            from tenancy.models import Tenant
            return Tenant.objects.none()

        # If user is tenant admin, return all tenants
        if TenancyRoleManager.is_tenant_admin(user):
            from tenancy.models import Tenant
            return Tenant.objects.all()

        # Otherwise return only tenants they're assigned to manage
        tenant_ids = TenancyRole.objects.filter(
            user=user,
            role=TenancyRole.TENANT_MANAGER
        ).values_list('tenant_id', flat=True)

        from tenancy.models import Tenant
        return Tenant.objects.filter(id__in=tenant_ids)

    @staticmethod
    def assign_role(user, role, tenant=None, assigned_by=None):
        """
        Assign a tenancy role to a user.
        """
        role_obj, created = TenancyRole.objects.get_or_create(
            user=user,
            role=role,
            tenant=tenant,
            defaults={'assigned_by': assigned_by}
        )
        return role_obj

    @staticmethod
    def revoke_role(user, role, tenant=None):
        """
        Revoke a tenancy role from a user.
        """
        return TenancyRole.objects.filter(
            user=user,
            role=role,
            tenant=tenant
        ).delete()[0]

    @staticmethod
    def has_any_tenancy_role(user):
        """
        Check if user has any tenancy role.
        """
        if not user or not user.is_authenticated:
            return False

        return TenancyRole.objects.filter(user=user).exists()


# Singleton instance for easy importing
roles = TenancyRoleManager()