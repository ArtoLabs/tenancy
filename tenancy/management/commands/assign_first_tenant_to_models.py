from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps

from tenancy.mixins import TenantMixin

from tenancy.models import Tenant

User = get_user_model()


class Command(BaseCommand):
    help = 'Assign the first tenant to all models that contain TenantMixin.'

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = Tenant.objects.first()

        if tenant is None:
            self.stdout.write(
                self.style.ERROR('No Tenant found. Create at least one Tenant before running this command.')
            )
            return

        # Detect all models that use TenantMixin
        tenanted_models = [
            model for model in apps.get_models()
            if any(issubclass(base, TenantMixin) for base in model.__mro__)
        ]

        if not tenanted_models:
            self.stdout.write(self.style.WARNING('No models found using TenantMixin.'))
            return

        for model in tenanted_models:
            updated_count = model.objects.filter(tenant__isnull=True).update(tenant=tenant)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Assigned {updated_count} objects in {model._meta.label} to tenant "{tenant.name}"'
                )
            )

        self.stdout.write(self.style.SUCCESS('Bootstrap completed successfully!'))