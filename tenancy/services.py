import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps

from .models import Tenant
from .utils import clone_all_template_objects

User = get_user_model()
logger = logging.getLogger(__name__)


class TenantProvisioningError(Exception):
    """Raised when tenant provisioning fails."""
    pass


class TenantProvisioner:
    """
    Service class for provisioning new tenants with default data.
    """

    @staticmethod
    @transaction.atomic
    def create_tenant(tenant_data: dict, admin_data: dict):
        """
        Create a new tenant with admin user and clone all template objects.

        This method:
        1. Creates the tenant record
        2. Creates the admin user for the tenant
        3. Automatically clones all template objects from the template tenant
        4. Respects each model's cloning mode (full/skeleton/field overrides)
        5. Handles foreign key dependencies automatically

        Args:
            tenant_data: Dictionary with tenant information
                {
                    'name': str,
                    'domain': str,
                    'is_active': bool (optional, default=True)
                }

            admin_data: Dictionary with admin user information
                {
                    'username': str,
                    'email': str,
                    'password': str
                }

        Returns:
            Tuple of (tenant, user, clone_map)
            - tenant: The created Tenant instance
            - user: The created admin User instance
            - clone_map: Dictionary mapping model classes to cloned objects

        Raises:
            TenantProvisioningError: If tenant creation or cloning fails

        Example:
            >>> tenant_data = {
            ...     'name': 'Acme Corp',
            ...     'domain': 'acme.example.com',
            ...     'is_active': True
            ... }
            >>> admin_data = {
            ...     'username': 'admin@acme.com',
            ...     'email': 'admin@acme.com',
            ...     'password': 'secure_password_123'
            ... }
            >>> tenant, user, cloned = TenantProvisioner.create_tenant(
            ...     tenant_data, admin_data
            ... )
            >>> print(f"Created tenant: {tenant.name}")
            >>> print(f"Cloned {sum(len(objs) for objs in cloned.values())} objects")
        """
        try:
            # Step 1: Create the tenant
            logger.info(f"Creating new tenant: {tenant_data['name']}")
            tenant = Tenant.objects.create(
                name=tenant_data['name'],
                domain=tenant_data['domain'],
                is_active=tenant_data.get('is_active', True)
            )
            logger.info(f"✓ Tenant created: {tenant.name} (id={tenant.id})")

            # Step 2: Create admin user for the tenant
            logger.info(f"Creating admin user: {admin_data['username']}")
            user = User.objects.create_user(
                username=admin_data['username'],
                email=admin_data.get('email', ''),
                password=admin_data['password'],
                tenant=tenant,
            )
            user.is_staff = True
            user.is_superuser = False
            user.save()
            logger.info(f"✓ Admin user created: {user.username} (id={user.id})")

            # Step 3: Clone all template objects for the new tenant
            # This automatically:
            # - Discovers all models using TenantMixin
            # - Respects each model's CLONE_MODE or CLONE_FIELD_OVERRIDES
            # - Clones in topological order (handles FK dependencies)
            # - Returns a map of old IDs to new instances
            logger.info("=" * 60)
            logger.info("Beginning template object cloning...")
            logger.info("=" * 60)

            clone_map = clone_all_template_objects(
                new_tenant=tenant,
                # template_tenant=None,  # Uses first tenant by default
                # excluded_models=[],    # Optionally exclude specific models
                # field_overrides={}     # Optionally override fields at runtime
            )

            # Log cloning summary
            total_cloned = sum(len(objects) for objects in clone_map.values())
            logger.info("=" * 60)
            logger.info(f"✓ Cloning complete: {total_cloned} objects across {len(clone_map)} models")
            logger.info("=" * 60)

            # Log per-model breakdown
            for model_class, cloned_objects in clone_map.items():
                logger.info(
                    f"  • {model_class.__name__}: {len(cloned_objects)} objects"
                )

            return tenant, user #, clone_map

        except Exception as e:
            logger.error(f"Failed to create tenant: {e}", exc_info=True)
            raise TenantProvisioningError(
                f"Tenant provisioning failed: {str(e)}"
            ) from e

    @staticmethod
    @transaction.atomic
    def create_tenant_with_custom_overrides(
            tenant_data: dict,
            admin_data: dict,
            field_overrides: dict = None,
            excluded_models: list = None
    ):
        """
        Create a tenant with custom field overrides for specific models.

        Use this method when you need to override specific fields during cloning
        beyond what's defined in model-level metadata.

        Args:
            tenant_data: Tenant information dictionary
            admin_data: Admin user information dictionary
            field_overrides: Dictionary mapping model classes to field overrides
                Example: {
                    SiteConfiguration: {'is_default': True},
                    Theme: {'name': 'Custom Theme'}
                }
            excluded_models: List of model classes to skip cloning
                Example: [LargeMediaFile, DeprecatedModel]

        Returns:
            Tuple of (tenant, user, clone_map)

        Example:
            >>> from myapp.models import SiteConfiguration, Theme
            >>>
            >>> tenant, user, cloned = TenantProvisioner.create_tenant_with_custom_overrides(
            ...     tenant_data={'name': 'Custom Corp', 'domain': 'custom.example.com'},
            ...     admin_data={'username': 'admin', 'password': 'pass123'},
            ...     field_overrides={
            ...         SiteConfiguration: {'is_default': True, 'custom_field': 'value'},
            ...         Theme: {'name': 'Branded Theme'}
            ...     },
            ...     excluded_models=[LargeMediaFile]
            ... )
        """
        try:
            # Create tenant and admin user
            logger.info(f"Creating tenant with custom overrides: {tenant_data['name']}")
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

            logger.info(f"✓ Tenant and admin created")
            logger.info("Beginning custom cloning with overrides...")

            # Clone with custom configuration
            clone_map = clone_all_template_objects(
                new_tenant=tenant,
                excluded_models=excluded_models or [],
                field_overrides=field_overrides or {}
            )

            total_cloned = sum(len(objects) for objects in clone_map.values())
            logger.info(f"✓ Cloned {total_cloned} objects with custom overrides")

            return tenant, user, clone_map

        except Exception as e:
            logger.error(f"Failed to create tenant with overrides: {e}", exc_info=True)
            raise TenantProvisioningError(
                f"Custom tenant provisioning failed: {str(e)}"
            ) from e

    @staticmethod
    def get_cloning_preview():
        """
        Preview which models will be cloned and their cloning modes.

        Useful for debugging or documentation purposes to see what will
        happen when a new tenant is created.

        Returns:
            List of dictionaries with model information

        Example:
            >>> preview = TenantProvisioner.get_cloning_preview()
            >>> for info in preview:
            ...     print(f"{info['model']}: {info['mode']} ({info['count']} objects)")
            Theme: full (5 objects)
            Font: full (10 objects)
            SiteConfiguration: skeleton (1 objects)
        """
        from .utils import get_all_tenant_models, _get_clone_mode
        from .models import Tenant

        template_tenant = Tenant.objects.order_by("id").first()
        if not template_tenant:
            return []

        preview = []
        tenant_models = get_all_tenant_models()

        for model in tenant_models:
            # Get template queryset
            if hasattr(model, 'get_template_queryset'):
                qs = model.get_template_queryset()
            else:
                qs = model.objects.filter(tenant=template_tenant)

            # Get cloning mode
            clone_mode = _get_clone_mode(model)

            # Check for metadata
            has_overrides = hasattr(model, 'CLONE_FIELD_OVERRIDES')
            overrides = getattr(model, 'CLONE_FIELD_OVERRIDES', {}) if has_overrides else {}

            preview.append({
                'model': model.__name__,
                'count': qs.count(),
                'mode': clone_mode,
                'has_overrides': has_overrides,
                'overrides': overrides,
            })

        return preview

    @staticmethod
    def log_cloning_preview():
        """
        Log a preview of what will be cloned to the console.

        Example output:
            ╔════════════════════════════════════════════════════════╗
            ║          TENANT CLONING PREVIEW                        ║
            ╚════════════════════════════════════════════════════════╝

            Font (10 objects) → full clone
            Theme (5 objects) → full clone
            SiteConfiguration (1 objects) → skeleton clone
              ↳ Overrides: title_font=None, body_font=None
        """
        preview = TenantProvisioner.get_cloning_preview()

        print("\n" + "=" * 60)
        print("TENANT CLONING PREVIEW")
        print("=" * 60 + "\n")

        if not preview:
            print("⚠️  No template tenant found or no models to clone")
            return

        for info in preview:
            mode_str = f"→ {info['mode']} clone"
            print(f"{info['model']} ({info['count']} objects) {mode_str}")

            if info['has_overrides']:
                override_str = ", ".join(
                    f"{k}={v}" for k, v in info['overrides'].items()
                )
                print(f"  ↳ Overrides: {override_str}")

        print("\n" + "=" * 60 + "\n")