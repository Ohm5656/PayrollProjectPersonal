"""Serialize GUI, watcher and writer transitions within the desktop process."""
from functools import wraps


def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        service = getattr(self, 'service', None) or self
        with service.operation_lock:
            return method(self, *args, **kwargs)
    return call
