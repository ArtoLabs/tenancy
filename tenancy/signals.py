# signals.py
from django.dispatch import Signal

# Fired after a tenant has been provisioned AND template objects have been cloned,
# after the DB transaction commits.
#
# Kwargs sent:
# - tenant: Tenant instance
# - domain: tenant.domain (convenience)
# - admin_user: the provisioned tenant admin user
# - clone_summary: dict[str, int] (model label -> number of objects cloned)
# - total_cloned: int
tenant_provisioned = Signal()
