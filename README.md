# File: README.md
# Django Row-Level Multi-Tenancy

A lightweight, reusable Django package providing row-level multi-tenancy for MySQL.

## Features

- **Tenant Model**: Core model for managing tenants
- **Automatic Domain Detection**: Middleware detects tenant from incoming request domain
- **Thread-Local Storage**: Current tenant stored in thread-local context
- **Tenant-Aware Models**: Mixin for automatic tenant isolation
- **Custom Manager & QuerySet**: Automatic filtering by current tenant
- **Simple Integration**: Install, configure, and go

## Installation

```bash
pip install git+https://github.com/ArtoLabs/tenancy.git
```

## Quick Start

### 1. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    # ... other apps
    'tenancy.apps.TenancyConfig',
]
```

### 2. Add Middleware

```python
# settings.py
MIDDLEWARE = [
    'tenancy.middleware.TenantMiddleware',
    # ... other middleware
]
```

### 3. Configure Allowed Hosts

```python
# settings.py
# For production
ALLOWED_HOSTS = ['.example.com']  # Allows all subdomains

# For local development (see Local Development Setup below)
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.localhost', 'tenant1.localhost', 'tenant2.localhost']
```

### 4. Run Migrations

```bash
python manage.py migrate tenancy
```

### 5. Create Your Tenant-Aware Models

```python
# myapp/models.py
from django.db import models
from tenancy import TenantMixin

class Product(TenantMixin):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return self.name
```

### 6. Create Tenants

```python
from tenancy.models import Tenant

# Create tenants
tenant1 = Tenant.objects.create(
    name='Acme Corp',
    domain='acme.example.com',  # Production domain
    schema_name='acme'
)

tenant2 = Tenant.objects.create(
    name='Widgets Inc',
    domain='widgets.example.com',  # Production domain
    schema_name='widgets'
)
```

## Local Development Setup

When running Django's development server (`python manage.py runserver`), you can't use real subdomains with `127.0.0.1` or `localhost` by default. Here are three approaches:

### Option 1: Using .localhost domains (Recommended - Easiest)

Modern browsers automatically resolve `*.localhost` to `127.0.0.1`. This is the simplest approach:

**1. Update your `/etc/hosts` file (optional but recommended):**

```bash
# On macOS/Linux, edit /etc/hosts:
sudo nano /etc/hosts

# Add these lines:
127.0.0.1 tenant1.localhost
127.0.0.1 tenant2.localhost
127.0.0.1 admin.localhost
```

**2. Configure Django settings:**

```python
# settings.py
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.localhost']
```

**3. Create development tenants:**

```python
# In Django shell: python manage.py shell
from tenancy.models import Tenant

tenant1 = Tenant.objects.create(
    name='Tenant 1',
    domain='tenant1.localhost',
    schema_name='tenant1'
)

tenant2 = Tenant.objects.create(
    name='Tenant 2', 
    domain='tenant2.localhost',
    schema_name='tenant2'
)
```

**4. Run the development server on port 8000:**

```bash
python manage.py runserver 8000
```

**5. Access your tenants:**

- Tenant 1: `http://tenant1.localhost:8000`
- Tenant 2: `http://tenant2.localhost:8000`
- Admin (no tenant): `http://localhost:8000/admin`

### Option 2: Using /etc/hosts with Custom Domains

**1. Edit `/etc/hosts`:**

```bash
# On macOS/Linux:
sudo nano /etc/hosts

# On Windows: 
# Edit C:\Windows\System32\drivers\etc\hosts as Administrator

# Add these lines:
127.0.0.1 tenant1.local
127.0.0.1 tenant2.local
127.0.0.1 admin.local
```

**2. Configure Django:**

```python
# settings.py
ALLOWED_HOSTS = ['tenant1.local', 'tenant2.local', 'admin.local', 'localhost']
```

**3. Create tenants:**

```python
Tenant.objects.create(
    name='Tenant 1',
    domain='tenant1.local',
    schema_name='tenant1'
)
```

**4. Access:**

- `http://tenant1.local:8000`
- `http://tenant2.local:8000`

### Option 3: Using Port-Based Routing (Not Recommended)

If you can't modify `/etc/hosts`, you can run multiple Django instances on different ports and use a reverse proxy, but this is more complex and not ideal for development.

## Testing Multi-Tenancy Locally

### Step-by-Step Testing Guide

**1. Set up the package in a test Django project:**

```bash
# Create a test project
django-admin startproject testproject
cd testproject

# Install the package in development mode
pip install -e /path/to/django-row-tenancy

# Create a test app
python manage.py startapp products
```

**2. Configure settings.py:**

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'tenancy',  # Add tenancy
    'products',  # Your test app
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'tenancy.middleware.TenantMiddleware',  # Add this
]

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.localhost']

# Database configuration (use MySQL in production)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',  # or MySQL
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

**3. Create a test model:**

```python
# products/models.py
from django.db import models
from tenancy import TenantMixin

class Product(TenantMixin):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

# products/admin.py
from django.contrib import admin
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'tenant']
    list_filter = ['tenant']
```

**4. Run migrations:**

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

**5. Create test tenants and data:**

```python
# python manage.py shell
from tenancy.models import Tenant
from products.models import Product
from tenancy.utils import tenant_context

# Create tenants
tenant1 = Tenant.objects.create(
    name='Acme Corp',
    domain='tenant1.localhost',
    schema_name='acme'
)

tenant2 = Tenant.objects.create(
    name='Widgets Inc',
    domain='tenant2.localhost',
    schema_name='widgets'
)

# Create products for tenant1
with tenant_context(tenant1):
    Product.objects.create(name='Acme Widget', price=99.99)
    Product.objects.create(name='Acme Gadget', price=149.99)

# Create products for tenant2
with tenant_context(tenant2):
    Product.objects.create(name='Super Widget', price=79.99)
    Product.objects.create(name='Mega Gadget', price=199.99)

# Verify isolation
with tenant_context(tenant1):
    print(f"Tenant 1 products: {Product.objects.count()}")  # Should be 2

with tenant_context(tenant2):
    print(f"Tenant 2 products: {Product.objects.count()}")  # Should be 2
```

**6. Create views to test (optional):**

```python
# products/views.py
from django.shortcuts import render
from .models import Product

def product_list(request):
    products = Product.objects.all()  # Automatically filtered by tenant
    return render(request, 'products/list.html', {
        'products': products,
        'tenant': request.tenant
    })

# products/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name='product_list'),
]

# testproject/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('products/', include('products.urls')),
]
```

**7. Test in browser:**

```bash
python manage.py runserver 8000
```

Visit:
- `http://tenant1.localhost:8000/products/` - See only Acme products
- `http://tenant2.localhost:8000/products/` - See only Widgets products
- `http://localhost:8000/admin/` - Django admin (see all tenants)

### Debugging Tips

**Check current tenant:**

```python
# In views
def my_view(request):
    print(f"Current tenant: {request.tenant}")
    print(f"Tenant name: {request.tenant.name if request.tenant else 'None'}")
```

**Verify tenant detection:**

```python
# Add temporary middleware for debugging
class DebugTenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        print(f"Host: {request.get_host()}")
        print(f"Tenant: {getattr(request, 'tenant', None)}")
        return self.get_response(request)
```

**Common issues:**

1. **"No tenant found"**: Make sure the domain in your Tenant model exactly matches the domain you're visiting
2. **ALLOWED_HOSTS error**: Add your domain to ALLOWED_HOSTS in settings.py
3. **Products from wrong tenant**: Check that middleware is properly configured and request.tenant is set

## Usage

### Automatic Tenant Filtering

All queries are automatically filtered by the current tenant:

```python
# This only returns products for the current tenant
products = Product.objects.all()
```

### Manual Tenant Context

```python
from tenancy.utils import tenant_context

with tenant_context(tenant1):
    # All queries here are scoped to tenant1
    products = Product.objects.all()
```

### Accessing All Tenants (Admin/System Operations)

```python
# Bypass tenant filtering (use with caution)
all_products = Product.objects.all_tenants()
```

### View Decorators

```python
from tenancy.utils import require_tenant

@require_tenant
def my_view(request):
    # Tenant is guaranteed to be set
    products = Product.objects.all()
    return render(request, 'products.html', {'products': products})
```

## API Reference

### Models

- **Tenant**: Core tenant model with fields: name, domain, schema_name, is_active

### Mixins

- **TenantMixin**: Add to your models for automatic tenant support

### Middleware

- **TenantMiddleware**: Detects tenant from request domain and sets context

### Context Functions

- **get_current_tenant()**: Get the current tenant
- **set_current_tenant(tenant)**: Set the current tenant
- **clear_current_tenant()**: Clear tenant context

### Manager Methods

- **objects.filter_by_tenant(tenant)**: Explicitly filter by tenant
- **objects.all_tenants()**: Get all records across tenants

## Configuration

No additional configuration required! The package works out of the box.

## Development

To use this package in development:

```bash
# Clone the repository
git clone https://github.com/yourusername/django-row-tenancy.git

# Install in development mode
pip install -e .
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.