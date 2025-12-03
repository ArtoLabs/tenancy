from django.apps import AppConfig


class TenancyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenancy'
    verbose_name = 'Multi-Tenancy'

    # def ready(self):
    #     # Import system checks so that Django registers them.
    #     from . import checks  # noqa
    #     return
