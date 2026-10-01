from fastapi import Request
from fastapi.templating import Jinja2Templates
from urllib.parse import quote, urlsplit

from app.core.table_context import table_query


def menu_image_url(image: str | None) -> str:
    """Support both cloud URLs and filenames from local menu uploads."""
    fallback = "/static/images/menu-placeholder.svg"
    value = (image or "").strip()
    if not value:
        return fallback
    try:
        parsed = urlsplit(value)
    except ValueError:
        return fallback
    if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
        return value
    if parsed.scheme or parsed.netloc:
        return fallback
    value = value.replace("\\", "/")
    for prefix in ("/static/images/", "static/images/"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    if value.startswith("/") or ".." in value.split("/"):
        return fallback
    return "/static/images/" + quote(value, safe="/%")


class TemplateService:
    """ห่อหุ้มการ render HTML ไม่ให้ router ผูกติดกับ Jinja2 โดยตรง
    ถ้า starlette เปลี่ยน signature อีกในอนาคต แก้ที่คลาสนี้ที่เดียว
    """

    def __init__(self, directory: str):
        self.templates = Jinja2Templates(directory=directory)
        self.templates.env.filters["menu_image_url"] = menu_image_url

    def render(self, request: Request, name: str, context: dict | None = None):
        return self.templates.TemplateResponse(request, name, {
            **(context or {}),
            "table_id": getattr(request.state, "table_id", None),
            "table_query": table_query(request),
        })
