import os
from urllib.parse import urlencode, urlsplit

import httpx
import qrcode
from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import RedirectResponse
from qrcode.image.svg import SvgPathImage

from app.core.table_context import MAX_TABLES
from app.services.table_settings_service import TableSettingsService
from app.services.template_service import TemplateService


class TableRouter:
    """บันทึกจำนวนโต๊ะของร้านและสร้าง QR จากจำนวนที่บันทึกไว้"""

    def __init__(self, template_service: TemplateService):
        self.template_service = template_service
        self.table_settings = TableSettingsService()

        self.router = APIRouter(prefix="/admin")

        self.router.add_api_route(
            "/tables",
            self.show_tables,
            methods=["GET"],
        )

        self.router.add_api_route(
            "/tables",
            self.save_tables,
            methods=["POST"],
        )

    @staticmethod
    def _check_url(base_url):
        parsed = urlsplit(base_url)
        hostname = parsed.hostname

        if (
            parsed.scheme not in ("http", "https")
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or len(base_url) > 500
            or any(
                char.isspace() or ord(char) < 32
                for char in base_url
            )
        ):
            raise ValueError("Invalid frontend URL")

        # ตรวจสอบว่าเลขพอร์ตถูกต้องด้วย
        _ = parsed.port

        return hostname

    def _render(
        self,
        request,
        base_url,
        count,
        error=None,
        saved=False,
        status=200,
    ):
        tables = []
        hostname = None

        try:
            hostname = self._check_url(base_url)
        except ValueError:
            error = error or (
                "กรุณาใส่ URL เว็บเมนูที่เป็น http:// หรือ https:// "
                "โดยไม่มี query หรือ #"
            )

        if error is None:
            for number in range(1, count + 1):
                url = f"{base_url}/?table={number}"

                qr = qrcode.make(
                    url,
                    image_factory=SvgPathImage,
                    border=4,
                )

                tables.append({
                    "number": number,
                    "url": url,
                    "svg": qr.to_string(encoding="unicode"),
                })

        response = self.template_service.render(
            request,
            "tables.html",
            {
                "title": "QR Code ประจำโต๊ะ",
                "base_url": base_url,
                "tables": tables,
                "error": error,
                "saved": saved,
                "table_count": count,
                "max_tables": MAX_TABLES,
                "local_url": hostname in (
                    "localhost",
                    "127.0.0.1",
                    "0.0.0.0",
                    "::1",
                ),
            },
        )

        response.status_code = status
        response.headers["Cache-Control"] = "no-store"

        return response

    # ---------- อ่านจำนวนโต๊ะและแสดง QR ----------

    async def show_tables(
        self,
        request: Request,
        base_url: str | None = None,
        saved: bool = False,
        admin_token: str | None = Cookie(None),
    ):
        if admin_token != "logged_in":
            return RedirectResponse(
                "/admin/login",
                status_code=303,
            )

        base_url = (
            base_url
            if base_url is not None
            else os.environ.get(
                "PUBLIC_BASE_URL",
                str(request.base_url),
            )
        ).strip().rstrip("/")

        try:
            count = await self.table_settings.get_count()
        except httpx.HTTPError:
            return self._render(
                request,
                base_url,
                1,
                error=(
                    "โหลดจำนวนโต๊ะไม่ได้ "
                    "กรุณาตรวจสอบ Backend แล้วลองใหม่"
                ),
                status=503,
            )

        return self._render(
            request,
            base_url,
            count,
            saved=saved,
        )

    # ---------- บันทึกจำนวนโต๊ะ ----------

    async def save_tables(
        self,
        request: Request,
        base_url: str = Form(...),
        table_count: int = Form(
            ...,
            ge=1,
            le=MAX_TABLES,
        ),
        admin_token: str | None = Cookie(None),
    ):
        if admin_token != "logged_in":
            return RedirectResponse(
                "/admin/login",
                status_code=303,
            )

        base_url = base_url.strip().rstrip("/")

        # ตรวจ URL ก่อนบันทึกจำนวนโต๊ะ
        try:
            self._check_url(base_url)
        except ValueError:
            return self._render(
                request,
                base_url,
                table_count,
                status=400,
            )

        try:
            await self.table_settings.set_count(table_count)
        except httpx.HTTPError:
            return self._render(
                request,
                base_url,
                table_count,
                error="บันทึกจำนวนโต๊ะไม่สำเร็จ กรุณาลองใหม่",
                status=503,
            )

        # Redirect หลังบันทึกสำเร็จ ป้องกันส่งฟอร์มซ้ำตอนรีเฟรช
        query = urlencode({
            "base_url": base_url,
            "saved": "true",
        })

        return RedirectResponse(
            f"/admin/tables?{query}",
            status_code=303,
        )