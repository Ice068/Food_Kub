"""Authenticated menu management with bounded, local image uploads."""
import hmac
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from app.core.admin_auth import create_admin_token, valid_admin_token
from app.core.config import settings
from app.services.menu_service import MenuService
from app.services.template_service import TemplateService


class AdminRouter:
    IMAGE_DIR = Path(settings.STATIC_DIR) / "images"

    def __init__(self, menu_service: MenuService, template_service: TemplateService):
        self.router = APIRouter(prefix="/admin")
        self.menu_service = menu_service
        self.template_service = template_service
        for path, handler, methods in [
            ("/", self.show_admin_page, ["GET"]),
            ("/add", self.add_menu, ["POST"]),
            ("/edit/{item_id}", self.edit_menu, ["POST"]),
            ("/delete/{item_id}", self.delete_menu, ["POST"]),
            ("/login", self.show_login_page, ["GET"]),
            ("/login", self.process_login, ["POST"]),
            ("/logout", self.logout, ["GET"]),
        ]:
            self.router.add_api_route(path, handler, methods=methods)

    async def show_login_page(self, request: Request):
        return self.template_service.render(request, "login.html", {"title": "เข้าสู่ระบบ"})

    async def process_login(self, request: Request, username: str = Form(...), password: str = Form(...)):
        configured_user = os.environ.get("FOOD_KUB_ADMIN_USERNAME", "admin")
        configured_password = os.environ.get("FOOD_KUB_ADMIN_PASSWORD", "demo-food-kub" if settings.DEMO_MODE else "")
        if configured_password and hmac.compare_digest(username.encode(), configured_user.encode()) and hmac.compare_digest(password.encode(), configured_password.encode()):
            response = RedirectResponse("/admin/", status_code=303)
            response.set_cookie("admin_token", create_admin_token(), httponly=True,
                                secure=settings.COOKIE_SECURE, samesite="lax", max_age=43200)
            return response
        response = self.template_service.render(request, "login.html", {
            "title": "เข้าสู่ระบบ", "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง" if configured_password else "ยังไม่ได้ตั้งค่าบัญชีผู้ดูแล กรุณาตั้งค่า FOOD_KUB_ADMIN_PASSWORD บนเซิร์ฟเวอร์"})
        response.status_code = 401
        return response

    async def logout(self):
        response = RedirectResponse("/admin/login", status_code=303)
        response.delete_cookie("admin_token")
        return response

    async def show_admin_page(self, request: Request, admin_token: str | None = Cookie(None)):
        if not valid_admin_token(admin_token):
            return RedirectResponse("/admin/login", status_code=303)
        items = [item.to_dict() for item in await self.menu_service.get_all()]
        return self.template_service.render(request, "admin.html", {"title": "จัดการเมนู", "items": items})

    async def _image(self, image: UploadFile | None, existing: str = "menu-placeholder.svg") -> str:
        if not image or not image.filename:
            return existing
        content = await image.read(5 * 1024 * 1024 + 1)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(422, "รูปภาพต้องมีขนาดไม่เกิน 5 MB")
        from PIL import Image, UnidentifiedImageError
        from io import BytesIO
        try:
            with Image.open(BytesIO(content)) as picture:
                if picture.width * picture.height > 25000000:
                    raise ValueError("Image too large")
                picture.verify()
                image_format = picture.format
            extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}.get(image_format)
            if not extension:
                raise ValueError("Unsupported format")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(422, "กรุณาเลือกรูป JPEG, PNG, WebP หรือ GIF ที่ถูกต้อง") from exc
        self.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"menu-{uuid.uuid4().hex}{extension}"
        (self.IMAGE_DIR / filename).write_bytes(content)
        return filename

    async def add_menu(self, request: Request, name: str = Form(..., min_length=1, max_length=120),
                       price: float = Form(..., gt=0, le=100000, allow_inf_nan=False),
                       category: str = Form(..., min_length=1, max_length=60),
                       image: UploadFile | None = File(None), admin_token: str | None = Cookie(None)):
        if not valid_admin_token(admin_token):
            return RedirectResponse("/admin/login", status_code=303)
        if not name.strip() or not category.strip():
            raise HTTPException(422, "กรุณาระบุชื่อเมนูและหมวดหมู่")
        image_name = await self._image(image)
        await self.menu_service.add_item(name.strip(), round(price, 2), image_name, category.strip())
        return RedirectResponse("/admin/?saved=1", status_code=303)

    async def edit_menu(self, request: Request, item_id: int,
                        name: str = Form(..., min_length=1, max_length=120),
                        price: float = Form(..., gt=0, le=100000, allow_inf_nan=False),
                        category: str = Form(..., min_length=1, max_length=60),
                        image: UploadFile | None = File(None), admin_token: str | None = Cookie(None)):
        if not valid_admin_token(admin_token):
            return RedirectResponse("/admin/login", status_code=303)
        item = await self.menu_service.get_by_id(item_id)
        if not item:
            raise HTTPException(404, "ไม่พบเมนูนี้")
        if not name.strip() or not category.strip():
            raise HTTPException(422, "กรุณาระบุชื่อเมนูและหมวดหมู่")
        image_name = await self._image(image, item.image)
        await self.menu_service.update_item(item_id, name.strip(), round(price, 2), image_name, category.strip())
        return RedirectResponse("/admin/?saved=1", status_code=303)

    async def delete_menu(self, item_id: int, admin_token: str | None = Cookie(None)):
        if not valid_admin_token(admin_token):
            return RedirectResponse("/admin/login", status_code=303)
        await self.menu_service.delete_item(item_id)
        return RedirectResponse("/admin/?deleted=1", status_code=303)
