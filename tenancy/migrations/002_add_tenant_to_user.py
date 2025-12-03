# tenancy/migrations/002_add_tenant_to_user.py
from django.db import migrations, models
import django.db.models.deletion


def skip_if_custom_user(apps, schema_editor):
    """
    Helper to skip the migration if a custom user model is used.
    """
    UserModel = apps.get_model('auth', 'User')
    if UserModel._meta.label != 'auth.User':
        # Custom user, skip migration
        return False
    return True


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),  # adjust for your Django version
    ]

    operations = [
        # Conditionally add tenant FK only if default user model is used
        migrations.AddField(
            model_name='user',
            name='tenant',
            field=models.ForeignKey(
                to='tenancy.Tenant',
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='users',
            ),
        ),
    ]

    # Optional: skip for custom user
    def apply(self, project_state, schema_editor, collect_sql=False):
        UserModel = project_state.apps.get_model('auth', 'User')
        if UserModel._meta.label != 'auth.User':
            # Skip adding field
            return project_state
        return super().apply(project_state, schema_editor, collect_sql)
