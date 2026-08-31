import os
import uuid

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse

from app.services.menu_service import MenuService
from app.services.template_service import TemplateService


class AdminRouter:
    """หน้าที่ของ Admin: ล็อกอิน, ดูรายการเมนูทั้งหมด, เพิ่มเมนูใหม่, ลบเมนู"""

    IMAGE_DIR = "static/images"

    def __init__(self, menu_service: MenuService, template_service: TemplateService):
        # สร้าง Router โดยให้ prefix เริ่มที่ /admin เหมือนเดิม
        self.router = APIRouter(prefix="/admin")
        self.menu_service = menu_service
        self.template_service = template_service
        self._register_routes()

    def _register_routes(self):
        # ---- หน้าจัดการเมนูเดิม (อาจต้องเช็คว่าล็อกอินหรือยังในอนาคต) ----
        self.router.add_api_route("/", self.show_admin_page, methods=["GET"])
        self.router.add_api_route("/add", self.add_menu, methods=["POST"])
        self.router.add_api_route("/delete/{item_id}", self.delete_menu, methods=["POST"])
        
        # ---- เพิ่ม Route สำหรับ Login เข้ามาใหม่ ----
        self.router.add_api_route("/login", self.show_login_page, methods=["GET"])
        self.router.add_api_route("/login", self.process_login, methods=["POST"])

    # 1. ฟังก์ชันแสดงหน้าเว็บ login.html
    async def show_login_page(self, request: Request):
        return self.template_service.render(
            request, "login.html", {"title": "เข้าสู่ระบบ (Admin)"}
        )

    # 2. ฟังก์ชันรับข้อมูล Username/Password จากหน้าเว็บ
    async def process_login(
        self, 
        request: Request, 
        username: str = Form(...), 
        password: str = Form(...)
    ):
        # ตัวอย่างการตรวจสอบรหัสผ่าน (ของจริงควรเช็คจาก Database)
        if username == "admin" and password == "123456":
            
            # ถ้ารหัสถูก ให้เด้งกลับไปหน้าจอหลักของ Admin
            response = RedirectResponse(url="/admin/", status_code=303)
            
            # 💡 TODO: อนาคตควรเพิ่มโค้ดฝัง Cookie/Session ตรงนี้
            # response.set_cookie(key="is_admin", value="true")
            
            return response
            
        else:
            # ถ้ารหัสผิด ให้แสดงหน้า login เหมือนเดิม และส่งตัวแปร error ไปโชว์
            return self.template_service.render(
                request, 
                "login.html", 
                {
                    "title": "เข้าสู่ระบบ (Admin)", 
                    "error": "❌ ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง"
                }
            )

    # ----------- (โค้ดเดิมด้านล่างนี้เหมือนเดิมทุกประการ) -----------

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
        image_filename = "default.jpg"  # ค่าเริ่มต้นถ้าไม่ได้อัปโหลดรูป

        if image and image.filename:
            # ตั้งชื่อไฟล์ใหม่แบบสุ่ม กันชื่อซ้ำ
            ext = os.path.splitext(image.filename)[1]
            image_filename = f"{uuid.uuid4().hex}{ext}"
            save_path = os.path.join(self.IMAGE_DIR, image_filename)
            with open(save_path, "wb") as f:
                content = await image.read()
                f.write(content)

        await self.menu_service.add_item(name, price, image_filename, category)
        return RedirectResponse(url="/admin/", status_code=303)

    async def delete_menu(self, item_id: int):
        await self.menu_service.delete_item(item_id)
        return RedirectResponse(url="/admin/", status_code=303)