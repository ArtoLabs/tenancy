# tenancy/migrations/002_add_tenant_to_user.py
from django.db import migrations, models
from django.conf import settings
from .models import Tenant


def add_tenant_fk_to_default_user(apps, schema_editor):
    """
    Adds the tenant_id column to auth_user ONLY if the project is using
    Django’s default user model.
    """
    UserModel = apps.get_model(settings.AUTH_USER_MODEL.split('.')[0],
                               settings.AUTH_USER_MODEL.split('.')[1])

    # Only patch the default Django user model
    if settings.AUTH_USER_MODEL != "auth.User":
        return

    # Add the column manually
    db_alias = schema_editor.connection.alias
    table = UserModel._meta.db_table

    # Create the nullable column first
    schema_editor.add_field(
        UserModel,
        models.ForeignKey(
            Tenant,
            null=True,
            blank=True,
            on_delete=models.PROTECT,
            related_name='users',
            db_column='tenant_id'
        )
    )


def remove_tenant_fk_from_default_user(apps, schema_editor):
    """
    Reverse: remove the tenant_id column if it exists.
    """
    if settings.AUTH_USER_MODEL != "auth.User":
        return

    UserModel = apps.get_model(settings.AUTH_USER_MODEL.split('.')[0],
                               settings.AUTH_USER_MODEL.split('.')[1])

    field = UserModel._meta.get_field('tenant')

    schema_editor.remove_field(UserModel, field)


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(
            add_tenant_fk_to_default_user,
            remove_tenant_fk_from_default_user,
        ),
    ]
