# tenancy/migrations/002_add_tenant_to_user.py
from django.db import migrations, models
import django.db.models.deletion

def add_tenant_fk_to_default_user(apps, schema_editor):
    UserModel = apps.get_model('auth', 'User')
    TenantModel = apps.get_model('tenancy', 'Tenant')

    if UserModel._meta.label != 'auth.User':
        return

    field = models.ForeignKey(
        TenantModel,
        null=True,
        blank=True,
        on_delete=django.db.models.deletion.PROTECT,
        related_name='users',
        db_column='tenant_id',
    )
    field.set_attributes_from_name('tenant')
    schema_editor.add_field(UserModel, field)


def remove_tenant_fk_from_default_user(apps, schema_editor):
    UserModel = apps.get_model('auth', 'User')
    if UserModel._meta.label != 'auth.User':
        return
    field = UserModel._meta.get_field('tenant')
    schema_editor.remove_field(UserModel, field)


class Migration(migrations.Migration):
    atomic = False  # <-- important for MySQL

    dependencies = [
        ('tenancy', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(
            add_tenant_fk_to_default_user,
            remove_tenant_fk_from_default_user
        ),
    ]
