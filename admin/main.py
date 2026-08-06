from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core import settings
from app.services.menu_service import MenuService
from app.repositories.menu_repository import JsonMenuRepository
from app.routers.admin_router import AdminRouter


class Application:
    """ประกอบทุกส่วนของแอป Admin เข้าด้วยกัน (dependency wiring)"""

    def __init__(self):
        self.app = FastAPI(title=settings.APP_TITLE)
        self.menu_repository = JsonMenuRepository(
            data_file=settings.MENU_DATA_FILE,
            images_dir=settings.MENU_IMAGES_DIR,
        )
        self.menu_service = MenuService(self.menu_repository)
        self.templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)
        self._mount_static()
        self._include_routers()

    def _mount_static(self):
        self.app.mount(
            "/media",
            StaticFiles(directory=settings.MENU_IMAGES_DIR),
            name="media",
        )
        self.app.mount(
            settings.STATIC_URL,
            StaticFiles(directory=settings.STATIC_DIR),
            name="static",
        )

    def _include_routers(self):
        admin_router = AdminRouter(self.menu_service, self.templates)
        self.app.include_router(admin_router.router)

    def get_app(self) -> FastAPI:
        return self.app


application = Application()
app = application.get_app()