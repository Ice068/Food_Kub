from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.services.menu_service import MenuService
from app.services.template_service import TemplateService
from app.routers.menu_router import MenuRouter
from app.routers.cart_router import CartRouter
from app.routers.admin_router import AdminRouter

class Application:
    """ประกอบทุกส่วนของแอปเข้าด้วยกัน (dependency wiring)"""

    def __init__(self):
        self.app = FastAPI(title=settings.APP_TITLE)
        self.menu_service = MenuService()
        self.template_service = TemplateService(settings.TEMPLATES_DIR)
        self._mount_static()
        self._include_routers()

    def _mount_static(self):
        self.app.mount(
            settings.STATIC_URL,
            StaticFiles(directory=settings.STATIC_DIR),
            name="static",
        )

    def _include_routers(self):
        menu_router = MenuRouter(self.menu_service, self.template_service)
        cart_router = CartRouter(self.template_service)
        self.app.include_router(menu_router.router)
        self.app.include_router(cart_router.router)

    def get_app(self) -> FastAPI:
        return self.app


application = Application()
app = application.get_app()  # uvicorn/fastapi ต้องการตัวแปรชื่อ app
