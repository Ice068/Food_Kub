import secrets
from fastapi import APIRouter, HTTPException, Depends, Header
from app.core.admin_auth import admin_api_key
from pydantic import BaseModel, Field
from app.services.menu_service import MenuService

def require_admin(x_food_kub_key: str | None = Header(None)):
    if not x_food_kub_key or not secrets.compare_digest(x_food_kub_key, admin_api_key()):
        raise HTTPException(401, "Admin access required")


router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])
menu_service = MenuService()

class AddItemSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    price: float = Field(..., gt=0, le=100000, allow_inf_nan=False)
    image: str
    category: str = Field(..., min_length=1, max_length=60)

@router.post("/add")
async def add_item(payload: AddItemSchema):
    new_item = menu_service.add_item(
        name=payload.name,
        price=payload.price,
        image=payload.image,
        category=payload.category
    )
    return {"status": "success", "item": new_item.to_dict()}

@router.post("/delete/{item_id}")
async def delete_item(item_id: int):
    success = menu_service.delete_item(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found or delete failed")
    return {"status": "success", "message": f"Item {item_id} deleted"}


@router.post("/edit/{item_id}")
async def edit_item(item_id: int, payload: AddItemSchema):
    item = menu_service.update_item(item_id, **payload.model_dump())
    if item is None:
        raise HTTPException(404, "Item not found")
    return {"status": "success", "item": item.to_dict()}
