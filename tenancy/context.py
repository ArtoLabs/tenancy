"""
Thread-local storage for the current tenant context.
"""

import threading

_thread_locals = threading.local()


def set_current_tenant(tenant):
    """
    Set the current tenant for this thread.
    """
    _thread_locals.tenant = tenant


def get_current_tenant():
    """
    Get the current tenant for this thread.
    Returns None if no tenant has been set.
    """
    return getattr(_thread_locals, "tenant", None)


def clear_current_tenant():
    """
    Clear the current tenant from this thread.
    """
    if hasattr(_thread_locals, "tenant"):
        delattr(_thread_locals, "tenant")


def activate_tenant(tenant):
    """
    Make `tenant` the current tenant for this thread, e.g. in a management
    command or background job. Pair it with deactivate_tenant() in a finally block.
    """
    set_current_tenant(tenant)


def deactivate_tenant():
    """Clear the current tenant set by activate_tenant()."""
    clear_current_tenant()
