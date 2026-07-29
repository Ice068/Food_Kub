import os
import uuid

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse

from app.services.menu_service import MenuService
from app.services.template_service import TemplateService


class AdminRouter:
    """หน้าที่ของ Admin: ดูรายการเมนูทั้งหมด, เพิ่มเมนูใหม่, ลบเมนู"""

    IMAGE_DIR = "static/images"

    def __init__(self, menu_service: MenuService, template_service: TemplateService):
        self.router = APIRouter(prefix="/admin")
        self.menu_service = menu_service
        self.template_service = template_service
        self._register_routes()

    def _register_routes(self):
        self.router.add_api_route("/", self.show_admin_page, methods=["GET"])
        self.router.add_api_route("/add", self.add_menu, methods=["POST"])
        self.router.add_api_route("/delete/{item_id}", self.delete_menu, methods=["POST"])

    async def show_admin_page(self, request: Request):
        items = [item.to_dict() for item in self.menu_service.get_all()]
        return self.template_service.render(
            request, "admin.html", {"title": "จัดการเมนู (Admin)", "items": items}
        )

    async def add_menu(
        self,
        name: str = Form(...),
        price: float = Form(...),
        category: str = Form(...),
        image: UploadFile = File(None),
    ):
        image_filename = "default.jpg"  # ค่าเริ่มต้นถ้าไม่ได้อัปโหลดรูป

        if image and image.filename:
            # ตั้งชื่อไฟล์ใหม่แบบสุ่ม กันชื่อซ้ำ
            ext = os.path.splitext(image.filename)[1]
            image_filename = f"{uuid.uuid4().hex}{ext}"
            save_path = os.path.join(self.IMAGE_DIR, image_filename)
            with open(save_path, "wb") as f:
                content = await image.read()
                f.write(content)

        self.menu_service.add_item(name, price, image_filename, category)
        return RedirectResponse(url="/admin/", status_code=303)

    async def delete_menu(self, item_id: int):
        self.menu_service.delete_item(item_id)
        return RedirectResponse(url="/admin/", status_code=303)