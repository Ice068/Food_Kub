import os
import uuid

# ต้องนำเข้า Cookie เพิ่มเติมตรงนี้ด้วย
from fastapi import APIRouter, Request, Form, UploadFile, File, Cookie
from fastapi.responses import RedirectResponse

from app.services.menu_service import MenuService
from app.services.template_service import TemplateService

class AdminRouter:
    IMAGE_DIR = "static/images"

    def __init__(self, menu_service: MenuService, template_service: TemplateService):
        self.router = APIRouter(prefix="/admin")
        self.menu_service = menu_service
        self.template_service = template_service
        self._register_routes()

    def _register_routes(self):
        # หน้าจอ Admin (ต้องล็อกอินก่อน)
        self.router.add_api_route("/", self.show_admin_page, methods=["GET"])
        self.router.add_api_route("/add", self.add_menu, methods=["POST"])
        self.router.add_api_route("/delete/{item_id}", self.delete_menu, methods=["POST"])
        
        # ระบบ Login / Logout
        self.router.add_api_route("/login", self.show_login_page, methods=["GET"])
        self.router.add_api_route("/login", self.process_login, methods=["POST"])
        self.router.add_api_route("/logout", self.logout, methods=["GET"])

    async def show_login_page(self, request: Request):
        return self.template_service.render(
            request, "login.html", {"title": "เข้าสู่ระบบ (Admin)"}
        )

    async def process_login(
        self, 
        request: Request, 
        username: str = Form(...), 
        password: str = Form(...)
    ):
        if username == "admin" and password == "123456":
            # ล็อกอินสำเร็จ -> เด้งไปหน้า Admin
            response = RedirectResponse(url="/admin/", status_code=303)
            # สร้าง Cookie ชื่อ "admin_token" เพื่อจำว่าคนนี้คือ Admin
            response.set_cookie(key="admin_token", value="logged_in", httponly=True)
            return response
        else:
            return self.template_service.render(
                request, "login.html", 
                {"title": "เข้าสู่ระบบ (Admin)", "error": "❌ ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง"}
            )

    async def logout(self):
        # ลบ Cookie ทิ้งเมื่อกดออกจากระบบ
        response = RedirectResponse(url="/admin/login", status_code=303)
        response.delete_cookie("admin_token")
        return response

    # ==========================================
    # ส่วนที่ถูกป้องกัน (ต้องมี Cookie ถึงจะเข้าได้)
    # ==========================================

    async def show_admin_page(self, request: Request, admin_token: str = Cookie(None)):
        # ถ้าไม่มี Token แปลว่ายังไม่ได้ล็อกอิน ให้เด้งกลับไปหน้า Login
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)

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
        admin_token: str = Cookie(None) # เช็คสิทธิ์ก่อนเพิ่มเมนู
    ):
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)

        image_filename = "default.jpg"
        if image and image.filename:
            ext = os.path.splitext(image.filename)[1]
            image_filename = f"{uuid.uuid4().hex}{ext}"
            save_path = os.path.join(self.IMAGE_DIR, image_filename)
            with open(save_path, "wb") as f:
                content = await image.read()
                f.write(content)

        await self.menu_service.add_item(name, price, image_filename, category)
        return RedirectResponse(url="/admin/", status_code=303)

    async def delete_menu(self, item_id: int, admin_token: str = Cookie(None)): # เช็คสิทธิ์ก่อนลบ
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)
            
        await self.menu_service.delete_item(item_id)
        return RedirectResponse(url="/admin/", status_code=303)