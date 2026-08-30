from fastapi import APIRouter, HTTPException
from app.services.menu_service import MenuService

router = APIRouter(prefix="/api/menu", tags=["Menu"])
menu_service = MenuService()

@router.get("")
async def get_menu():
    items = menu_service.get_all()
    return [item.to_dict() for item in items]

@router.get("/categories")
async def get_categories():
    return menu_service.get_categories()

@router.get("/category/{category}")
async def get_by_category(category: str):
    items = menu_service.get_by_category(category)
    return [item.to_dict() for item in items]

@router.get("/{item_id}")
async def get_by_id(item_id: int):
    item = menu_service.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return item.to_dict()
