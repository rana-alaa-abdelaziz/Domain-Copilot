import uuid
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="no-correlation-id")

def get_correlation_id() -> str:
    """
    Get the correlation ID for the current request context.
    Returns 'no-correlation-id' if outside a request context.
    """
    return _correlation_id.get()

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Read from header or generate a new UUID4
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
            
        # Store in context variable
        token = _correlation_id.set(correlation_id)
        
        try:
            response = await call_next(request)
            # Echo it back on the response
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            _correlation_id.reset(token)
