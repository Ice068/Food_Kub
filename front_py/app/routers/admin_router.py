import os
import uuid

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse

from app.services.menu_service import MenuService
from app.services.template_service import TemplateService
from app.core.storage import upload_image_to_cloud


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
        items = [item.to_dict() for item in await self.menu_service.get_all()]
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
        image_result = "default.jpg"
        if image and image.filename:
            content = await image.read()
            # ลองอัปโหลดขึ้น Cloud Storage
            cloud_url = await upload_image_to_cloud(content, image.filename)
            if cloud_url:
                image_result = cloud_url
            else:
                # Fallback: บันทึกลงเครื่องหากเกิดข้อผิดพลาด
                os.makedirs(self.IMAGE_DIR, exist_ok=True)
                ext = os.path.splitext(image.filename)[1]
                image_filename = f"{uuid.uuid4().hex}{ext}"
                save_path = os.path.join(self.IMAGE_DIR, image_filename)
                with open(save_path, "wb") as f:
                    f.write(content)
                image_result = image_filename

        await self.menu_service.add_item(name, price, image_result, category)
        return RedirectResponse(url="/admin/", status_code=303)

    async def delete_menu(self, item_id: int):
        await self.menu_service.delete_item(item_id)
        return RedirectResponse(url="/admin/", status_code=303)