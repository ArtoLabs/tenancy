import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps

from .models import Tenant
from .mixins import CloneForTenantMixin

import inspect


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
        
        for model in apps.get_models():
            if issubclass(model, CloneForTenantMixin):
                print("MODEL:", model.__name__)
                # What object are we about to call?
                attr = getattr(model, "clone_defaults_for_new_tenant", None)
                print("  has_attr:", bool(attr))
                if attr:
                    # show where the function is defined
                    try:
                        fn = attr.__func__ if hasattr(attr, "__func__") else attr
                        print("  defined in:", fn.__module__)
                        print("  source snippet:")
                        print("\n".join(inspect.getsource(fn).splitlines()[:20]))
                    except Exception as e:
                        print("  cannot show source:", e)

                # Check whether template rows exist for this model (use model.get_template_queryset)
                try:
                    qs = model.get_template_queryset()
                    print("  template queryset count:", qs.count())
                    print("  example templates:", list(qs[:3]))
                except Exception as e:
                    print("  get_template_queryset raised:", repr(e))

        for model in cloneable_models:
            print(f"Cloning defaults for model: {model.__name__}")
            logger.info(f"Cloning defaults for model: {model.__name__}")
            model.clone_defaults_for_new_tenant(tenant.id)

        return tenant, user