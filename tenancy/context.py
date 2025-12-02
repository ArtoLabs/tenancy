"""
Thread-local storage for the current tenant context
"""
import threading

_thread_locals = threading.local()


def set_current_tenant(tenant):
    """
    Set the current tenant in thread-local storage.

    Args:
        tenant: Tenant instance or None
    """
    _thread_locals.tenant = tenant


def get_current_tenant():
    """
    Get the current tenant from thread-local storage.

    Returns:
        Tenant instance or None
    """
    return getattr(_thread_locals, 'tenant', None)


def clear_current_tenant():
    """
    Clear the current tenant from thread-local storage.
    """
    if hasattr(_thread_locals, 'tenant'):
        delattr(_thread_locals, 'tenant')