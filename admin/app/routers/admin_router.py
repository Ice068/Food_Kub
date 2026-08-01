import os
import uuid

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core import settings
from app.services.menu_service import MenuService


class AdminRouter:
    """หน้าที่ของ Admin: ดูรายการเมนูทั้งหมด, เพิ่ม, แก้ไข, ลบเมนู"""

    def __init__(self, menu_service: MenuService, templates: Jinja2Templates):
        self.router = APIRouter()
        self.menu_service = menu_service
        self.templates = templates
        self._register_routes()

    def _register_routes(self):
        self.router.add_api_route("/", self.show_list, methods=["GET"])
        self.router.add_api_route("/add", self.add_menu, methods=["POST"])
        self.router.add_api_route("/edit/{item_id}", self.show_edit, methods=["GET"])
        self.router.add_api_route("/edit/{item_id}", self.edit_menu, methods=["POST"])
        self.router.add_api_route("/delete/{item_id}", self.delete_menu, methods=["POST"])

    async def show_list(self, request: Request):
        items = [item.to_dict() for item in self.menu_service.get_all()]
        return self.templates.TemplateResponse(
            request, "admin.html", {"title": "จัดการเมนู (Admin)", "items": items}
        )

    def _save_uploaded_image(self, image: UploadFile) -> str:
        ext = os.path.splitext(image.filename)[1]
        filename = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(settings.MENU_IMAGES_DIR, filename)
        with open(path, "wb") as f:
            f.write(image.file.read())
        return filename

    async def add_menu(
        self,
        name: str = Form(...),
        price: float = Form(...),
        category: str = Form(...),
        image: UploadFile = File(None),
    ):
        image_filename = "default.jpg"
        if image and image.filename:
            image_filename = self._save_uploaded_image(image)

        self.menu_service.add_item(name, price, image_filename, category)
        return RedirectResponse(url="/", status_code=303)

    async def show_edit(self, request: Request, item_id: int):
        item = self.menu_service.get_by_id(item_id)
        if not item:
            return RedirectResponse(url="/", status_code=303)
        return self.templates.TemplateResponse(
            request, "edit.html", {"title": "แก้ไขเมนู", "item": item.to_dict()}
        )

    async def edit_menu(
        self,
        item_id: int,
        name: str = Form(...),
        price: float = Form(...),
        category: str = Form(...),
        image: UploadFile = File(None),
    ):
        image_filename = None
        if image and image.filename:
            image_filename = self._save_uploaded_image(image)

        self.menu_service.update_item(item_id, name, price, category, image_filename)
        return RedirectResponse(url="/", status_code=303)

    async def delete_menu(self, item_id: int):
        self.menu_service.delete_item(item_id)
        return RedirectResponse(url="/", status_code=303)
