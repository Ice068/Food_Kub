from fastapi import FastAPI
from app.routers.menu_api import router as menu_router
from app.routers.admin_api import router as admin_router
from app.routers.payment_api import router as payment_router
from app.core.config import settings

app = FastAPI(title=settings.APP_TITLE)

# Include routers
app.include_router(menu_router)
app.include_router(admin_router)
app.include_router(payment_router)

@app.get("/")
async def root():
    return {"message": "Welcome to Food_Kub Backend API!"}
