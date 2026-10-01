import os
from urllib.parse import urlsplit

import qrcode
from qrcode.image.svg import SvgPathImage
from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import RedirectResponse

from app.services.template_service import TemplateService
from app.core.table_context import MAX_TABLES


class TableRouter:
    """Printable QR codes pointing to the customer-facing frontend."""

    def __init__(self, template_service: TemplateService):
        self.template_service = template_service
        self.router = APIRouter(prefix="/admin")
        self.router.add_api_route("/tables", self.show_tables, methods=["GET"])

    async def show_tables(
        self, request: Request, base_url: str | None = None,
        admin_token: str | None = Cookie(None),
        table_count: int = Query(5, ge=1, le=MAX_TABLES),
    ):
        if admin_token != "logged_in":
            return RedirectResponse("/admin/login", status_code=303)

        base_url = (
            base_url if base_url is not None
            else os.environ.get("PUBLIC_BASE_URL", str(request.base_url))
        ).strip().rstrip("/")
        error = None
        hostname = None
        try:
            parsed = urlsplit(base_url)
            hostname = parsed.hostname
            if (
                parsed.scheme not in ("http", "https") or not hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or len(base_url) > 500
                or any(char.isspace() or ord(char) < 32 for char in base_url)
            ):
                raise ValueError("Invalid frontend URL")
            _ = parsed.port
        except ValueError:
            error = "กรุณาใส่ URL เว็บเมนูที่เป็น http:// หรือ https:// โดยไม่มี query หรือ #"

        tables = []
        if error is None:
            for number in range(1, table_count + 1):
                url = f"{base_url}/?table={number}"
                qr = qrcode.make(url, image_factory=SvgPathImage, border=4)
                tables.append({
                    "number": number, "url": url,
                    "svg": qr.to_string(encoding="unicode"),
                })

        return self.template_service.render(request, "tables.html", {
            "title": "QR Code ประจำโต๊ะ", "base_url": base_url,
            "tables": tables, "error": error,
            "table_count": table_count, "max_tables": MAX_TABLES,
            "local_url": hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"),
        })
