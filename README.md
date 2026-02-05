# DJANGO ROW-BASED MULTI-TENANCY PACKAGE

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
- [Configuration](#CONFIGURATION)
- [Core Concepts](#core-concepts)
- [Role-Based Permissions](#role-based-permissions)
- [Cloning System](#cloning-system)
- [Querysets in Forms](#querysets-in-forms)
- [Admin Interfaces](#admin-interfaces)
- [Advanced Usage](#advanced-usage)
- [Tenant Provisioning Signal](#tenant-provisioning-signal)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

# INSTALLATION

Install directly from GitHub:

```bash
pip install git+https://github.com/ArtoLabs/tenancy.git
```

---

# QUICK START

### 1. Add to Installed Apps

This step enables the tenancy package inside your Django project. Adding the app registers its models, admin sites, system checks, cloning utilities, and role system with Django. Without this, none of the tenant resolution, tenant-aware models, or admin separation logic will be available, and Django will treat your project as a single-tenant application.

By installing the app early, Django can also run tenancy’s built-in system checks at startup, which warn you about unsafe unique constraints and other configuration issues before they cause runtime failures.

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

The tenant middleware is responsible for resolving which tenant a request belongs to, based on the incoming hostname. It attaches the resolved tenant to the request, activates the tenant context for the current thread, and enforces cross-tenant access rules.

It must run after Django’s authentication middleware so that it can safely evaluate the authenticated user against the resolved tenant. This middleware is the backbone of tenant isolation; without it, tenant-aware models and authentication guards cannot function correctly.

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

### 3. Add Authentication Backend

This authentication backend adds a tenant-aware guard to Django’s normal authentication pipeline. It ensures that a user can only authenticate on tenant domains they are allowed to access, even if their username and password are otherwise valid.

This protects common entry points such as login views, Django admin login, and any code path that calls authenticate(). Without this backend, a user could successfully log in on the wrong tenant domain and only be rejected later, which is both confusing and unsafe.
```python
# settings.py
AUTHENTICATION_BACKENDS = [
    'tenancy.backends.TenantGuardModelBackend',  # Recommended: tenant-safe authentication
    # The rest of your backends
]
```

### 4. Create Custom User Model

A custom user model is required so users can be explicitly associated with tenants. The tenant user mixin adds a tenant relationship to your user model while remaining compatible with Django’s authentication system.

This association allows the tenancy package to reason about which tenant a user belongs to, enforce login rules, and apply correct scoping in the admin interfaces. Defining this early is critical, as Django does not allow changing the user model after initial migrations.

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

Any model that should be isolated per tenant must inherit from the tenant mixin. This automatically adds a tenant field, enables tenant-scoped querying, and integrates the model into the tenant cloning system used when provisioning new tenants.

Tenant-aware models are automatically filtered by the active tenant context, which prevents accidental cross-tenant data access in normal queries. They also participate in template cloning, allowing new tenants to start with predefined data.

#### NOTE:

This tenancy package supports multiple cloning modes. One of them, **skeleton mode**, creates a minimal "blank" version of each row for a new tenant rather than copying real data from an existing tenant. For skeleton cloning to work correctly and safely, your models must be designed with defaults in mind. Please see the cloning section below for more information.

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

The tenancy package provides two separate admin sites: one for system-level tenant administration and one for tenant-scoped management. Mapping them to different URLs keeps responsibilities clearly separated and prevents privilege confusion.

The system admin site is used by tenant admins to create and manage tenants. The tenant admin site is used by tenant managers to manage content within their own tenant only. This separation is fundamental to the security model.

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

Models must be registered separately with each admin site to control who can see and manage them. Tenant admin registrations are automatically scoped to the current tenant, while super admin registrations allow cross-tenant visibility.

Using the provided admin mixins ensures that permissions, query filtering, and tenant assignment are handled consistently and safely. 

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

Finally, apply database migrations to create the tenant model, role tables, tenant fields, and supporting indexes. This step materializes the tenancy system in the database and enables tenant provisioning and isolation at runtime.

Always run migrations after configuring the user model and tenant mixins, as these affect the database schema in fundamental ways.

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

# CONFIGURATION

[Return to the Table of Contents](#table-of-contents)

---

## Settings

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

## Development Setup with Multiple Domains

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

# CORE CONCEPTS

[Return to the Table of Contents](#table-of-contents)

---

## 1. Understanding the Tenant Context

This package enforces tenancy by maintaining a current tenant context. All tenant-aware models scope their queries relative to that context. If no tenant context is active, tenant-aware queries intentionally return no rows.

This behavior is the foundation of tenant safety.

### How the Tenant Context Is Set

During a normal HTTP request, the tenant context is automatically established by middleware.

The middleware resolves the tenant from the request's host name (for example, `tenant1.example.com`), activates that tenant for the duration of the request, and attaches it to the request object. While the request is being processed:

- All tenant-aware models automatically filter to that tenant
- No manual `tenant=...` filtering is required
- Related objects remain safely scoped

When the request finishes, the tenant context is cleared.

As long as a request is handled under a valid tenant domain and passes through the middleware, tenant scoping is always active.

### When No Tenant Context Exists

A tenant context does not exist in the following situations:

- Requests where tenant resolution is intentionally skipped (for example, bootstrap or global admin paths)
- Requests to hostnames that do not match an active tenant
- Any code running outside the request/response lifecycle, including:
  - Django shell
  - Management commands
  - Background tasks
  - Startup code
  - Standalone scripts

In these cases, tenant-aware queries return empty querysets by design. This prevents accidental cross-tenant access when the system cannot safely determine intent.

If you ever see an unexpectedly empty queryset, the first thing to check is whether a tenant context is active.

### Working With a Tenant Outside Requests

When running code outside middleware and you want to operate on a specific tenant, you must be explicit. There are two supported patterns.

**Activate a tenant context** when you want normal tenant scoping to apply:
```python
from tenancy.context import activate_tenant, deactivate_tenant
from tenancy.models import Tenant
from myapp.models import Article

tenant = Tenant.objects.get(domain="tenant1.example.com")

activate_tenant(tenant)
try:
    articles = Article.objects.all()
finally:
    deactivate_tenant()
```

This is the preferred approach for per-tenant scripts, background jobs, and maintenance tasks.

**Bypass tenant scoping explicitly** when you need cross-tenant access:
```python
Article.objects.all_tenants()
```

You can then filter by tenant manually if needed:
```python
Article.objects.all_tenants().filter(tenant=tenant)
```

### Why This Design Exists

Row-based multi-tenancy fails most often through silent data leaks, not crashes. This system defaults to returning no data unless tenant intent is explicit. Safe behavior is automatic; unsafe behavior requires conscious action.

Once you understand that "no tenant context means no data," the rest of the system becomes predictable and reliable.

## 2. Making a Model Tenant-Aware

A model becomes tenant-aware by inheriting from the provided tenant mixin. This is the single switch that tells the system, "rows of this model belong to a tenant and must be isolated."

If a model should have separate data per tenant, it must use the mixin. If it should be shared globally across all tenants, it must not.

### Basic Tenant-Aware Model
```python
from django.db import models
from tenancy.mixins import TenantMixin

class Article(TenantMixin, models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()

    def __str__(self):
        return self.title
```

This does several important things automatically:

- Adds a tenant foreign key to the model
- Registers the model as tenant-scoped
- Attaches a tenant-aware manager by default
- Ensures all ORM queries are filtered to the active tenant context

Once this is in place, standard queries behave as expected:
```python
Article.objects.all()
```

Returns only rows belonging to the current tenant.

You should never manually add `tenant=...` filters in normal application code. If you feel the need to do that, something is likely misconfigured.

### Models That Should NOT Be Tenant-Aware

Not every model should be tenant-scoped.

Examples of models that should usually remain global:

- The Tenant model itself
- System configuration tables
- Feature flags shared across tenants
- Reference or lookup tables intended to be global

These models should not inherit from `TenantMixin` and will behave like normal Django models.

### Ordering and Inheritance Rules

When using multiple mixins, `TenantMixin` should appear before `models.Model` and generally before other behavioral mixins:
```python
class Article(TenantMixin, TimestampMixin, models.Model):
    ...
```

This ensures the tenant field and manager are applied correctly.

### Required Fields and Defaults

Tenant-aware models participate in cloning when new tenants are created. Because of this:

- Required fields must have safe defaults, be nullable, or be explicitly handled during cloning
- Unsafe required fields will cause tenant provisioning to fail loudly rather than create invalid rows

This is intentional. Cloning errors should surface early.

### Quick Sanity Check

A model is correctly tenant-aware if all of the following are true:

- It inherits from `TenantMixin`
- It does not manually define a tenant field
- It does not override `objects` with a non-tenant manager
- Queries return data during a tenant request and return no data without a tenant context

If those conditions are met, the model is correctly isolated.

## 3. Using the Tenant Manager

Tenant isolation in this package is enforced entirely through a custom manager and queryset. For tenant-aware models, the manager is not an implementation detail. It is part of the tenancy contract.

If a tenant-aware model uses a manager that does not inherit from the tenant manager, tenant scoping will be broken.

This applies even if the model correctly inherits from TenantMixin.

### The Default Manager

When you use TenantMixin without defining a custom manager, the model automatically receives a tenant-aware manager. In the simplest case, you do not need to do anything.
```python
class Article(TenantMixin, models.Model):
    title = models.CharField(max_length=200)
```

This is already safe.

### Adding a Custom Manager

The moment you define a custom manager, you must inherit from TenantManager.
```python
from tenancy.managers import TenantManager

class ArticleManager(TenantManager):
    def published(self):
        return self.get_queryset().filter(is_published=True)

class Article(TenantMixin, models.Model):
    title = models.CharField(max_length=200)
    is_published = models.BooleanField(default=False)

    objects = ArticleManager()
```

This preserves tenant scoping while allowing custom query helpers.

The key rule is simple: always build on top of TenantManager.

### Overriding get_queryset()

If you override get_queryset(), you must start from super().
```python
class ArticleManager(TenantManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)
```

Failing to call super() will bypass tenant filtering and cause empty or cross-tenant results depending on context.

### What Not to Do

Do not attach a plain Django manager to a tenant-aware model.
```python
class ArticleManager(models.Manager):
    ...
```

This will silently disable tenant scoping and cause subtle bugs, especially in:

- Cloning
- Background tasks
- Signals
- Admin views

If you see empty querysets or unexpected data, always check the manager first.

### Cross-Tenant Queries

The tenant manager provides an explicit escape hatch for administrative operations:
```python
Article.objects.all_tenants()
```

This bypasses tenant filtering and returns all rows across all tenants. Use it sparingly and intentionally.

### Quick Checklist

Before moving on, ensure:

- Every tenant-aware model uses TenantManager (directly or indirectly)
- Custom managers call super().get_queryset()
- Custom querysets inherit from TenantQuerySet
- Plain Django managers are never used on tenant models

If these rules are followed, tenant scoping remains consistent everywhere in your application.

## 4. Using Custom Tenant-Aware QuerySets

Custom querysets are used when you want reusable, chainable query logic on tenant-aware models. In a multi-tenant system like this one, querysets are not just a convenience layer. They are part of the tenant isolation mechanism.

Because tenant scoping is enforced at the ORM level, any queryset used by a tenant-aware model must explicitly apply the tenant filter. This package provides a tenant-aware base queryset to support that.

### The TenantQuerySet Base Class

This package defines a `TenantQuerySet` class that applies tenant filtering internally. It is responsible for:

- Applying the tenant filter when a tenant context is active
- Returning empty querysets when no tenant context exists
- Supporting an explicit escape hatch for cross-tenant access

If you want custom queryset methods on a tenant-aware model, you must inherit from `TenantQuerySet`.
```python
from tenancy.managers import TenantQuerySet

class ArticleQuerySet(TenantQuerySet):
    def published(self):
        return self.filter(is_published=True)

    def featured(self):
        return self.filter(is_featured=True)
```

This ensures that all query logic is layered on top of tenant-safe behavior.

### Attaching a Custom QuerySet (Important)

Unlike some common Django patterns, you cannot rely on `Manager.from_queryset()` alone in this package.

`TenantManager` constructs its queryset explicitly and applies tenant filtering itself. Because of that, attaching a custom queryset requires overriding `get_queryset()` and instantiating your custom queryset directly.

The correct pattern is:
```python
from tenancy.managers import TenantManager
from .querysets import ArticleQuerySet

class ArticleManager(TenantManager):
    def get_queryset(self):
        qs = ArticleQuerySet(self.model, using=self._db)
        if hasattr(self.model, "_is_tenant_model") and self.model._is_tenant_model():
            return qs._apply_tenant_filter()
        return qs

from django.db import models
from tenancy.mixins import TenantMixin

class Article(TenantMixin, models.Model):
    title = models.CharField(max_length=200)
    is_published = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)

    objects = ArticleManager()
```

With this setup, all of the following are tenant-safe and composable:
```python
Article.objects.published()
Article.objects.featured().published()
```

### Why This Is Necessary

In this package, tenant filtering is not a database feature and not a global Django setting. It is applied by:

- The tenant-aware manager
- The tenant-aware queryset

If either of those layers is bypassed, tenant isolation is no longer guaranteed.

This is why using a plain Django `QuerySet` or a manager that does not explicitly apply `_apply_tenant_filter()` is unsafe for tenant-aware models.

### What Not to Do

**Do not use `models.QuerySet` for tenant-aware models.**
```python
class ArticleQuerySet(models.QuerySet):
    ...
```

Even if this appears to work in simple cases, it bypasses the tenant filtering logic and will eventually lead to incorrect or cross-tenant results.

**Do not assume that `from_queryset()` will automatically wire in tenant behavior.** In this package, tenant scoping must be applied explicitly in `get_queryset()`.

### When to Use QuerySet Methods vs Manager Methods

As a general guideline:

- Use queryset methods for reusable, chainable filtering logic
- Use manager methods for entry points, shortcuts, or behavior that does not need to be chainable

In practice, most tenant-safe query logic belongs on the queryset and is surfaced through a tenant-aware manager.

## 5. Querying Outside the Request Context

Tenant scoping is automatically applied during HTTP requests because the tenant context is set by middleware. Outside of a request context, however, no tenant is active by default.

This is a deliberate design choice. When the system cannot safely infer tenant intent, it returns no data rather than risk cross-tenant access.

Understanding how to work in these situations is essential for scripts, background jobs, signals, and tenant provisioning.

### What "Outside the Request Context" Means

The following environments do not have an active tenant context unless you explicitly set one:

- Django shell
- Management commands
- Background workers (Celery, RQ, etc.)
- Startup code
- Standalone scripts
- Signals triggered by non-request code

In these situations, tenant-aware queries such as:
```python
Article.objects.all()
```

Will return an empty queryset.

This is expected behavior.

### Pattern 1: Activating a Tenant Context

When you want code to behave as if it is running inside a tenant request, explicitly activate a tenant context.
```python
from tenancy.context import activate_tenant, deactivate_tenant
from tenancy.models import Tenant
from myapp.models import Article

tenant = Tenant.objects.get(domain="tenant1.example.com")

activate_tenant(tenant)
try:
    articles = Article.objects.filter(is_published=True)
finally:
    deactivate_tenant()
```

This is the preferred approach for:

- Per-tenant background jobs
- Maintenance scripts
- Data migrations scoped to a single tenant
- Tenant-specific signals or hooks

Always ensure the tenant context is cleared using a try/finally block. Tenant context is thread-local and must not leak into unrelated work.

### Pattern 2: Explicit Cross-Tenant Queries

For administrative or provisioning tasks that intentionally operate across tenants, use the explicit escape hatch.
```python
Article.objects.all_tenants()
```

This bypasses tenant filtering entirely and returns rows from all tenants.

You can then filter explicitly:
```python
Article.objects.all_tenants().filter(tenant=tenant)
```

This pattern is useful when iterating across tenants or performing system-wide checks.

### Choosing the Right Pattern

As a rule of thumb:

- If your code is conceptually "running as a tenant," activate the tenant context.
- If your code is conceptually "operating on the system," use `all_tenants()` and be explicit.

Do not rely on implicit behavior in non-request code. Always make tenant intent obvious.

### Common Pitfalls

- Forgetting to activate a tenant and assuming data is missing
- Using `all_tenants()` in application code where tenant scoping should apply
- Activating a tenant context and failing to deactivate it
- Running tenant-aware queries during bootstrap paths where middleware intentionally skips tenant resolution

If something behaves differently inside a view than it does in a script, tenant context is almost always the reason.

## 6. Tenant-Safe Uniqueness Constraints

In a row-based multi-tenant system, global uniqueness is almost always wrong.

A value that must be unique within a tenant must not be globally unique in the database. If you use `unique=True` incorrectly, tenant creation and cloning will eventually fail with integrity errors.

This section explains how to define uniqueness correctly for tenant-aware models.

### Why unique=True Is Dangerous in Multi-Tenancy

In a traditional single-tenant Django app, this is common and safe:
```python
slug = models.SlugField(unique=True)
```

In a multi-tenant app, this enforces uniqueness across all tenants, not per tenant.

That means:

- Two different tenants cannot have the same slug
- Cloning template data will fail on the second tenant
- Errors appear at runtime, not at migration time

This is almost never what you want.

### The Correct Pattern: Tenant-Scoped Uniqueness

For tenant-aware models, uniqueness must include the tenant field.

Instead of `unique=True`, define a composite uniqueness constraint using `UniqueConstraint`.
```python
from django.db import models
from tenancy.mixins import TenantMixin

class Article(TenantMixin, models.Model):
    slug = models.SlugField()
    title = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                name="unique_article_slug_per_tenant",
            )
        ]
```

This enforces:

- Each tenant can use the same slug values
- Slugs are unique within a tenant
- Cloning works correctly
- Database integrity is preserved

This is the only safe way to enforce per-tenant uniqueness.

### When Global Uniqueness Is Appropriate

Global uniqueness is appropriate only for models that are not tenant-aware, such as:

- The Tenant model itself
- Global configuration tables
- System-wide lookup or reference data

If a model inherits from `TenantMixin`, you should assume `unique=True` is incorrect unless you have a very specific reason.

### System Checks and Early Warnings

This package includes a Django system check that detects unsafe uniqueness patterns on tenant-aware models.

If you declare `unique=True` on a field of a tenant-aware model, the check will warn you during startup so the issue can be fixed before it causes runtime failures.

These warnings should be treated as errors during development.

### How This Affects Cloning and Provisioning

Tenant provisioning often involves cloning rows from a template tenant. If tenant-unsafe uniqueness constraints exist:

- The first tenant may provision successfully
- Subsequent tenants will fail with integrity errors
- Failures may occur deep into the cloning process

Correct tenant-scoped constraints prevent these failures entirely.

### Quick Checklist

Before moving on, ensure:

- Tenant-aware models do not use `unique=True` for tenant-specific values
- All per-tenant uniqueness is enforced with `UniqueConstraint`
- The tenant field is always included in the constraint
- System check warnings are resolved, not ignored

---

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

# ROLE-BASED PERMISSIONS

[Return to the Table of Contents](#table-of-contents)

---

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

# CLONING SYSTEM

[Return to the Table of Contents](#table-of-contents)

---

When you create a new tenant, you typically need more than a Tenant row. Most real applications require baseline rows such as navigation, settings, default pages, categories, roles, permissions, or other “starting state” data.

This package includes a cloning system that can automatically populate tenant-scoped models during provisioning so each tenant starts from a consistent baseline. Cloning is intentionally flexible because different apps bootstrap data in different ways:

Some apps want to copy a curated “template tenant” (a full starter dataset).

Some apps want only a minimal skeleton of required rows, with fields left blank or set to safe defaults so the consuming project can fill them in later.

Some apps want a mixture: copy some models from the template, skeletonize others, and exclude some entirely.

Cloning runs outside the normal request flow, so tenant context and manager correctness matter. If you use custom managers/querysets on tenant models, they must remain tenant-aware or cloning can fail or behave unexpectedly.

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

#### Model Defaults and Skeleton Cloning


When skeleton cloning runs, the system attempts to generate reasonable default values for many common Django field types automatically, such as strings, numbers, booleans, JSON, dates, and UUIDs. However, this automatic behavior is intentionally limited. If a field is required (`null=False`) and has no default that can be safely generated, the clone process will stop and raise an error explaining which field needs attention.

Because of this, it is **strongly recommended** that every field in any model that will be cloned defines an explicit default, or is marked as nullable where appropriate. Relying on implicit behavior can lead to clone failures, especially as your schema evolves.

#### Important Notes

* **Required fields without defaults are not allowed in skeleton cloning.** If no safe default can be generated, an error will be raised and the tenant will not be created.
* **Certain field types cannot have meaningful automatic defaults.** In particular, image and file fields cannot be safely defaulted. If a model includes image or file fields and is expected to support skeleton cloning, those fields must be declared with `null=True` and `blank=True`.
* **Foreign keys and other relational fields** may require explicit defaults or nullable settings, depending on your data model and cloning strategy.

#### Best Practice

Treat skeleton cloning as a contract: if a model is cloneable, it must be able to exist in a clean, minimal state. Defining your own defaults makes this explicit, predictable, and future-proof.

If skeleton cloning fails, the error message will always indicate the exact model and field that needs a default or adjustment.






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

# QUERYSETS IN FORMS

[Return to the Table of Contents](#table-of-contents)

---

When using tenant-scoped models in Django forms, special care is needed to avoid issues related to tenant context.

This tenancy app intentionally treats a missing tenant as "no data" for safety. If a tenant-scoped model is queried when no tenant has been set, the queryset is forced to `.none()`. This most commonly shows up when your project creates querysets during import time (module load), because at startup there is no active tenant yet. The app prints a warning to help you locate the exact line of code, but the right long-term fix is to structure your forms so tenant-scoped querysets are created at form initialization time, not at import time.

## Key Rule

**Never call `YourTenantModel.objects...` in a form field definition at the class level.**

Use an empty placeholder queryset in the field definition, then set the real tenant-scoped queryset inside `__init__`, where tenant context exists. This applies to:
- Plain `forms.Form` fields
- `forms.ModelForm` fields
- Any custom `ModelChoiceField` subclasses

## Regular Forms

### ❌ Avoid This Pattern

This runs at import time:
```python
class MyForm(forms.Form):
    person = forms.ModelChoiceField(queryset=Person.objects.all())
```

### ✅ Use This Pattern Instead

Use an empty placeholder and populate it at runtime:
```python
class MyForm(forms.Form):
    person = forms.ModelChoiceField(queryset=Person.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"].queryset = Person.objects.all()
```

### Filtering and Ordering

If you need filtering or ordering, apply it in `__init__` as well:
```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields["person"].queryset = Person.objects.filter(gender="F").order_by("first_name", "last_name")
```

## ModelForms

For `forms.ModelForm`, there is an extra gotcha: relationship fields (FK and M2M) are auto-generated by Django at class construction time. If you let Django auto-create those fields and their default querysets, it can trigger the warning during import.

### The Fix

Explicitly override relationship fields with a safe empty placeholder queryset, then set the tenant-scoped queryset in `__init__`:
```python
class PersonForm(forms.ModelForm):
    father = forms.ModelChoiceField(
        queryset=Person.objects.all_tenants().none(),
        required=False
    )
    mother = forms.ModelChoiceField(
        queryset=Person.objects.all_tenants().none(),
        required=False
    )
    spouses = forms.ModelMultipleChoiceField(
        queryset=Person.objects.all_tenants().none(),
        required=False
    )

    class Meta:
        model = Person
        fields = ["first_name", "last_name", "father", "mother", "spouses"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["father"].queryset = Person.objects.filter(gender="M").order_by("first_name", "last_name")
        self.fields["mother"].queryset = Person.objects.filter(gender="F").order_by("first_name", "last_name")
        self.fields["spouses"].queryset = Person.objects.all().order_by("first_name", "last_name")
```

### Why `all_tenants().none()`?

The placeholder uses `Model.objects.all_tenants().none()` for a specific reason: it avoids tenant evaluation during import while remaining empty so it cannot expose any cross-tenant data even if something were to render it before `__init__` runs. Then, at runtime, you replace it with the real tenant-scoped queryset using the normal tenant manager (`Model.objects...`).

## Passing Request Context

If you need access to request-specific context to decide what to show, pass the request (or any needed context) into the form from the view and still set the queryset inside `__init__`:

### In the View
```python
def get_form_kwargs(self):
    kwargs = super().get_form_kwargs()
    kwargs["request"] = self.request
    return kwargs
```

### In the Form
```python
def __init__(self, *args, request=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields["person"].queryset = Person.objects.all()
```

## Troubleshooting

If you see tenancy warnings during startup, treat them as a checklist:

1. Find the line shown under "Likely trigger"
2. Replace any class-level tenant-scoped querysets with an empty placeholder
3. Move all tenant-scoped queryset assignment into the form's `__init__`

---

# ADMIN INTERFACES

[Return to the Table of Contents](#table-of-contents)

---

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

# ADVANCED USAGE

[Return to the Table of Contents](#table-of-contents)

---

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

# TENANT PROVISIONING SIGNAL

[Return to the Table of Contents](#table-of-contents)

---

The package emits a `tenant_provisioned` signal after each tenant is fully created, allowing you to hook into the provisioning process for custom setup tasks.

### When It's Emitted

The signal fires once per tenant, immediately after:
- Tenant record is created
- Tenant admin user is created
- All template objects are cloned
- Database transaction commits successfully

### Signal Payload
```python
tenant_provisioned.send(
    sender=TenantProvisioner,
    tenant=tenant,           # The new Tenant instance
    domain=domain,           # Tenant's domain (convenience)
    admin_user=user,         # The created admin user
    clone_summary={...},     # Dict: {model_label: count}
    total_cloned=42          # Total objects cloned
)
```

### Registering a Receiver

**1. Create the receiver function:**
```python
# myapp/tenancy_receivers.py
from django.dispatch import receiver
from tenancy.signals import tenant_provisioned

@receiver(tenant_provisioned)
def on_tenant_provisioned(sender, tenant, domain, admin_user, clone_summary, **kwargs):
    """
    React to tenant provisioning.
    
    IMPORTANT: Use .all_tenants() to bypass automatic tenant scoping,
    since receivers run outside the normal request lifecycle.
    """
    from myapp.models import SiteSettings
    
    # Explicitly target the new tenant
    SiteSettings.objects.all_tenants().update_or_create(
        tenant=tenant,
        defaults={
            'primary_domain': domain,
            'setup_completed': True,
        }
    )
    
    # Example: Log provisioning details
    print(f"Provisioned {tenant.name}: {clone_summary}")
```

**2. Register in your app config:**
```python
# myapp/apps.py
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = 'myapp'
    
    def ready(self):
        import myapp.tenancy_receivers  # Import to register receivers
```

### Common Use Cases

- Update tenant-scoped configuration with the new domain
- Provision external resources (DNS, SSL certificates, third-party accounts)
- Send welcome emails or notifications
- Enqueue background jobs for data import
- Create audit log entries

### ⚠️ Critical: Tenant Scoping in Receivers

Signal receivers run outside the request lifecycle, so **there is no active tenant context**. Always use `.all_tenants()` to bypass automatic filtering:
```python
# ❌ WRONG - filters by current tenant (probably None)
SiteSettings.objects.update_or_create(...)

# ✅ CORRECT - explicitly targets the new tenant
SiteSettings.objects.all_tenants().update_or_create(
    tenant=tenant,
    defaults={...}
)
```
---

# TROUBLESHOOTING

[Return to the Table of Contents](#table-of-contents)

---

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

# BEST PRACTICES

[Return to the Table of Contents](#table-of-contents)

---

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

# CONTRIBUTING

[Return to the Table of Contents](#table-of-contents)

---

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

### Version 0.2.0
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

### Version 0.1.0
- Initial release
- Multi-tenant data isolation
- Dual admin interfaces
- Three cloning modes
- Automatic tenant provisioning
- Foreign key resolution
- Topological sorting for dependencies