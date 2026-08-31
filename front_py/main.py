from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.services.menu_service import MenuService
from app.services.template_service import TemplateService
from app.services.cart_service import CartService
from app.services.payment_service import PaymentService
from app.routers.menu_router import MenuRouter
from app.routers.cart_router import CartRouter
from app.routers.admin_router import AdminRouter
from app.routers.payment_router import PaymentRouter


class Application:
    

    def __init__(self):
        self.app = FastAPI(title=settings.APP_TITLE)
        self.app.add_middleware(SessionMiddleware, secret_key="food-kub-secret-key")
        self.menu_service = MenuService()
        self.cart_service = CartService()
        self.payment_service = PaymentService()
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
        menu_router = MenuRouter(self.menu_service, self.template_service, self.cart_service)
        cart_router = CartRouter(
            self.cart_service,
            self.menu_service,
            self.template_service
        )
        admin_router = AdminRouter(self.menu_service, self.template_service)
        payment_router = PaymentRouter(
            self.payment_service,
            self.cart_service,
            self.menu_service,
            self.template_service
        )
        self.app.include_router(menu_router.router)
        self.app.include_router(cart_router.router)
        self.app.include_router(admin_router.router)
        self.app.include_router(payment_router.router)

    def get_app(self) -> FastAPI:
        return self.app


application = Application()
app = application.get_app()