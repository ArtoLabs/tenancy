# Django Multi-Tenancy Package

A comprehensive Django package for building multi-tenant applications with complete data isolation, intelligent object cloning, and dual admin interfaces.

## Features

- 🏢 **Complete Tenant Isolation** - Every tenant's data is completely separate
- 🔐 **Dual Admin Interfaces** - Separate admin sites for system admins and tenant managers
- 🎨 **Intelligent Object Cloning** - Three cloning modes (full, skeleton, field overrides) with automatic foreign key resolution
- 🔄 **Automatic Tenant Provisioning** - Clone template objects when creating new tenants
- 🛡️ **Permission System** - Tenant managers can view/edit but not create/delete
- 🎯 **Domain-Based Routing** - Automatic tenant detection from hostname
- 🧩 **Plug-and-Play** - Minimal configuration required

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Core Concepts](#core-concepts)
- [Cloning System](#cloning-system)
- [Admin Interfaces](#admin-interfaces)
- [Permission Model](#permission-model)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Installation

Install directly from GitHub:

```bash
pip install git+https://github.com/ArtoLabs/tenancy.git
```

---

## Quick Start

### 1. Add to Installed Apps

```python
# settings.py
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    'tenancy',  # Add this
    
    # Your apps...
]
```

### 2. Add Middleware

```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    'tenancy.middleware.TenantMiddleware',  # Add this - must be AFTER AuthenticationMiddleware
]
```

### 3. Create Custom User Model

```python
# myapp/models.py
from django.contrib.auth.models import AbstractUser
from tenancy.mixins import TenantUserMixin

class User(TenantUserMixin, AbstractUser):
    """Custom user model with tenant support."""
    pass
```

```python
# settings.py
AUTH_USER_MODEL = 'myapp.User'
```

### 4. Add Tenant-Aware Models

```python
# myapp/models.py
from django.db import models
from tenancy.mixins import TenantMixin

class Product(TenantMixin):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return self.name
```

### 5. Configure URLs

```python
# urls.py
from django.urls import path, include
from tenancy.admin import super_admin_site, tenant_admin_site

urlpatterns = [
    path('admin/', super_admin_site.urls),    # System admin at /admin
    path('manage/', tenant_admin_site.urls),  # Tenant admin at /manage
    # Your other URLs...
]
```

### 6. Register Models in Admin

```python
# myapp/admin.py
from django.contrib import admin
from tenancy.admin import tenant_admin_site, super_admin_site
from tenancy.mixins import TenantAdminMixin, SuperUserAdminMixin
from .models import Product

# Tenant admin (for tenant managers at /manage)
@admin.register(Product, site=tenant_admin_site)
class ProductTenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'price']
    search_fields = ['name']

# Super admin (for system admins at /admin)
@admin.register(Product, site=super_admin_site)
class ProductSuperAdmin(SuperUserAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'price']  # tenant_display is added automatically
    search_fields = ['name']
```

### 7. Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 8. Create Superuser and First Tenant

```bash
# Create superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver

# Navigate to http://localhost:8000/admin
# Login and create your first tenant (the "template tenant")
```

---

## Configuration

### Settings

```python
# settings.py

# Required: Custom user model with TenantUserMixin
AUTH_USER_MODEL = 'myapp.User'

# Recommended: Logging configuration for debugging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'tenancy': {
            'handlers': ['console'],
            'level': 'INFO',  # Change to 'DEBUG' for detailed cloning logs
        },
    },
}
```

### Development Setup with Multiple Domains

For local development, you'll need to configure your system to route different domains to localhost:

#### Option 1: /etc/hosts (Recommended)

```bash
# /etc/hosts (Linux/Mac)
# C:\Windows\System32\drivers\etc\hosts (Windows)

127.0.0.1   localhost
127.0.0.1   tenant1.localhost
127.0.0.1   tenant2.localhost
127.0.0.1   acme.localhost
```

Then access tenants at:
- `http://tenant1.localhost:8000/manage/`
- `http://tenant2.localhost:8000/manage/`

#### Option 2: dnsmasq (Mac/Linux)

Configure wildcard DNS for `.localhost` domains:

```bash
# Install dnsmasq (Mac)
brew install dnsmasq

# Configure
echo 'address=/.localhost/127.0.0.1' > /usr/local/etc/dnsmasq.conf

# Start service
sudo brew services start dnsmasq
```

---

## Core Concepts

### The Tenant Model

Every tenant has:
- **name**: Display name (e.g., "Acme Corporation")
- **domain**: Unique hostname (e.g., "acme.example.com")
- **is_active**: Whether the tenant can access the system

### TenantMixin

Add `TenantMixin` to any model that should be tenant-scoped:

```python
from tenancy.mixins import TenantMixin

class MyModel(TenantMixin):
    # Your fields here
    pass
```

This provides:
- Automatic `tenant` foreign key
- Tenant-aware manager (`objects`)
- Automatic tenant assignment on save
- Template object cloning capabilities

### TenantUserMixin

Add to your custom User model for tenant-aware users:

```python
from django.contrib.auth.models import AbstractUser
from tenancy.mixins import TenantUserMixin

class User(TenantUserMixin, AbstractUser):
    pass
```

This adds:
- `tenant` foreign key with `PROTECT` on delete
- Allows superusers without a tenant
- Enables tenant-based user filtering

### The Template Tenant

The **first tenant** created (usually ID=1) serves as the **template tenant**:
- Contains "template objects" that define the default configuration
- When a new tenant is created, template objects are cloned
- Only superusers can modify template objects

**Best Practice**: Create your first tenant with domain `template.localhost` and use it exclusively for defining default configurations.

---

## Cloning System

The package provides three cloning modes for flexible object provisioning.

### Mode 1: Full Clone (Default)

Clones all field values from template objects:

```python
class Theme(TenantMixin):
    name = models.CharField(max_length=100)
    primary_color = models.CharField(max_length=7)
    logo = models.ImageField(upload_to='themes/')
    
    # No CLONE_MODE specified = full clone
```

**Result**: New tenant gets exact copies of all theme fields including colors and logo references.

### Mode 2: Skeleton Clone

Creates "blank" objects with intelligent defaults:

```python
class SiteConfig(TenantMixin):
    site_domain_name = models.CharField(max_length=200, blank=True, null=True)
    site_title = models.CharField(max_length=200, blank=True, null=True)
    admin_email = models.EmailField(blank=True, null=True)
    max_users = models.IntegerField(null=True)
    is_active = models.BooleanField(default=True)
    
    CLONE_MODE = 'skeleton'
```

**Skeleton defaults by field type**:
- `CharField/TextField/EmailField` → `""` (empty string)
- `IntegerField/FloatField` → `0`
- `BooleanField` → `False`
- `ForeignKey` → First available instance or `None`
- `DateField/DateTimeField` → `None`
- `JSONField` → `{}`
- Fields with `default=` → Uses that default

**Result**: New tenant gets empty/default values, preventing null `__str__` issues while allowing customization.

### Mode 3: Field-Level Overrides

Clone normally but override specific fields:

```python
class Product(TenantMixin):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_featured = models.BooleanField(default=False)
    
    CLONE_FIELD_OVERRIDES = {
        'sku': '',  # Clear SKU for new tenant
        'is_featured': False,  # Reset featured flag
        # name and price are cloned normally
    }
```

**Result**: `name` and `price` are cloned from template, but `sku` is cleared and `is_featured` is reset.

**⚠️ Precedence Rule**: If both `CLONE_MODE` and `CLONE_FIELD_OVERRIDES` are defined, `CLONE_FIELD_OVERRIDES` takes precedence and a warning is logged.

### Foreign Key Resolution

The cloning system automatically handles foreign key relationships:

```python
class Font(TenantMixin):
    name = models.CharField(max_length=100)
    # Full clone by default

class Theme(TenantMixin):
    name = models.CharField(max_length=100)
    title_font = models.ForeignKey(Font, on_delete=models.SET_NULL, null=True)
    body_font = models.ForeignKey(Font, on_delete=models.SET_NULL, null=True)
    # Full clone by default
```

**Cloning process**:
1. Fonts are cloned first (no dependencies)
2. Themes are cloned second (depend on Fonts)
3. Foreign keys automatically point to newly cloned Font instances

**Uses topological sorting** to ensure dependencies are cloned in the correct order.

### Populating Fields from Tenant

Use Django's `save()` method to populate fields from the tenant:

```python
class SiteConfig(TenantMixin):
    site_domain_name = models.CharField(max_length=200, blank=True, null=True)
    site_title = models.CharField(max_length=200, blank=True, null=True)
    
    CLONE_MODE = 'skeleton'
    
    def save(self, *args, **kwargs):
        # Auto-populate domain from tenant if empty
        if not self.site_domain_name and self.tenant:
            self.site_domain_name = self.tenant.domain
        
        # Auto-generate title if empty
        if not self.site_title and self.tenant:
            self.site_title = f"{self.tenant.name} Site"
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.site_domain_name or f"SiteConfig {self.id}"
```

This pattern allows you to:
- Access tenant properties (`tenant.domain`, `tenant.name`)
- Set derived values during cloning
- Keep logic in your models (not in the package)

---

## Admin Interfaces

The package provides **two separate admin sites** with different purposes:

### Super Admin (`/admin`)

**Purpose**: System-wide management for superusers

**Access**: `http://yourdomain.com/admin`

**Who can access**: Only superusers

**Features**:
- Manage all tenants
- Create new tenants (with provisioning workflow)
- View/edit objects across ALL tenants
- Shows `tenant_display` column in list views
- Can create and delete objects
- Manage system users

**Registering models**:

```python
from tenancy.admin import super_admin_site
from tenancy.mixins import SuperUserAdminMixin

@admin.register(MyModel, site=super_admin_site)
class MyModelSuperAdmin(SuperUserAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'description']
    # tenant_display is added automatically
```

### Tenant Admin (`/manage`)

**Purpose**: Tenant-specific management for tenant staff

**Access**: `http://tenant-domain.com/manage`

**Who can access**: Staff users belonging to the current tenant

**Features**:
- View/edit ONLY current tenant's objects
- Cannot create new objects (provisioned at tenant creation)
- Cannot delete objects (prevents breaking configuration)
- Tenant field is hidden (auto-assigned)
- Foreign key dropdowns show only tenant's objects

**Registering models**:

```python
from tenancy.admin import tenant_admin_site
from tenancy.mixins import TenantAdminMixin

@admin.register(MyModel, site=tenant_admin_site)
class MyModelTenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']
```

### Creating a New Tenant (Super Admin Workflow)

1. Login to super admin: `http://localhost:8000/admin`
2. Click **"Create Tenant"** in the admin index
3. Fill out the form:
   - **Tenant Name**: "Acme Corporation"
   - **Domain**: "acme.localhost"
   - **Active**: ✓
   - **Admin Username**: "admin@acme.com"
   - **Admin Email**: "admin@acme.com"
   - **Admin Password**: (secure password)
4. Click **"Create Tenant"**

**What happens automatically**:
- Tenant record is created
- Admin user is created for the tenant
- ALL template objects are discovered
- Objects are cloned in topological order (respecting dependencies)
- Each model's cloning mode is respected
- Foreign keys are resolved to newly cloned instances

**Result**: The new tenant is fully provisioned and the admin user can login at `http://acme.localhost:8000/manage`

---

## Permission Model

### Tenant Manager Permissions

Tenant managers (staff users belonging to a tenant) can:

✅ **VIEW** objects belonging to their tenant
✅ **EDIT** objects belonging to their tenant

❌ **CREATE** new objects (objects are provisioned during tenant creation)
❌ **DELETE** objects (prevents breaking configuration)
❌ **ACCESS** other tenants' objects

### Why Restrict Create/Delete?

**Design Philosophy**:
1. Template objects are carefully designed by system admins
2. Objects are cloned during tenant provisioning to ensure consistency
3. Manual creation could bypass proper cloning and break foreign key relationships
4. Manual deletion could break dependencies between related objects
5. If a tenant needs configuration reset, superuser re-runs provisioning

**Allowing Edit**:
- Tenant managers can customize cloned objects (colors, text, settings)
- This provides flexibility without risking data integrity

### Superuser Override

Superusers bypass ALL restrictions:
- Can access both `/admin` and `/manage`
- Can create and delete objects
- Can view all tenants' objects
- Useful for debugging and support

---

## Advanced Usage

### Custom Cloning Logic

For complex cloning scenarios, override the cloning methods:

```python
class ComplexModel(TenantMixin):
    name = models.CharField(max_length=100)
    data = models.JSONField(default=dict)
    
    def clone_for_tenant(self, new_tenant_id, overrides=None):
        """Custom cloning logic."""
        overrides = overrides or {}
        
        # Modify data before cloning
        data_copy = self.data.copy()
        data_copy['cloned_at'] = timezone.now().isoformat()
        overrides['data'] = data_copy
        
        return super().clone_for_tenant(new_tenant_id, overrides)
```

### Excluding Models from Cloning

Exclude specific models from automatic cloning:

```python
from tenancy.services import TenantProvisioner
from myapp.models import LargeMediaFile

tenant, user, clone_map = TenantProvisioner.create_tenant_with_custom_overrides(
    tenant_data={'name': 'Acme', 'domain': 'acme.com'},
    admin_data={'username': 'admin', 'password': 'pass'},
    excluded_models=[LargeMediaFile]
)
```

### Runtime Field Overrides

Override fields at provisioning time (beyond model metadata):

```python
from tenancy.services import TenantProvisioner
from myapp.models import SiteConfig, Theme

tenant, user, clone_map = TenantProvisioner.create_tenant_with_custom_overrides(
    tenant_data={'name': 'Acme', 'domain': 'acme.com'},
    admin_data={'username': 'admin', 'password': 'pass'},
    field_overrides={
        SiteConfig: {'is_default': True},
        Theme: {'name': 'Custom Branded Theme'}
    }
)
```

### Programmatic Tenant Creation

Create tenants programmatically in your code:

```python
from tenancy.services import TenantProvisioner, TenantProvisioningError

try:
    tenant, user, clone_map = TenantProvisioner.create_tenant(
        tenant_data={
            'name': 'Acme Corporation',
            'domain': 'acme.example.com',
            'is_active': True
        },
        admin_data={
            'username': 'admin@acme.com',
            'email': 'admin@acme.com',
            'password': 'secure_password_123'
        }
    )
    
    # Access cloned objects
    from myapp.models import Theme
    for old_id, new_theme in clone_map[Theme].items():
        print(f"Cloned Theme {old_id} -> {new_theme.id}")
        
except TenantProvisioningError as e:
    print(f"Failed to create tenant: {e}")
```

### Preview Cloning Before Provisioning

See what will be cloned without creating a tenant:

```python
from tenancy.services import TenantProvisioner

# Get preview information
preview = TenantProvisioner.get_cloning_preview()

for info in preview:
    print(f"{info['model']}: {info['count']} objects ({info['mode']} mode)")
    if info['has_overrides']:
        print(f"  Overrides: {info['overrides']}")

# Or use the formatted logger
TenantProvisioner.log_cloning_preview()
```

### Accessing Clone Map

The clone map provides old ID → new instance mappings:

```python
tenant, user, clone_map = TenantProvisioner.create_tenant(tenant_data, admin_data)

# clone_map structure: {Model: {old_id: new_instance}}
from myapp.models import Product

# Get a specific cloned object
original_product_id = 10
new_product = clone_map[Product][original_product_id]

# Iterate all cloned products
for old_id, new_product in clone_map[Product].items():
    print(f"Product {old_id} cloned as {new_product.id}: {new_product.name}")
```

### Manual Tenant Context

Activate a tenant context manually (e.g., in management commands):

```python
from tenancy.models import Tenant

tenant = Tenant.objects.get(domain='acme.example.com')

# Activate
tenant.activate()

# Now TenantMixin.save() will use this tenant
my_model = MyModel(name="Test")
my_model.save()  # Automatically assigned to tenant

# Deactivate when done
tenant.deactivate()
```

---

## Troubleshooting

### "No active tenant found for domain"

**Problem**: Accessing a domain that doesn't have a tenant.

**Solutions**:
1. Verify the tenant exists: `Tenant.objects.filter(domain='your-domain.com')`
2. Check `is_active=True`
3. Ensure `/etc/hosts` or DNS is configured correctly
4. Verify middleware is installed and after `AuthenticationMiddleware`

### "Cannot save Model without an active tenant"

**Problem**: Trying to save a TenantMixin model outside a tenant context.

**Solutions**:
1. Access via tenant domain (middleware sets context)
2. Manually activate tenant context:
   ```python
   tenant.activate()
   my_model.save()
   tenant.deactivate()
   ```
3. Explicitly set tenant:
   ```python
   my_model.tenant = tenant
   my_model.save()
   ```

### Tenant Manager Can't Login

**Problem**: Tenant manager sees "You don't have permission" when accessing `/manage`.

**Solutions**:
1. Verify user has `is_staff=True`
2. Verify user's `tenant` matches the request's tenant
3. Check user is accessing via their tenant's domain
4. Verify middleware is working (check logs)

### Objects Not Cloning

**Problem**: New tenant has no objects after provisioning.

**Solutions**:
1. Check template tenant has objects: `Model.get_template_queryset()`
2. Verify models use `TenantMixin`
3. Check logs for cloning errors (set `'tenancy'` logger to `DEBUG`)
4. Ensure models are registered in admin (for visibility)

### Foreign Key Errors During Cloning

**Problem**: "FK references object that doesn't exist"

**Solutions**:
1. Ensure related model also uses `TenantMixin`
2. Verify related objects exist in template tenant
3. Check that related model is included in cloning (not excluded)
4. Review topological sort order in logs

### "list object has no attribute ForeignKey"

**Problem**: Error during topological sorting.

**Solutions**:
1. Update to latest version (this was a bug that's been fixed)
2. Check for unusual field definitions on your models
3. Verify all models using `TenantMixin` are concrete (not abstract)

---

## Best Practices

### 1. Template Tenant Setup

Create a dedicated template tenant:

```python
# First tenant created
template = Tenant.objects.create(
    name='Template',
    domain='template.localhost',
    is_active=True
)
```

- Use this ONLY for defining defaults
- Don't use it as a real tenant
- Superusers should carefully curate template objects

### 2. Model Design

**Always provide `__str__` methods that handle None**:

```python
class MyModel(TenantMixin):
    name = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return self.name or f"MyModel {self.id}"
```

This prevents issues when skeleton cloning sets fields to empty string.

**Use appropriate cloning modes**:
- **Full clone**: For shared resources (themes, fonts, categories)
- **Skeleton clone**: For tenant-specific configs (site settings, branding)
- **Field overrides**: For partial cloning with specific nullifications

### 3. Foreign Keys

**Make FKs nullable when using skeleton mode**:

```python
class SiteConfig(TenantMixin):
    theme = models.ForeignKey(Theme, null=True, blank=True)  # Good
    # theme = models.ForeignKey(Theme)  # Bad with skeleton mode
    
    CLONE_MODE = 'skeleton'
```

### 4. Admin Registration

**Always register on both admin sites**:

```python
# Super admin
@admin.register(MyModel, site=super_admin_site)
class MyModelSuperAdmin(SuperUserAdminMixin, admin.ModelAdmin):
    pass

# Tenant admin
@admin.register(MyModel, site=tenant_admin_site)
class MyModelTenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    pass
```

### 5. Testing

**Test with multiple tenants**:

```python
from tenancy.models import Tenant

def test_tenant_isolation():
    tenant1 = Tenant.objects.create(name='T1', domain='t1.test')
    tenant2 = Tenant.objects.create(name='T2', domain='t2.test')
    
    tenant1.activate()
    obj1 = MyModel.objects.create(name='Object 1')
    
    tenant2.activate()
    obj2 = MyModel.objects.create(name='Object 2')
    
    # Verify isolation
    assert MyModel.objects.filter(tenant=tenant1).count() == 1
    assert MyModel.objects.filter(tenant=tenant2).count() == 1
```

### 6. Logging

**Enable debug logging during development**:

```python
# settings.py
LOGGING = {
    'version': 1,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'tenancy': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Shows detailed cloning information
        },
    },
}
```

### 7. Production Deployment

**Security checklist**:
- [ ] Use HTTPS for all tenant domains
- [ ] Configure proper DNS for tenant domains
- [ ] Set `DEBUG = False`
- [ ] Use strong passwords for tenant admin users
- [ ] Regularly backup database (includes all tenants)
- [ ] Monitor for unusual cross-tenant access attempts
- [ ] Keep superuser count minimal

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

---

## License

[Your License Here]

---

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/ArtoLabs/tenancy/issues
- Documentation: https://github.com/ArtoLabs/tenancy

---

## Changelog

### Version 1.0.0
- Initial release
- Multi-tenant data isolation
- Dual admin interfaces
- Three cloning modes
- Automatic tenant provisioning
- Foreign key resolution
- Topological sorting for dependencies