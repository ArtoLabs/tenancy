# Django Multi-Tenancy Package

A comprehensive Django package for building multi-tenant applications with complete data isolation, role-based permissions, intelligent object cloning, and dual admin interfaces.

## Features

- 🏢 **Complete Tenant Isolation** - Every tenant's data is completely separate
- 🔐 **Role-Based Access Control** - Independent permission system with `tenantadmin` and `tenantmanager` roles
- 🛡️ **Dual Admin Interfaces** - Separate admin sites for system admins and tenant managers
- 🎨 **Intelligent Object Cloning** - Three cloning modes (full, skeleton, field overrides) with automatic foreign key resolution
- 🔄 **Automatic Tenant Provisioning** - Clone template objects when creating new tenants
- 🎯 **Domain-Based Routing** - Automatic tenant detection from hostname
- 🔒 **Tenant-Safe Authentication** - Prevents tenant managers from authenticating on the wrong tenant domain
- 🧩 **Plug-and-Play** - Minimal configuration required

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Core Concepts](#core-concepts)
- [Role-Based Permissions](#role-based-permissions)
- [Cloning System](#cloning-system)
- [Admin Interfaces](#admin-interfaces)
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

### 3. Add Authentication Backend (Recommended)

The tenancy package provides a tenant-aware authentication backend that prevents users from authenticating on the wrong tenant domain when using Django’s authenticate() pipeline (including username/password login and Django admin login).

```python
# settings.py
AUTHENTICATION_BACKENDS = [
    'tenancy.backends.TenantGuardModelBackend',  # Recommended: tenant-safe authentication
    # The rest of your backends
]
```

### 4. Create Custom User Model

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

### 5. Add Tenant-Aware Models

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

### 6. Configure URLs

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

### 7. Register Models in Admin

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

### 8. Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 9. Bootstrap Your First Tenant

Use the bootstrap command to create your first tenant and initial users:

```bash
python manage.py bootstrap_first_tenant
```

This interactive command will:
1. Create your first tenant (the "template tenant")
2. Create a tenant manager user for that tenant
3. Optionally create a system admin user with `tenantadmin` role

**Example session:**
```
Enter tenant name: Acme Corporation
Enter tenant domain (e.g. tenant1.localhost): acme.localhost
Enter tenant manager username: manager@acme.com
Enter tenant manager email: manager@acme.com
Enter tenant manager password: ••••••••
Create a system admin now? (y/n): y
Enter system admin username: admin
Enter system admin email: admin@example.com
Enter system admin password: ••••••••

✓ Created tenant "Acme Corporation" with domain "acme.localhost"
✓ Created tenant manager user "manager@acme.com"
✓ Assigned tenantmanager role for tenant "Acme Corporation"
✓ Created system admin user "admin"
✓ Assigned tenantadmin role (system-wide access)
```

**What gets created:**
- **Tenant**: Your first tenant with the specified domain
- **Tenant Manager**: User with `tenantmanager` role for this tenant (can access `/manage`)
- **System Admin** (optional): User with `tenantadmin` role (can access `/admin` and all `/manage` sites)

**Next steps:**
1. Add `127.0.0.1 acme.localhost` to `/etc/hosts`
2. Start server: `python manage.py runserver`
3. System admin login: `http://localhost:8000/admin/`
4. Tenant manager login: `http://acme.localhost:8000/manage/`

---

## Configuration

### Settings

```python
# settings.py

# Required: Custom user model with TenantUserMixin
AUTH_USER_MODEL = 'myapp.User'

# Recommended: tenant-safe authentication (prevents cross-tenant authentication)
AUTHENTICATION_BACKENDS = [
    'tenancy.backends.TenantGuardModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Optional: Bootstrap mode (allows /admin access without tenant resolution)
TENANCY_BOOTSTRAP = False  # Set to True only during initial setup

# Recommended: Enforce tenant membership for authenticated users (middleware-level safety net)
TENANCY_ENFORCE_MEMBERSHIP = True

# Optional: Skip membership enforcement for certain paths (useful for custom auth endpoints)
TENANCY_MEMBERSHIP_EXEMPT_PATHS = [
    '/accounts/',  # typical magic-link/OTP endpoints
    '/auth/',
    '/login/',
    '/logout/',
    '/static/',
    '/media/',
    '/favicon.ico',
    '/health/',
]

# Optional: If request.tenant is missing during auth, deny by default
TENANCY_DENY_AUTH_WITHOUT_TENANT = True

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
- Allows users without a tenant assignment
- Enables tenant-based user filtering

### The Template Tenant

The **first tenant** created serves as the **template tenant**:
- Contains "template objects" that define the default configuration
- When a new tenant is created, template objects are cloned
- Only users with `tenantadmin` role can modify template objects

**Best Practice**: Create your first tenant with domain `template.localhost` and use it exclusively for defining default configurations.

---

## Role-Based Permissions

The tenancy package uses a **self-contained role system** that is completely independent of Django's `is_superuser` and `is_staff` flags.

### The Two Roles

#### Tenant Admin (`tenantadmin`)

**Purpose**: System-wide administration

**Access**:
- ✅ Can access `/admin/` (super admin site)
- ✅ Can access ALL `/manage/` sites for ALL tenants (god mode)
- ✅ Can create new tenants
- ✅ Can view and manage all tenant data
- ✅ Can assign roles to users

**Use case**: The system owner or IT administrator who oversees the entire multi-tenant system. Typically only 1-2 people have this role.

#### Tenant Manager (`tenantmanager`)

**Purpose**: Tenant-specific administration

**Access**:
- ❌ Cannot access `/admin/` (403 Forbidden)
- ✅ Can access `/manage/` for their assigned tenant only
- ❌ Cannot access other tenants' `/manage/` sites (404 Not Found)
- ❌ Cannot create new tenants
- ✅ Can manage users and data within their tenant
- ❌ Cannot see Tenant or TenancyRole models

**Use case**: The manager or admin of a specific tenant organization. Each tenant has one or more tenant managers.

### The TenancyRole Model

Roles are stored in the `TenancyRole` model with these fields:
- **user**: The user being granted the role
- **role**: Either `'tenantadmin'` or `'tenantmanager'`
- **tenant**: The specific tenant (required for `tenantmanager`, must be `None` for `tenantadmin`)
- **assigned_at**: When the role was granted
- **assigned_by**: Who granted the role (audit trail)

### Managing Roles

#### Via Python Shell

```python
from django.contrib.auth import get_user_model
from tenancy.models import Tenant
from tenancy.roles import roles, TenancyRole

User = get_user_model()

# Assign tenant admin role (system-wide access)
admin_user = User.objects.get(username='admin')
roles.assign_role(
    user=admin_user,
    role=TenancyRole.TENANT_ADMIN,
    tenant=None,  # System-wide, not tied to specific tenant
    assigned_by=None  # Or pass the user who is assigning
)

# Assign tenant manager role (tenant-specific access)
manager_user = User.objects.get(username='manager')
tenant = Tenant.objects.get(domain='acme.localhost')
roles.assign_role(
    user=manager_user,
    role=TenancyRole.TENANT_MANAGER,
    tenant=tenant,  # Specific tenant only
    assigned_by=admin_user
)

# Check roles
is_admin = roles.is_tenant_admin(admin_user)  # True
is_manager = roles.is_tenant_manager(manager_user, tenant)  # True

# Get all tenants a user can manage
managed_tenants = roles.get_managed_tenants(manager_user)

# Revoke a role
roles.revoke_role(manager_user, TenancyRole.TENANT_MANAGER, tenant)
```

#### Via Admin Interface

System admins can manage roles via the super admin interface:

1. Login to `/admin/` as a tenant admin
2. Go to "Tenancy Roles"
3. Click "Add Tenancy Role"
4. Select:
   - **User**: The user to grant the role to
   - **Role**: Either `tenantadmin` or `tenantmanager`
   - **Tenant**: Leave blank for `tenantadmin`, select tenant for `tenantmanager`

#### During Tenant Creation

When creating a tenant via the super admin interface, the initial admin user is automatically assigned the `tenantmanager` role for that tenant.

### Debugging Permissions

Use the diagnostic command to check a user's permissions:

```bash
python manage.py debug_tenancy_permissions <username>
```

**Example output:**
```
Tenancy Roles:
  ✓ Tenant Manager - Can manage tenant-specific content
    Tenant: Acme Corporation (acme.localhost)
    Assigned: 2025-01-09 14:32:46

Tenant Admin Status:
  ✗ User is NOT a tenant admin

Tenant Manager Status:
  ✓ User is tenant manager for 1 tenant(s):
    - Acme Corporation (acme.localhost)

Access Check by Tenant:
  ✓ Acme Corporation (acme.localhost)
    Access: YES (as tenant manager)
  ✗ Demo Corp (demo.localhost)
    Access: NO
    Expected: 404 Not Found
```

### Migration from Django Auth

If you're upgrading from a version that used Django's `is_superuser` and `is_staff`, use the migration command:

```bash
# First, do a dry run to see what will happen
python manage.py migrate_tenancy_permissions --dry-run

# If everything looks good, run the actual migration
python manage.py migrate_tenancy_permissions
```

This will:
- Convert all `is_superuser=True` users → `tenantadmin` role
- Convert all `is_staff=True` users with a tenant → `tenantmanager` role for their tenant
- Flag any staff users without a tenant for manual review

**Note**: After migration, the `is_superuser` and `is_staff` flags are no longer used for tenancy permissions and can be used for other purposes in your application.

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

The package provides **two separate admin sites** with different purposes and access controls:

### Super Admin (`/admin`)

**Purpose**: System-wide management for tenant admins

**Access**: `http://yourdomain.com/admin`

**Who can access**: Only users with `tenantadmin` role

**Features**:
- Manage all tenants
- Create new tenants (with provisioning workflow)
- View/edit objects across ALL tenants
- Shows `tenant_display` column in list views
- Can create and delete objects
- Manage tenancy roles
- Manage all system users

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

**Purpose**: Tenant-specific management for tenant managers

**Access**: `http://tenant-domain.com/manage`

**Who can access**: 
- Users with `tenantmanager` role for the current tenant
- Users with `tenantadmin` role (god mode - can access all tenants)

**Features**:
- View/edit ONLY current tenant's objects
- Can create and manage objects within tenant
- Tenant field is hidden (auto-assigned)
- Foreign key dropdowns show only tenant's objects
- Cannot see Tenant or TenancyRole models

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
   - **Admin Username**: "manager@acme.com"
   - **Admin Email**: "manager@acme.com"
   - **Admin Password**: (secure password)
4. Click **"Create Tenant"**

**What happens automatically**:
- Tenant record is created
- Admin user is created and assigned the `tenantmanager` role for this tenant
- ALL template objects are discovered
- Objects are cloned in topological order (respecting dependencies)
- Each model's cloning mode is respected
- Foreign keys are resolved to newly cloned instances

**Result**: The new tenant is fully provisioned and the manager user can login at `http://acme.localhost:8000/manage`

---

## Advanced Usage

### Tenant-Safe Login for Custom Authentication Flows

If your authentication flow bypasses authenticate() and calls login(request, user) directly, use the tenancy helper:

```python
from tenancy.auth import tenancy_login

if not tenancy_login(request, user):
    return redirect("accounts:login")
```

### Request Convenience Helper (request.tenancy)

The middleware attaches a helper object to each request after tenant resolution.

Available helpers:

- request.tenant
- request.tenancy.can_authenticate_user(user) -> bool
- request.tenancy.can_authenticate_email(email) -> bool

Example usage:

```python
email = request.POST.get("email", "").strip()

if not request.tenancy.can_authenticate_email(email):
    return render(request, "accounts/check_your_email.html")
```

### Customizing Admin Site Classes

The tenancy package allows you to extend or replace the admin site classes to add custom authentication, logging, or other behavior.

#### Why Customize Admin Sites?

You might want to customize the admin sites to:
- **Add Multi-Factor Authentication (MFA)** - Require 2FA/TOTP before admin access
- **Implement Passwordless Authentication** - Use magic links or OAuth instead of passwords
- **Add Custom Login Flows** - Redirect to SSO, check IP allowlists, etc.
- **Enhance Audit Logging** - Track all admin actions with custom logging
- **Add Rate Limiting** - Prevent brute force attacks on admin interfaces
- **Customize Admin UI** - Change branding, add custom dashboard widgets

The package provides hooks to extend both admin sites (`/admin` and `/manage`) with your custom logic while preserving all tenant isolation and provisioning features.

#### How It Works

The tenancy package checks your Django settings for custom admin site classes:
- `TENANCY_TENANT_ADMIN_SITE_CLASS` - Custom class for tenant admin (`/manage`)
- `TENANCY_SUPER_ADMIN_SITE_CLASS` - Custom class for super admin (`/admin`)

If these settings are present, the package uses your custom classes. Otherwise, it uses the default `TenantAdminSite` and `SuperAdminSite`.

**Important**: Your custom classes are instantiated **before** any models are registered, so all registrations (including the `Tenant` model and auto-registered `User` model) happen on your custom instances.

#### Example: Adding Multi-Factor Authentication

This example shows how to add MFA (using `django-otp`) to both admin sites:

##### Step 1: Install Dependencies

```bash
pip install django-otp qrcode
```

##### Step 2: Create Custom Admin Site Classes

Create a separate file to avoid circular imports:

```python
# accounts/admin_sites.py
from django.shortcuts import redirect
from django_otp import devices_for_user
from tenancy.admin import TenantAdminSite, SuperAdminSite


class MFAMixin:
    """
    Mixin to add MFA enforcement to admin sites.
    
    CRITICAL: This mixin must call super().has_permission() to preserve
    the tenancy role checking from TenantAdminSite and SuperAdminSite.
    """
    
    def has_permission(self, request):
        """
        Enforce MFA in addition to tenancy role checks.
        
        Permission flow:
        1. Check tenancy roles (via super() - checks tenantadmin or tenantmanager)
        2. Verify user has at least one MFA device registered
        3. Check that MFA has been verified this session
        """
        user = request.user
        
        # CRITICAL: Check tenancy roles FIRST
        # This calls either SuperAdminSite.has_permission() or TenantAdminSite.has_permission()
        if not super().has_permission(request):
            return False
        
        # User has correct tenancy role, now check MFA requirements
        
        # Active check (redundant but safe to keep)
        if not getattr(user, "is_active", False):
            return False
        
        # Check registered MFA devices
        user_devices = list(devices_for_user(user))
        if not user_devices:
            return False
        
        # If session says MFA required, deny permission (forces verify step)
        if request.session.get("mfa_required", False):
            return False
        
        return True
    
    def login(self, request, extra_context=None):
        """
        Override login flow to enforce MFA.
        
        CRITICAL: This method handles authentication and MFA, then redirects.
        It does NOT check authorization - that's handled by has_permission().
        
        Login flow:
        1. If not authenticated → redirect to login
        2. If no MFA devices → redirect to setup
        3. If MFA not verified → redirect to verify
        4. If all good → redirect to original URL (authorization checked there)
        """
        # Get the original URL the user was trying to access
        next_url = request.GET.get('next', request.POST.get('next', None))
        
        # If not authenticated, redirect to your login view
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        
        # Authenticated but not active - deny access
        if not getattr(request.user, "is_active", False):
            return redirect("accounts:profile")
        
        # Check if user has MFA devices
        if not list(devices_for_user(request.user)):
            # Redirect to MFA setup
            if next_url:
                request.session['mfa_setup_next'] = next_url
            return redirect("accounts:mfa_setup")
        
        # Check if MFA verification is needed
        if request.session.get("mfa_required", False):
            # Redirect to MFA verification
            if next_url:
                request.session['mfa_verify_next'] = next_url
            return redirect("accounts:mfa_verify")
        
        # User is authenticated AND MFA is verified
        # Redirect to the original URL (or admin index if no next parameter)
        if next_url:
            return redirect(next_url)
        else:
            # No next parameter - redirect to this admin site's index
            return redirect(f'{self.name}:index')


class MFATenantAdminSite(MFAMixin, TenantAdminSite):
    """
    Tenant admin with MFA enforcement.
    
    Permission hierarchy:
    1. MFAMixin.has_permission() checks tenancy roles via super()
       └─> TenantAdminSite.has_permission() checks tenantmanager/tenantadmin role
    2. Then checks MFA requirements
    
    Login flow:
    1. MFAMixin.login() handles authentication and MFA
    2. Redirects back to original URL
    3. has_permission() checks authorization
    """
    pass


class MFASuperAdminSite(MFAMixin, SuperAdminSite):
    """
    Super admin with MFA enforcement.
    
    Permission hierarchy:
    1. MFAMixin.has_permission() checks tenancy roles via super()
       └─> SuperAdminSite.has_permission() checks tenantadmin role
    2. Then checks MFA requirements
    
    Login flow:
    1. MFAMixin.login() handles authentication and MFA
    2. Redirects back to original URL
    3. has_permission() checks authorization
    """
    pass
```

**Critical Points**:
1. **`has_permission()` must call `super()`** - This preserves tenancy role checking
2. **`login()` should redirect, not render** - Return `redirect(next_url)`, not `redirect(self.index(request))`
3. **Separate authentication from authorization** - `login()` handles auth/MFA, `has_permission()` handles tenancy roles

**Why a separate file?** This prevents circular imports. The tenancy package imports your classes during initialization, so they can't be in the same file that imports from the tenancy package.

##### Step 3: Configure Settings

```python
# settings.py

# Tell tenancy package to use your MFA-enabled admin site classes
TENANCY_TENANT_ADMIN_SITE_CLASS = 'accounts.admin_sites.MFATenantAdminSite'
TENANCY_SUPER_ADMIN_SITE_CLASS = 'accounts.admin_sites.MFASuperAdminSite'

# Configure django-otp
INSTALLED_APPS = [
    # ...
    'django_otp',
    'django_otp.plugins.otp_totp',
    # ...
]

MIDDLEWARE = [
    # ...
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',  # Add after AuthenticationMiddleware
    'tenancy.middleware.TenantMiddleware',
    # ...
]
```

##### Step 4: Create MFA Views

```python
# accounts/views.py
from django.shortcuts import render, redirect
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp import match_token

def mfa_setup(request):
    """View to setup MFA device (show QR code)."""
    if request.method == 'POST':
        # Create TOTP device
        device = TOTPDevice.objects.create(
            user=request.user,
            name='default',
            confirmed=True
        )
        # Get the next URL from session
        next_url = request.session.pop('mfa_setup_next', '/admin/')
        return redirect(next_url)
    
    return render(request, 'accounts/mfa_setup.html')

def mfa_verify(request):
    """View to verify MFA token."""
    if request.method == 'POST':
        token = request.POST.get('token')
        device = match_token(request.user, token)
        
        if device:
            # Mark MFA as verified for this session
            request.session['mfa_required'] = False
            # Redirect back to original URL
            next_url = request.session.pop('mfa_verify_next', '/admin/')
            return redirect(next_url)
        else:
            # Token invalid
            return render(request, 'accounts/mfa_verify.html', {
                'error': 'Invalid token'
            })
    
    return render(request, 'accounts/mfa_verify.html')
```

##### Step 5: Register Your Models

```python
# accounts/admin.py
from django.contrib import admin
from tenancy.admin import tenant_admin_site, super_admin_site
from tenancy.mixins import TenantAdminMixin, SuperUserAdminMixin
from .models import Profile

# Import the admin sites from tenancy - they're now MFA-enabled!
# No need to import your MFA classes here

@admin.register(Profile, site=super_admin_site)
class ProfileSuperAdmin(SuperUserAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'full_name')

@admin.register(Profile, site=tenant_admin_site)
class ProfileTenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('user', 'full_name')
```

##### Step 6: Use the Admin Sites

```python
# urls.py
from tenancy.admin import super_admin_site, tenant_admin_site

urlpatterns = [
    path('admin/', super_admin_site.urls),    # MFA-protected super admin
    path('manage/', tenant_admin_site.urls),  # MFA-protected tenant admin
    # ...
]
```

**Result**: Both admin sites now require:
1. ✅ Correct tenancy role (`tenantadmin` or `tenantmanager`)
2. ✅ MFA setup and verification
3. ✅ Complete isolation between tenants

#### Common Mistakes When Customizing

❌ **Not calling `super().has_permission()`**
```python
def has_permission(self, request):
    # WRONG - bypasses tenancy role checks!
    if not request.user.is_staff:
        return False
    # ... MFA checks ...
    return True
```

✅ **Correct - calls super() first**
```python
def has_permission(self, request):
    # Check tenancy roles first
    if not super().has_permission(request):
        return False
    # Then check MFA
    # ... MFA checks ...
    return True
```

❌ **Rendering instead of redirecting in login()**
```python
def login(self, request, extra_context=None):
    # WRONG - tries to render index directly!
    return redirect(self.index(request))
```

✅ **Correct - redirects to URL**
```python
def login(self, request, extra_context=None):
    # Redirect to URL (authorization checked there)
    next_url = request.GET.get('next', '/admin/')
    return redirect(next_url)
```

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
from tenancy.roles import roles, TenancyRole

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
    
    # The user is automatically assigned tenantmanager role
    # But you can assign additional roles:
    roles.assign_role(user, TenancyRole.TENANT_ADMIN, None)
    
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

### User Can't Access Admin

**Problem**: User sees "You don't have permission" when accessing admin.

**Solutions**:
1. **For `/admin` access**: User must have `tenantadmin` role
   ```python
   roles.assign_role(user, TenancyRole.TENANT_ADMIN, None)
   ```

2. **For `/manage` access**: User must have `tenantmanager` role for that tenant
   ```python
   tenant = Tenant.objects.get(domain='acme.localhost')
   roles.assign_role(user, TenancyRole.TENANT_MANAGER, tenant)
   ```

3. Verify user is active: `user.is_active = True`

4. Check roles with diagnostic command:
   ```bash
   python manage.py debug_tenancy_permissions username
   ```

### Tenant Manager Can Access Wrong Tenant

**Problem**: Manager of Tenant A can access Tenant B's `/manage`.

**Solutions**:
1. Check role assignments:
   ```bash
   python manage.py debug_tenancy_permissions username
   ```

2. Verify they don't have multiple `tenantmanager` roles:
   ```python
   from tenancy.roles import TenancyRole
   roles = TenancyRole.objects.filter(user=user, role='tenantmanager')
   print(roles)  # Should only show one tenant
   ```

3. Revoke incorrect roles:
   ```python
   from tenancy.roles import roles
   roles.revoke_role(user, TenancyRole.TENANT_MANAGER, wrong_tenant)
   ```

### Tenant Manager Can Access /admin/

**Problem**: Tenant manager can access super admin site.

**Solutions**:
1. Check if they have `tenantadmin` role:
   ```bash
   python manage.py debug_tenancy_permissions username
   ```

2. Revoke `tenantadmin` role if present:
   ```python
   roles.revoke_role(user, TenancyRole.TENANT_ADMIN, None)
   ```

3. If using custom admin site classes, verify `has_permission()` calls `super()`:
   ```python
   def has_permission(self, request):
       if not super().has_permission(request):  # Must call super!
           return False
       # Your custom checks...
   ```

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

---

## Best Practices

### 1. Role Management

**Principle of Least Privilege**:
- Assign `tenantadmin` role sparingly (typically 1-2 people)
- Most users should have `tenantmanager` role for specific tenants
- Don't grant `tenantadmin` unless user needs cross-tenant access

**Audit Trail**:
- Always pass `assigned_by` when assigning roles programmatically
- Regularly review role assignments via admin interface
- Use the diagnostic command to verify permissions

**Role Assignment Pattern**:
```python
# Good - specific and auditable
roles.assign_role(
    user=manager,
    role=TenancyRole.TENANT_MANAGER,
    tenant=tenant,
    assigned_by=request.user
)

# Bad - too permissive
roles.assign_role(user=manager, role=TenancyRole.TENANT_ADMIN, tenant=None)
```

### 2. Template Tenant Setup

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
- Only users with `tenantadmin` role should modify it

### 3. Model Design

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

### 4. Foreign Keys

**Make FKs nullable when using skeleton mode**:

```python
class SiteConfig(TenantMixin):
    theme = models.ForeignKey(Theme, null=True, blank=True)  # Good
    # theme = models.ForeignKey(Theme)  # Bad with skeleton mode
    
    CLONE_MODE = 'skeleton'
```

### 5. Admin Registration

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

### 6. Testing

**Test with multiple tenants and roles**:

```python
from tenancy.models import Tenant
from tenancy.roles import roles, TenancyRole
from django.contrib.auth import get_user_model

User = get_user_model()

def test_tenant_isolation():
    # Create tenants
    tenant1 = Tenant.objects.create(name='T1', domain='t1.test')
    tenant2 = Tenant.objects.create(name='T2', domain='t2.test')
    
    # Create users with roles
    admin = User.objects.create_user(username='admin', password='pass')
    roles.assign_role(admin, TenancyRole.TENANT_ADMIN, None)
    
    manager1 = User.objects.create_user(username='mgr1', password='pass')
    roles.assign_role(manager1, TenancyRole.TENANT_MANAGER, tenant1)
    
    # Test isolation
    tenant1.activate()
    obj1 = MyModel.objects.create(name='Object 1')
    
    tenant2.activate()
    obj2 = MyModel.objects.create(name='Object 2')
    
    # Verify isolation
    assert MyModel.objects.filter(tenant=tenant1).count() == 1
    assert MyModel.objects.filter(tenant=tenant2).count() == 1
    
    # Verify role permissions
    assert roles.is_tenant_admin(admin)
    assert not roles.is_tenant_admin(manager1)
    assert roles.is_tenant_manager(manager1, tenant1)
    assert not roles.is_tenant_manager(manager1, tenant2)
```

### 7. Logging

**Enable debug logging during development**:

```python
# settings.py
LOGGING = {
    'version': 1,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'tenancy': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Shows detailed role checks and cloning information
        },
    },
}
```

### 8. Production Deployment

**Security checklist**:
- [ ] Use HTTPS for all tenant domains
- [ ] Configure proper DNS for tenant domains
- [ ] Set `DEBUG = False`
- [ ] Set `TENANCY_BOOTSTRAP = False`
- [ ] Use strong passwords for tenant admin users
- [ ] Regularly backup database (includes all tenants and roles)
- [ ] Monitor for unusual cross-tenant access attempts
- [ ] Keep `tenantadmin` role count minimal (1-2 users)
- [ ] Review role assignments periodically

**Monitoring**:
```python
# Example: Alert on suspicious access patterns
from tenancy.roles import TenancyRole

# Count tenant admins (should be small)
admin_count = TenancyRole.objects.filter(role='tenantadmin').count()
if admin_count > 5:
    send_alert("Too many tenant admins!")

# Monitor role changes
from django.db.models.signals import post_save
from tenancy.roles import TenancyRole

@receiver(post_save, sender=TenancyRole)
def log_role_assignment(sender, instance, created, **kwargs):
    if created:
        logger.warning(f"New role assigned: {instance}")
```

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

### Version 2.0.0
- **Breaking**: Replaced Django's `is_superuser`/`is_staff` with dedicated tenancy roles
- Added `TenancyRole` model for role-based access control
- Added `tenantadmin` role (system-wide access)
- Added `tenantadmin` role (tenant-specific access)
- Added role management utilities (`roles` manager)
- Added `debug_tenancy_permissions` management command
- Added `migrate_tenancy_permissions` command for upgrading
- Added `bootstrap_first_tenant` command for initial setup
- Removed `is_superadmin` field from `TenantUserMixin`
- Updated admin site permission checks to use roles
- Fixed MFA integration example to properly call `super().has_permission()`
- Improved separation of authentication and authorization in admin flow

### Version 1.0.0
- Initial release
- Multi-tenant data isolation
- Dual admin interfaces
- Three cloning modes
- Automatic tenant provisioning
- Foreign key resolution
- Topological sorting for dependencies