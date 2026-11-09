from fastapi import FastAPI

from app.core.config import settings
from app.routers.menu_api import router as menu_router
from app.routers.admin_api import router as admin_router
from app.routers.payment_api import router as payment_router
from app.routers.stats_api import router as stats_router
from app.routers.table_settings_api import router as table_settings_router

app = FastAPI(title=settings.APP_TITLE)

# ลงทะเบียน API ของระบบ
app.include_router(menu_router)
app.include_router(admin_router)
app.include_router(payment_router)
app.include_router(stats_router)
app.include_router(table_settings_router)


@app.get("/")
async def root():
    return {
        "message": "Welcome to Food_Kub Backend API!"
    }