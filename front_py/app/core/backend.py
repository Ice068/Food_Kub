"""Select the configured API; demo mode never contacts Firebase or a payment bank."""
import httpx
from app.core.config import settings


def backend_client(**kwargs) -> httpx.AsyncClient:
    if settings.DEMO_MODE:
        from app.services.demo_service import demo_request
        kwargs["transport"] = httpx.MockTransport(demo_request)
    kwargs.setdefault("timeout", 8.0)
    return httpx.AsyncClient(**kwargs)
