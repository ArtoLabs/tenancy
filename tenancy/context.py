"""
Thread-local storage for the current tenant context
"""
import threading

_thread_locals = threading.local()


def set_current_tenant(tenant):
    _thread_locals.tenant = tenant


def get_current_tenant():
    return getattr(_thread_locals, 'tenant', None)


def clear_current_tenant():
    if hasattr(_thread_locals, 'tenant'):
        delattr(_thread_locals, 'tenant')


# ---------------------------
# Request-scoped flags
# ---------------------------

def set_in_request(value: bool):
    _thread_locals.in_request = bool(value)


def in_request_context() -> bool:
    return bool(getattr(_thread_locals, "in_request", False))


def set_tenant_required(value: bool):
    _thread_locals.tenant_required = bool(value)


def is_tenant_required() -> bool:
    # Default to True when unset
    return bool(getattr(_thread_locals, "tenant_required", True))


def clear_request_flags():
    for attr in ("in_request", "tenant_required"):
        if hasattr(_thread_locals, attr):
            delattr(_thread_locals, attr)
