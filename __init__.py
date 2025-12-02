"""
Django Row-Level Multi-Tenancy Package
"""
default_app_config = 'tenancy.apps.TenancyConfig'

from .models import Tenant
from .mixins import TenantMixin
from .middleware import TenantMiddleware
from .context import get_current_tenant, set_current_tenant
from .admin import tenant_admin_site, super_admin_site, TenantAdminMixin

__version__ = '0.1.0'
__all__ = [
    'Tenant',
    'TenantMixin',
    'TenantMiddleware',
    'get_current_tenant',
    'set_current_tenant',
    'tenant_admin_site',
    'super_admin_site',
    'TenantAdminMixin',
]