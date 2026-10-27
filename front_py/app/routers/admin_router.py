import os
import uuid
import base64
from io import BytesIO
from urllib.parse import quote

import qrcode
import httpx

# ต้องนำเข้า Cookie เพิ่มเติมตรงนี้ด้วย
from fastapi import APIRouter, Request, Form, UploadFile, File, Cookie
from fastapi.responses import RedirectResponse
from app.services.menu_service import MenuService
from app.services.template_service import TemplateService
from app.services.dashboard_service import DashboardService

class AdminRouter:
    IMAGE_DIR = "static/images"

    def __init__(self, menu_service: MenuService, template_service: TemplateService, dashboard_service: DashboardService | None = None):
        self.router = APIRouter(prefix="/admin")
        self.menu_service = menu_service
        self.template_service = template_service
        self.dashboard_service = dashboard_service or DashboardService()
        self._register_routes()

    def _register_routes(self):
        # หน้าจอ Admin (ต้องล็อกอินก่อน)
        self.router.add_api_route("/", self.show_admin_page, methods=["GET"])
        self.router.add_api_route("/dashboard", self.show_dashboard, methods=["GET"])
        self.router.add_api_route("/tables", self.show_tables_page, methods=["GET"])
        self.router.add_api_route("/add", self.add_menu, methods=["POST"])
        self.router.add_api_route("/delete/{item_id}", self.delete_menu, methods=["POST"])
        self.router.add_api_route("/availability/{item_id}", self.set_availability, methods=["POST"])
        self.router.add_api_route("/tables/{table_number}/status", self.set_table_status, methods=["POST"])
        self.router.add_api_route("/tables/{table_number}/pay", self.record_cash_payment, methods=["POST"])
        self.router.add_api_route("/tables/{table_number}/reset", self.reset_table, methods=["POST"])
        self.router.add_api_route("/tables/{table_number}/items/{item_id}/kitchen", self.set_kitchen_status, methods=["POST"])
        
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
            # ล็อกอินสำเร็จ -> เด้งไปหน้าแดชบอร์ด
            response = RedirectResponse(url="/admin/dashboard", status_code=303)
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

        try:
            items = [item.to_dict() for item in await self.menu_service.get_all()]
            backend_available = True
        except httpx.HTTPError:
            items = []
            backend_available = False
        return self.template_service.render(
            request,
            "admin.html",
            {"title": "จัดการเมนู (Admin)", "items": items, "backend_available": backend_available},
        )

    async def show_dashboard(self, request: Request, admin_token: str = Cookie(None)):
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)

        try:
            items = [item.to_dict() for item in await self.menu_service.get_all()]
            inventory_available = True
        except httpx.HTTPError:
            items = []
            inventory_available = False
        try:
            data = await self.dashboard_service.dashboard_data()
            stats_available = True
        except httpx.HTTPError:
            data = {
                "today": "—", "revenue": 0, "bills": 0,
                "revenue_yesterday": 0, "bills_yesterday": 0,
                "active_tables": 0, "total_tables": 10, "top_dish": None,
                "popular": [], "trend": [], "trend_max": 0,
                "categories": [], "live_tables": [], "transactions": [],
            }
            stats_available = False
        return self.template_service.render(
            request,
            "dashboard.html",
            {
                "title": "แดชบอร์ดร้านอาหาร",
                "items": items,
                "available_count": sum(1 for item in items if item.get("available", True)),
                "sold_out_count": sum(1 for item in items if not item.get("available", True)),
                "inventory_available": inventory_available,
                "stats_available": stats_available,
                **data,
                "error": request.query_params.get("error"),
                "message": request.query_params.get("message"),
            },
        )

    async def set_table_status(self, table_number: int, status: str = Form(...), admin_token: str = Cookie(None)):
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)
        try:
            await self.dashboard_service.set_table_status(table_number, status)
        except httpx.HTTPError as exc:
            return RedirectResponse(url="/admin/dashboard?error=" + quote(str(exc)), status_code=303)
        return RedirectResponse(url="/admin/dashboard", status_code=303)

    async def record_cash_payment(self, table_number: int, method: str = Form("cash"), admin_token: str = Cookie(None)):
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)
        try:
            await self.dashboard_service.record_payment(table_number, method)
        except httpx.HTTPError as exc:
            return RedirectResponse(url="/admin/dashboard?error=" + quote(str(exc)), status_code=303)
        return RedirectResponse(url="/admin/dashboard?message=บันทึกการชำระเงินแล้ว", status_code=303)

    async def reset_table(self, table_number: int, admin_token: str = Cookie(None)):
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)
        try:
            await self.dashboard_service.reset_table(table_number)
        except httpx.HTTPError as exc:
            return RedirectResponse(url="/admin/dashboard?error=" + quote(str(exc)), status_code=303)
        return RedirectResponse(url="/admin/dashboard?message=เคลียร์โต๊ะเรียบร้อย", status_code=303)

    async def set_kitchen_status(self, table_number: int, item_id: int, status: str = Form(...), admin_token: str = Cookie(None)):
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)
        try:
            await self.dashboard_service.set_kitchen_status(table_number, item_id, status)
        except httpx.HTTPError as exc:
            return RedirectResponse(url="/admin/dashboard?error=" + quote(str(exc)), status_code=303)
        return RedirectResponse(url="/admin/dashboard", status_code=303)

    async def show_tables_page(self, request: Request, count: int = 10, admin_token: str = Cookie(None)):
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)
        count = max(1, min(count, 30))
        base_url = str(request.base_url).rstrip("/")
        tables = []
        for table_number in range(1, count + 1):
            target_url = f"{base_url}/?table={table_number}"
            qr = qrcode.make(target_url)
            image_buffer = BytesIO()
            qr.save(image_buffer, format="PNG")
            qr_data = base64.b64encode(image_buffer.getvalue()).decode("ascii")
            tables.append({"number": table_number, "target_url": target_url, "qr_data": qr_data})
        return self.template_service.render(
            request,
            "admin_tables.html",
            {"title": "QR Code โต๊ะ", "tables": tables, "count": count},
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

    async def set_availability(self, item_id: int, available: bool = Form(...), admin_token: str = Cookie(None)):
        if not admin_token:
            return RedirectResponse(url="/admin/login", status_code=303)
        await self.menu_service.set_availability(item_id, available)
        return RedirectResponse(url="/admin/", status_code=303)
