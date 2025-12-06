from django.db import models
from django.forms.models import model_to_dict

from .managers import TenantManager
from .models import Tenant


class TenantUserMixin(models.Model):
    """
    Mixin to add tenant field to custom user models.

    Projects should add this to their custom user model to enable
    multi-tenancy support for users.

    Usage:
        from django.contrib.auth.models import AbstractUser
        from tenancy.mixins import TenantUserMixin

        class User(TenantUserMixin, AbstractUser):
            # Your custom fields here
            pass

    The tenant field is:
    - nullable: Allows creation of superusers without a tenant
    - blank: Allows forms to be submitted without a tenant
    - PROTECT: Prevents deletion of a tenant that has users
    """
    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='users'
    )

    class Meta:
        abstract = True


class TenantMixin(models.Model):
    """
    Mixin to add tenant support and cloning capabilities to any Django model.

    This mixin provides:
    - A foreign key to the Tenant model
    - A custom manager (TenantManager) with tenant-aware methods
    - Automatic tenant assignment on save
    - Helper method to identify tenant models
    - Ability to clone template objects (tenant=None) for new tenants

    Usage:
        class MyModel(TenantMixin):
            name = models.CharField(max_length=100)
            # ... other fields
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='%(app_label)s_%(class)s_set',
        verbose_name='Tenant',
        db_index=True,
        null=True,
        blank=True,
    )

    # Use custom manager that provides tenant-aware query methods
    objects = TenantManager()

    # Fields to exclude when cloning objects
    CLONE_EXCLUDE_FIELDS = ("id", "pk")

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['tenant']),
        ]

    def save(self, *args, **kwargs):
        """
        Override save to automatically set tenant from context if not set.
        """
        if not self.tenant_id:
            from .context import get_current_tenant
            current_tenant = get_current_tenant()

            if current_tenant is None:
                raise ValueError(
                    f"Cannot save {self.__class__.__name__} without an active tenant. "
                    "Either set the tenant explicitly or ensure middleware is active."
                )

            self.tenant = current_tenant

        super().save(*args, **kwargs)

    @classmethod
    def _is_tenant_model(cls):
        """
        Helper method to identify if a model uses the tenant mixin.
        """
        return hasattr(cls, 'tenant')

    # ------------------------------
    # Cloning methods from CloneForTenantMixin
    # ------------------------------

    @classmethod
    def get_template_queryset(cls):
        """
        Returns a queryset of template rows for cloning (tenant=None).
        """
        try:
            template_tenant = Tenant.objects.order_by("id").first()
        except Tenant.DoesNotExist:
            return cls.objects.none()

        if template_tenant is None:
            return cls.objects.none()

        return cls.objects.filter(tenant=template_tenant)

    def clone_for_tenant(self, new_tenant_id, overrides=None):
        """
        Creates a copy of this object for a specific tenant.
        """
        overrides = overrides or {}

        data = model_to_dict(self, exclude=self.CLONE_EXCLUDE_FIELDS)

        # Fetch the Tenant instance
        tenant_instance = Tenant.objects.get(id=new_tenant_id)
        data["tenant"] = tenant_instance  # assign instance, not ID

        # Apply any overrides
        data.update(overrides)

        # Create and return cloned object
        return self.__class__.objects.create(**data)

    @classmethod
    def clone_defaults_for_new_tenant(cls, new_tenant_id):
        """
        Clones all template objects for a new tenant.
        """
        new_instances = []
        for template in cls.get_template_queryset():
            new_instances.append(template.clone_for_tenant(new_tenant_id))
        return new_instances


class TenantAdminMixin:
    """
    Mixin for ModelAdmin classes that should be tenant-scoped in TenantAdminSite.

    This mixin provides complete tenant isolation for the admin interface by:
    - Filtering querysets to show only objects belonging to current tenant
    - Automatically setting tenant on new objects
    - Enforcing tenant-based permissions
    - Filtering foreign key choices to current tenant
    - Hiding the tenant field from forms (it's auto-set)

    Usage in project's admin.py:
        from tenancy.admin import tenant_admin_site
        from tenancy.mixins import TenantAdminMixin

        @admin.register(MyModel, site=tenant_admin_site)
        class MyModelAdmin(TenantAdminMixin, admin.ModelAdmin):
            list_display = ['name', 'description']

    IMPORTANT: Always use this with tenant_admin_site, not the default admin site.
    """

    def get_queryset(self, request):
        """
        Filter queryset to current tenant's objects.

        This is the core of tenant isolation - tenant managers can only
        see objects belonging to their tenant, never objects from other tenants.
        """
        qs = super().get_queryset(request)
        if hasattr(request, 'tenant') and request.tenant:
            if hasattr(qs.model, 'tenant'):
                return qs.filter(tenant=request.tenant)
        return qs

    def save_model(self, request, obj, form, change):
        """
        Automatically set tenant on new objects.

        When a tenant manager creates a new object, we automatically assign
        their tenant. They shouldn't be able to create objects for other tenants.

        Args:
            request: The HttpRequest
            obj: The model instance being saved
            form: The ModelForm instance
            change: Boolean indicating if this is an update (True) or create (False)
        """
        if hasattr(obj, 'tenant') and not change:
            if not getattr(obj, 'tenant_id', None):
                obj.tenant = request.tenant
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        """
        Check if user has permission to access this module.

        Permission requirements:
        1. User must be active and staff
        2. Request must have a tenant (set by middleware)
        3. Either user is superuser OR user belongs to the request's tenant

        This prevents users from accessing the admin for other tenants.
        """
        if not request.user.is_active or not request.user.is_staff:
            return False
        if not hasattr(request, 'tenant') or request.tenant is None:
            return False
        if request.user.is_superuser:
            return True
        if hasattr(request.user, 'tenant'):
            return request.user.tenant == request.tenant
        return True

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def get_exclude(self, request, obj=None):
        """
        Exclude tenant field from forms - it's set automatically.

        Tenant managers shouldn't see or manipulate the tenant field directly.
        It's automatically assigned based on their tenant context.
        """
        exclude = list(super().get_exclude(request, obj) or [])
        if hasattr(self.model, 'tenant') and 'tenant' not in exclude:
            exclude.append('tenant')
        return exclude

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Filter foreign key choices to only show objects from current tenant.

        This ensures tenant isolation extends to related objects. For example,
        if a Product has a foreign key to Category, the dropdown will only
        show categories from the current tenant.

        Only applies to models that use TenantMixin (checked via _is_tenant_model).

        Args:
            db_field: The foreign key field being rendered
            request: The HttpRequest
            **kwargs: Additional arguments for the form field

        Returns:
            FormField configured with tenant-filtered queryset
        """
        model = db_field.remote_field.model

        # Only apply tenant filtering to tenant-aware models
        if hasattr(model, "_is_tenant_model") and model._is_tenant_model():
            tenant = getattr(request, 'tenant', None)
            if tenant:
                kwargs["queryset"] = model.objects.filter(tenant=tenant)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class SuperUserAdminMixin:
    """
    Mixin for ModelAdmin classes in SuperAdminSite.

    This mixin provides cross-tenant visibility for system administrators by:
    - Showing tenant field as readonly
    - Adding tenant_display to list view with ID and domain
    - Showing all objects across all tenants (no filtering)

    Usage in package's admin.py:
        from tenancy.admin import super_admin_site
        from tenancy.mixins import SuperUserAdminMixin

        @admin.register(MyModel, site=super_admin_site)
        class MyModelSuperAdmin(SuperUserAdminMixin, admin.ModelAdmin):
            list_display = ['name', 'description']
            # tenant_display is added automatically

    IMPORTANT: Always use this with super_admin_site, not tenant_admin_site.
    """

    readonly_fields = ('tenant',)

    def tenant_display(self, obj):
        """
        Display tenant information in list view with ID and domain.

        Format: "ID – domain.com"
        Examples:
        - "1 – acme.example.com"
        - "42 – widgets.example.com"
        - "-" (if no tenant)

        This helps superusers quickly identify which tenant owns each object
        and provides the domain for easy reference.

        Args:
            obj: The model instance

        Returns:
            str: Formatted tenant display string
        """
        if hasattr(obj, 'tenant') and obj.tenant:
            return f"{obj.tenant.id} – {obj.tenant.domain}"
        return "-"

    tenant_display.short_description = "Tenant"

    def get_list_display(self, request):
        """
        Add tenant_display to list view.

        This automatically adds the tenant column to any admin using this mixin,
        so superusers always see which tenant each object belongs to.

        The tenant column is added at the end to avoid disrupting the natural
        order of model-specific fields.
        """
        base = list(super().get_list_display(request))
        if 'tenant_display' not in base:
            base.append('tenant_display')
        return base