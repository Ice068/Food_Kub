import logging
import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.services.menu_service import MenuService
from app.services.template_service import TemplateService
from app.services.cart_service import CartService
from app.services.payment_service import PaymentService
from app.services.stats_service import StatsService

from app.routers.menu_router import MenuRouter
from app.routers.cart_router import CartRouter
from app.routers.admin_router import AdminRouter
from app.routers.payment_router import PaymentRouter
from app.routers.table_router import TableRouter
from app.routers.dashboard_router import DashboardRouter


class Application:

    def __init__(self):
        self.app = FastAPI(title=settings.APP_TITLE)

        self.app.add_middleware(
            SessionMiddleware,
            secret_key=settings.SESSION_SECRET,
            https_only=settings.COOKIE_SECURE,
            same_site="lax",
            max_age=60 * 60 * 24 * 30,
        )

        self.menu_service = MenuService()
        self.cart_service = CartService()
        self.payment_service = PaymentService()
        self.stats_service = StatsService()
        self.template_service = TemplateService(
            settings.TEMPLATES_DIR
        )

        self._mount_static()
        self._include_routers()
        self._register_error_handlers()

    def _register_error_handlers(self):
        def error_response(request: Request, status: int, message: str):
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse({"ok": False, "detail": message, "error": message}, status_code=status)
            response = self.template_service.render(request, "error.html", {
                "title": "ให้เราลองอีกครั้ง · Food Kub", "message": message,
                "status_code": status, "error": message,
            })
            response.status_code = status
            return response

        @self.app.exception_handler(HTTPException)
        async def http_error(request, exc):
            return error_response(request, exc.status_code, str(exc.detail))

        @self.app.exception_handler(RequestValidationError)
        async def invalid_request(request, exc):
            return error_response(request, 422, "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบช่องที่กรอกและลองอีกครั้ง")

        @self.app.exception_handler(httpx.HTTPError)
        async def backend_error(request, exc):
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else 503
            message = "ติดต่อครัวไม่สำเร็จ กรุณาลองอีกครั้ง ข้อมูลในตะกร้ายังอยู่"
            if isinstance(exc, httpx.HTTPStatusError) and status in (400, 404, 409, 422):
                try:
                    message = str(exc.response.json().get("detail", message))
                except ValueError:
                    pass
            return error_response(request, status, message)

        @self.app.exception_handler(Exception)
        async def unexpected_error(request, exc):
            logging.getLogger(__name__).exception("Unexpected request failure", exc_info=exc)
            return error_response(request, 500, "เกิดข้อผิดพลาดชั่วคราว กรุณากลับไปที่เมนูแล้วลองอีกครั้ง")

    def _mount_static(self):
        self.app.mount(
            settings.STATIC_URL,
            StaticFiles(directory=settings.STATIC_DIR),
            name="static",
        )

    def _include_routers(self):
        menu_router = MenuRouter(
            self.menu_service,
            self.template_service,
            self.cart_service,
        )

        cart_router = CartRouter(
            self.cart_service,
            self.menu_service,
            self.template_service,
            stats_service=self.stats_service,
        )

        admin_router = AdminRouter(
            self.menu_service,
            self.template_service,
        )

        payment_router = PaymentRouter(
            self.payment_service,
            self.cart_service,
            self.menu_service,
            self.template_service,
            stats_service=self.stats_service,
        )

        dashboard_router = DashboardRouter(
            stats_service=self.stats_service,
            menu_service=self.menu_service,
            template_service=self.template_service,
        )

        self.app.include_router(menu_router.router)
        self.app.include_router(cart_router.router)
        self.app.include_router(admin_router.router)
        self.app.include_router(payment_router.router)
        self.app.include_router(
            TableRouter(self.template_service).router
        )
        self.app.include_router(dashboard_router.router)

    def get_app(self) -> FastAPI:
        return self.app


application = Application()
app = application.get_app()
