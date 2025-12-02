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
pip install django-row-tenancy
```

## Quick Start

### 1. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    # ... other apps
    'tenancy',
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

### 3. Run Migrations

```bash
python manage.py migrate tenancy
```

### 4. Create Your Tenant-Aware Models

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

### 5. Create Tenants

```python
from tenancy.models import Tenant

# Create tenants
tenant1 = Tenant.objects.create(
    name='Acme Corp',
    domain='acme.example.com',
    schema_name='acme'
)

tenant2 = Tenant.objects.create(
    name='Widgets Inc',
    domain='widgets.example.com',
    schema_name='widgets'
)
```

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